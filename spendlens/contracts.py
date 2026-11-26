"""Contract coverage: how much of the spend sat under a contract that was live on the invoice date.

Each invoice gets one status:

* covered: the supplier had a contract in scope whose dates include the invoice date
* outside contract dates: the supplier has a contract in scope, but not live on that date
* no contract: nothing in your list for that supplier (or that supplier and category)
* undated: the supplier has a contract in scope, but the invoice date cannot be read

"Covered" means a contract existed. It does not check that its price or terms were followed.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .names import name_similarity, normalize_name

REQUIRED = ("supplier", "start_date", "end_date")
EXPIRY_DAYS = 90
COVERED, OUTSIDE, NONE, UNDATED = "covered", "outside contract dates", "no contract", "undated"
STATUSES = (COVERED, OUTSIDE, NONE, UNDATED)


@dataclass
class Contract:
    supplier: str
    start: date
    end: date
    category: str = ""        # blank = applies to everything bought from the supplier
    contract_id: str = ""


@dataclass
class Coverage:
    spend: dict = field(default_factory=dict)       # status -> spend
    invoices: dict = field(default_factory=dict)    # status -> count
    covered_pct: float = 0.0
    suppliers: list = field(default_factory=list)   # SupplierCoverage, most uncovered spend first
    expiring: list = field(default_factory=list)    # (Contract, supplier, days left, covered spend)
    unmatched: list = field(default_factory=list)   # contracts whose supplier is not in the spend file
    contracts: int = 0
    as_of: date | None = None                       # latest invoice date in the file
    expiry_days: int = EXPIRY_DAYS


@dataclass
class SupplierCoverage:
    supplier: str
    total: float = 0.0
    covered: float = 0.0
    outside: float = 0.0
    none: float = 0.0
    undated: float = 0.0

    @property
    def uncovered(self) -> float:
        return self.outside + self.none


def parse_date(text: str) -> date | None:
    """'2025-03-14' (a trailing time is ignored) -> date. None for anything else."""
    m = re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})(?:$|[ T])", text or "")
    if not m:
        return None
    try:
        return date(*map(int, m.groups()))
    except ValueError:
        return None


def load_contracts(path: str) -> list[Contract]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = {c.strip().lower() for c in (reader.fieldnames or [])}
        missing = [c for c in REQUIRED if c not in cols]
        if missing:
            raise ValueError(f"contracts file is missing column(s): {', '.join(missing)}")
        out = []
        for raw in reader:
            r = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            if not any(r.values()):
                continue
            where = f"contracts file line {reader.line_num}"
            if not r["supplier"]:
                raise ValueError(f"{where}: supplier is empty")
            start, end = parse_date(r["start_date"]), parse_date(r["end_date"])
            if not start or not end:
                raise ValueError(f"{where}: dates must be YYYY-MM-DD")
            if end < start:
                raise ValueError(f"{where}: end_date is before start_date")
            out.append(Contract(r["supplier"], start, end, r.get("category", ""),
                                r.get("contract_id", "")))
    if not out:
        raise ValueError("contracts file has no contracts")
    return out


def match_suppliers(contracts: list[Contract], canon_of: dict[str, str],
                    threshold: float = 0.88) -> tuple[dict, list]:
    """Attach each contract to a merged supplier from the spend file.

    Returns ({canonical supplier: [contracts]}, [contracts that matched nobody]). Contract names
    never change how spend suppliers are merged.
    """
    exact: dict[str, str] = {}
    for raw, canonical in canon_of.items():
        exact.setdefault(normalize_name(raw), canonical)
    matched: dict[str, list] = defaultdict(list)
    unmatched = []
    for c in contracts:
        key = normalize_name(c.supplier)
        canonical = exact.get(key)
        if canonical is None and key:
            score, best = max(((name_similarity(key, k), k) for k in exact), default=(0.0, ""))
            if score >= threshold:
                canonical = exact[best]
        if canonical is None:
            unmatched.append(c)
        else:
            matched[canonical].append(c)
    return matched, unmatched


def contract_coverage(rows: list[dict], canon_of: dict[str, str], contracts: list[Contract],
                      threshold: float = 0.88, expiry_days: int = EXPIRY_DAYS) -> Coverage:
    """Classify every row (sets `contract_status`) and summarise."""
    matched, unmatched = match_suppliers(contracts, canon_of, threshold)
    cov = Coverage(spend={s: 0.0 for s in STATUSES}, invoices={s: 0 for s in STATUSES},
                   unmatched=unmatched, contracts=len(contracts), expiry_days=expiry_days)
    suppliers: dict[str, SupplierCoverage] = {}
    under: dict[int, float] = defaultdict(float)     # id(contract) -> covered spend
    attr = {COVERED: "covered", OUTSIDE: "outside", NONE: "none", UNDATED: "undated"}
    for r in rows:
        sup = canon_of.get(r["supplier"], r["supplier"])
        cat = (r.get("category") or "").strip().lower()
        scope = [c for c in matched.get(sup, ())
                 if not c.category or c.category.lower() == cat]
        day = parse_date(r.get("date", ""))
        if day and (cov.as_of is None or day > cov.as_of):
            cov.as_of = day
        if not scope:
            status = NONE
        elif not day:
            status = UNDATED
        else:
            live = [c for c in scope if c.start <= day <= c.end]
            status = COVERED if live else OUTSIDE
            if live:
                # overlapping contracts: count the spend once, against the one ending last
                under[id(max(live, key=lambda c: c.end))] += r["amount"]
        r["contract_status"] = status
        cov.spend[status] += r["amount"]
        cov.invoices[status] += 1
        s = suppliers.setdefault(sup, SupplierCoverage(sup))
        s.total += r["amount"]
        setattr(s, attr[status], getattr(s, attr[status]) + r["amount"])

    total = sum(cov.spend.values())
    cov.covered_pct = cov.spend[COVERED] / total * 100 if total else 0.0
    cov.suppliers = sorted(suppliers.values(), key=lambda s: (-s.uncovered, s.supplier))

    if cov.as_of:
        horizon = cov.as_of + timedelta(days=expiry_days)
        for sup, items in matched.items():
            for c in items:
                if not cov.as_of <= c.end <= horizon:
                    continue
                # skip if a later contract with the same scope already takes over
                renewed = any(o.end > c.end and o.start <= c.end + timedelta(days=1)
                              and (not o.category or o.category.lower() == c.category.lower())
                              for o in items)
                if not renewed:
                    cov.expiring.append((c, sup, (c.end - cov.as_of).days, under[id(c)]))
        cov.expiring.sort(key=lambda e: (e[2], -e[3]))
    return cov
