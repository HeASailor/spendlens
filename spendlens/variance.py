"""Price variance: what the same item costs at different suppliers.

For each item bought from two or more (merged) suppliers, compute every supplier's
volume-weighted average price, take the cheapest as the benchmark, and size the gap:
the extra spend versus buying every unit at the best supplier's price.

The benchmark is a price you have already paid, not a market quote. It ignores spec,
incoterms and quality differences, so treat the gap as a lead to investigate.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

MIN_INVOICES = 3   # a supplier needs this many invoices for an item to count as a price point


@dataclass
class ItemVariance:
    item: str
    category: str
    suppliers: list = field(default_factory=list)   # (name, avg_price, qty, invoices), cheapest first
    best_supplier: str = ""
    best_price: float = 0.0
    avg_price: float = 0.0       # volume-weighted across all suppliers
    worst_price: float = 0.0
    spread_pct: float = 0.0      # (worst - best) / best
    spend: float = 0.0
    gap_value: float = 0.0       # spend minus (qty x best price)


def item_key(row: dict) -> str:
    """Item label for grouping. Prefers the `item` column, falls back to a cleaned description."""
    item = (row.get("item") or "").strip()
    if item:
        return re.sub(r"\s+", " ", item)
    desc = (row.get("description") or "").lower()
    desc = re.sub(r"\(.*?\)", " ", desc.split(",")[0])
    desc = re.sub(r"\d+(\.\d+)?\s*(mm|cm|kg|g|ml|l|ft|t|%|pcs)?", " ", desc)
    return re.sub(r"\s+", " ", desc).strip().title()


def unit_price(row: dict):
    """(quantity, price). Uses `unit_price` if present, otherwise amount / quantity."""
    try:
        qty = float(str(row.get("quantity") or row.get("qty") or "").replace(",", ""))
    except ValueError:
        return None
    if qty <= 0:
        return None
    raw = row.get("unit_price") or ""
    try:
        price = float(str(raw).replace(",", "")) if raw != "" else row["amount"] / qty
    except ValueError:
        return None
    return (qty, price) if price > 0 else None


def has_price_columns(rows: list[dict]) -> bool:
    return any(("quantity" in r or "qty" in r) and ("unit_price" in r or "amount" in r)
               and (r.get("item") or r.get("description")) for r in rows[:50])


def price_variance(rows: list[dict], canon_of: dict[str, str],
                   min_invoices: int = MIN_INVOICES) -> tuple[list[ItemVariance], float]:
    """Return (items sorted by gap value, spend covered by the analysis)."""
    # item -> supplier -> [qty, spend, invoices]
    book: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0]))
    cat_of: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        key = item_key(r)
        qp = unit_price(r)
        if not key or not qp:
            continue
        qty, price = qp
        cell = book[key][canon_of.get(r["supplier"], r["supplier"])]
        cell[0] += qty
        cell[1] += qty * price
        cell[2] += 1
        cat_of[key][r.get("category") or "Uncategorised"] += r["amount"]

    out: list[ItemVariance] = []
    covered = 0.0
    for key, sups in book.items():
        pts = [(s, v[1] / v[0], v[0], v[2]) for s, v in sups.items() if v[2] >= min_invoices]
        if len(pts) < 2:
            continue
        pts.sort(key=lambda p: p[1])
        qty = sum(p[2] for p in pts)
        spend = sum(p[1] * p[2] for p in pts)
        best = pts[0][1]
        covered += spend
        out.append(ItemVariance(
            item=key,
            category=max(cat_of[key].items(), key=lambda kv: kv[1])[0],
            suppliers=pts, best_supplier=pts[0][0], best_price=best,
            avg_price=spend / qty, worst_price=pts[-1][1],
            spread_pct=(pts[-1][1] - best) / best * 100,
            spend=spend, gap_value=spend - qty * best))
    out.sort(key=lambda i: -i.gap_value)
    return out, covered
