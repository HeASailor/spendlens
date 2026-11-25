"""Price trend over time, per item.

For each item with dated, priced invoices, SpendLens builds a unit-price series by month (or
quarter) and compares the first third of the periods with the last third.

Two numbers per item, because one of them can mislead:

* All-supplier change: the volume-weighted average price in the late window against the early
  window. It moves when prices move, and also when you shift volume between a cheap and a dear
  supplier.
* Like-for-like change: only suppliers that sold the item in both windows, each compared with
  itself, weighted by late-window volume (a Laspeyres-style index). This is the price moving
  with the mix held still, and it is the headline number whenever it can be computed.

When the two disagree by several points, the gap is the effect of changing who you buy from.
Neither number knows about spec, delivery terms or quality, and an item bought in different
units under one name will give nonsense. Check the series before acting on it.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .variance import item_key, unit_price

MIN_PERIODS = 4              # periods with enough invoices before an item gets a trend
MIN_PERIOD_INVOICES = 2      # invoices an item needs in a period for that period to count
MIN_SUPPLIER_INVOICES = 2    # invoices a supplier needs in a window to be compared with itself
MOVE_THRESHOLD = 5.0         # percent change that counts as rising or falling
MIX_FLAG = 5.0               # points of gap between the two measures worth flagging

_DATE = re.compile(r"^(\d{4})-(\d{2})")


@dataclass
class ItemTrend:
    item: str
    category: str
    periods: list = field(default_factory=list)   # (label, avg_price, qty, invoices), oldest first
    early_price: float = 0.0     # all-supplier average, early window
    late_price: float = 0.0      # all-supplier average, late window
    raw_change_pct: float = 0.0  # late vs early, all suppliers
    lfl_change_pct: float | None = None   # like-for-like, None when no supplier spans both windows
    change_pct: float = 0.0      # headline: like-for-like if available, else all-supplier
    basis: str = "all suppliers"
    impact_value: float = 0.0    # late-window volume x price change on the headline basis
    spend: float = 0.0           # spend across all counted periods
    early_span: str = ""         # e.g. '2025-01 to 2025-04'
    late_span: str = ""

    @property
    def mix_gap(self) -> float | None:
        """All-supplier minus like-for-like, in points. Large values mean mix is driving the average."""
        return None if self.lfl_change_pct is None else self.raw_change_pct - self.lfl_change_pct


def period_of(date: str, period: str = "month") -> str | None:
    """'2025-03-14' -> '2025-03' (month) or '2025-Q1' (quarter). None if the date is unusable."""
    m = _DATE.match((date or "").strip())
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        return None
    if period == "quarter":
        return f"{year}-Q{(month - 1) // 3 + 1}"
    return f"{year}-{month:02d}"


def has_dates(rows: list[dict]) -> bool:
    return any(period_of(r.get("date", "")) for r in rows[:50])


def _window(book_item: dict, periods: list[str]) -> dict[str, list]:
    """Aggregate supplier -> [qty, spend, invoices] over a set of periods."""
    agg: dict[str, list] = defaultdict(lambda: [0.0, 0.0, 0])
    for p in periods:
        for sup, cell in book_item[p].items():
            a = agg[sup]
            a[0] += cell[0]
            a[1] += cell[1]
            a[2] += cell[2]
    return agg


def price_trend(rows: list[dict], canon_of: dict[str, str],
                period: str = "month") -> tuple[list[ItemTrend], float]:
    """Return (items sorted by size of cost impact, spend covered by the analysis)."""
    if period not in ("month", "quarter"):
        raise ValueError("period must be 'month' or 'quarter'")
    # item -> period -> supplier -> [qty, spend, invoices]
    book: dict[str, dict[str, dict[str, list]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0])))
    cat_of: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        per = period_of(r.get("date", ""), period)
        key = item_key(r)
        qp = unit_price(r)
        if not per or not key or not qp:
            continue
        qty, price = qp
        cell = book[key][per][canon_of.get(r["supplier"], r["supplier"])]
        cell[0] += qty
        cell[1] += qty * price
        cell[2] += 1
        cat_of[key][r.get("category") or "Uncategorised"] += r["amount"]

    out: list[ItemTrend] = []
    covered = 0.0
    for key, per_map in book.items():
        counted = sorted(p for p, sups in per_map.items()
                         if sum(c[2] for c in sups.values()) >= MIN_PERIOD_INVOICES)
        if len(counted) < MIN_PERIODS:
            continue
        series = []
        for p in counted:
            qty = sum(c[0] for c in per_map[p].values())
            spend = sum(c[1] for c in per_map[p].values())
            series.append((p, spend / qty, qty, sum(c[2] for c in per_map[p].values())))
        k = max(1, len(counted) // 3)
        early, late = _window(per_map, counted[:k]), _window(per_map, counted[-k:])
        e_qty, l_qty = sum(v[0] for v in early.values()), sum(v[0] for v in late.values())
        e_price = sum(v[1] for v in early.values()) / e_qty
        l_price = sum(v[1] for v in late.values()) / l_qty
        raw = (l_price - e_price) / e_price * 100

        # like-for-like: each supplier against itself, weighted by late-window volume
        num = den = 0.0
        for sup, lv in late.items():
            ev = early.get(sup)
            if not ev or ev[2] < MIN_SUPPLIER_INVOICES or lv[2] < MIN_SUPPLIER_INVOICES:
                continue
            pe, pl = ev[1] / ev[0], lv[1] / lv[0]
            num += lv[0] * (pl - pe)
            den += lv[0] * pe
        lfl = num / den * 100 if den else None

        if lfl is not None:
            change, basis, impact = lfl, "like-for-like", num
        else:
            change, basis, impact = raw, "all suppliers", l_qty * (l_price - e_price)
        spend = sum(s[1] * s[2] for s in series)
        covered += spend
        out.append(ItemTrend(
            item=key, category=max(cat_of[key].items(), key=lambda kv: kv[1])[0],
            periods=series, early_price=e_price, late_price=l_price,
            raw_change_pct=raw, lfl_change_pct=lfl, change_pct=change, basis=basis,
            impact_value=impact, spend=spend,
            early_span=f"{counted[0]} to {counted[k - 1]}" if k > 1 else counted[0],
            late_span=f"{counted[-k]} to {counted[-1]}" if k > 1 else counted[-1]))
    out.sort(key=lambda t: -abs(t.impact_value))
    return out, covered
