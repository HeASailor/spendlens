"""Core spend analytics. Pure standard library."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

REQUIRED = {"supplier", "amount"}
LEGAL_SUFFIXES = {
    "pvt", "ltd", "private", "limited", "inc", "incorporated", "llc", "llp",
    "gmbh", "co", "corp", "corporation", "company", "plc", "sa", "bv", "ag",
}

# Illustrative savings assumptions. Tune these to your own benchmarks.
DEFAULT_ASSUMPTIONS = {
    "tail_consolidation": 0.08,   # savings on tail spend moved to preferred suppliers
    "maverick_to_po": 0.05,       # savings from routing off-PO spend through PO + contract
    "duplicate_merge": 0.03,      # volume leverage from merging duplicate supplier records
}


def normalize_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    tokens = [t for t in s.split() if t not in LEGAL_SUFFIXES]
    return " ".join(tokens)


@dataclass
class Analysis:
    rows: int = 0
    total_spend: float = 0.0
    supplier_records: int = 0
    unique_suppliers: int = 0
    pareto_suppliers_80: int = 0
    tail_suppliers: int = 0
    tail_spend: float = 0.0
    maverick_spend: float = 0.0
    maverick_pct: float = 0.0
    short_terms_pct: float = 0.0
    hhi_by_category: dict = field(default_factory=dict)
    categories: list = field(default_factory=list)       # (name, spend)
    top_suppliers: list = field(default_factory=list)    # (name, spend, cumulative %)
    monthly: list = field(default_factory=list)          # (YYYY-MM, spend)
    duplicate_clusters: list = field(default_factory=list)  # (canonical, [names], spend)
    duplicate_spend: float = 0.0
    savings: dict = field(default_factory=dict)
    savings_total: float = 0.0


def load(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = {c.strip().lower() for c in (reader.fieldnames or [])}
        missing = REQUIRED - cols
        if missing:
            raise ValueError(f"CSV is missing required column(s): {', '.join(sorted(missing))}")
        rows = []
        for r in reader:
            r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
            try:
                r["amount"] = float(r["amount"].replace(",", ""))
            except ValueError:
                continue  # skip unparseable amounts
            if r["amount"] <= 0 or not r["supplier"]:
                continue
            rows.append(r)
    return rows


def cluster_suppliers(names: list[str], threshold: float = 0.88) -> list[list[str]]:
    """Group supplier-name variants using normalisation + fuzzy match (union-find)."""
    norm = {n: normalize_name(n) for n in names}
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # exact match on normalised form
    by_norm = defaultdict(list)
    for n, k in norm.items():
        by_norm[k].append(n)
    for group in by_norm.values():
        for other in group[1:]:
            union(group[0], other)

    # fuzzy match across distinct normalised forms
    keys = sorted(by_norm)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if abs(len(a) - len(b)) > 6:
                continue
            if a[:2] != b[:2]:
                continue
            # names that differ in their numbers are different entities
            if re.findall(r"\d+", a) != re.findall(r"\d+", b):
                continue
            if SequenceMatcher(None, a, b).ratio() >= threshold:
                union(by_norm[a][0], by_norm[b][0])

    groups = defaultdict(list)
    for n in names:
        groups[find(n)].append(n)
    return list(groups.values())


def analyze(rows: list[dict], assumptions: dict | None = None,
            fuzzy_threshold: float = 0.88) -> Analysis:
    a = Analysis()
    assume = {**DEFAULT_ASSUMPTIONS, **(assumptions or {})}
    if not rows:
        return a

    a.rows = len(rows)
    a.total_spend = sum(r["amount"] for r in rows)

    # --- supplier consolidation (merge variants first, so metrics are honest)
    spend_by_name = defaultdict(float)
    for r in rows:
        spend_by_name[r["supplier"]] += r["amount"]
    a.supplier_records = len(spend_by_name)

    clusters = cluster_suppliers(list(spend_by_name), fuzzy_threshold)
    canon_of = {}
    spend_by_supplier = {}
    for g in clusters:
        canonical = " ".join(normalize_name(max(g, key=lambda n: spend_by_name[n])).split()).title()
        spend_by_supplier[canonical] = sum(spend_by_name[n] for n in g)
        for n in g:
            canon_of[n] = canonical
        if len(g) > 1:
            a.duplicate_clusters.append(
                (canonical, sorted(g), spend_by_supplier[canonical]))
    a.duplicate_clusters.sort(key=lambda c: -c[2])
    a.duplicate_spend = sum(c[2] for c in a.duplicate_clusters)
    a.unique_suppliers = len(spend_by_supplier)

    # --- pareto + tail
    ranked = sorted(spend_by_supplier.items(), key=lambda kv: -kv[1])
    cum = 0.0
    for name, s in ranked:
        cum += s
        a.top_suppliers.append((name, s, cum / a.total_spend * 100))
    a.pareto_suppliers_80 = next(
        (i + 1 for i, t in enumerate(a.top_suppliers) if t[2] >= 80), len(ranked))
    # tail = suppliers that together make up the bottom 20% of spend
    tail_cum, tail_n = 0.0, 0
    for name, s in reversed(ranked):
        if tail_cum + s > a.total_spend * 0.20:
            break
        tail_cum += s
        tail_n += 1
    a.tail_suppliers, a.tail_spend = tail_n, tail_cum
    a.top_suppliers = a.top_suppliers[:10]

    # --- maverick (no PO)
    if any("po_number" in r for r in rows):
        a.maverick_spend = sum(r["amount"] for r in rows if not r.get("po_number"))
        a.maverick_pct = a.maverick_spend / a.total_spend * 100

    # --- payment terms
    terms = [(r["amount"], r.get("payment_terms_days", "")) for r in rows]
    valid = [(amt, int(t)) for amt, t in terms if t.isdigit()]
    if valid:
        tot = sum(x for x, _ in valid)
        a.short_terms_pct = sum(x for x, t in valid if t < 45) / tot * 100

    # --- categories, HHI
    cat_spend = defaultdict(float)
    cat_sup = defaultdict(lambda: defaultdict(float))
    for r in rows:
        c = r.get("category") or "Uncategorised"
        cat_spend[c] += r["amount"]
        cat_sup[c][canon_of[r["supplier"]]] += r["amount"]
    a.categories = sorted(cat_spend.items(), key=lambda kv: -kv[1])
    for c, sups in cat_sup.items():
        tot = sum(sups.values())
        a.hhi_by_category[c] = round(sum((v / tot * 100) ** 2 for v in sups.values()))

    # --- monthly trend
    mo = defaultdict(float)
    for r in rows:
        d = r.get("date", "")
        if len(d) >= 7:
            mo[d[:7]] += r["amount"]
    a.monthly = sorted(mo.items())

    # --- savings (illustrative)
    a.savings = {
        "Tail spend consolidation": a.tail_spend * assume["tail_consolidation"],
        "Maverick spend onto PO/contract": a.maverick_spend * assume["maverick_to_po"],
        "Duplicate supplier merge": a.duplicate_spend * assume["duplicate_merge"],
    }
    a.savings_total = sum(a.savings.values())
    return a
