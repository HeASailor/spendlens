"""Excel export of the findings: the full lists behind the HTML report, ready to filter."""

from __future__ import annotations

from .analyze import Analysis
from .trend import MOVE_THRESHOLD
from .xlsx import Cell, Sheet, write_xlsx


def _table(name: str, columns: list[tuple[str, str, int]], records: list) -> Sheet:
    """columns: (header, style, width); records: one list of values per row."""
    rows = [[Cell(h, "header") for h, _, _ in columns]]
    rows += [[Cell(v, columns[i][1]) for i, v in enumerate(rec)] for rec in records]
    return Sheet(name, rows, [w for _, _, w in columns])


def _savings(a: Analysis) -> Sheet:
    rows = [[Cell(h, "header") for h in ("Lever", "Spend it applies to", "Assumption", "Saving")]]
    for name, base, rate in a.savings_levers:
        n = len(rows) + 1
        rows.append([Cell(name), Cell(base, "money"), Cell(rate, "input"),
                     Cell(base * rate, "money", f"B{n}*C{n}")])
    last = len(rows)
    rows.append([Cell("Total", "bold"), Cell(), Cell(),
                 Cell(a.savings_total, "total", f"SUM(D2:D{last})")])
    rows.append([])
    rows.append([Cell("Change the shaded assumptions to your own benchmarks. Levers can overlap, "
                      "so read the total as an upper-end sizing, not a forecast.")])
    # not a filterable table: sorting would pull the total into the data
    return Sheet("Savings levers", rows, [36, 22, 14, 18], table=False)


def _summary(a: Analysis, title: str, levers: int) -> Sheet:
    rows = [[Cell("Measure", "header"), Cell("Value", "header")]]

    def add(label, value, style="text", formula=""):
        rows.append([Cell(label), Cell(value, style, formula)])

    add("Report", title)
    add("Invoices", a.rows, "int")
    add("Total spend", a.total_spend, "money")
    add("Supplier records", a.supplier_records, "int")
    add("Unique suppliers (after merging duplicates)", a.unique_suppliers, "int")
    add("Suppliers making up 80% of spend", a.pareto_suppliers_80, "int")
    add("Tail spend", a.tail_spend, "money")
    add("Spend with no PO", a.maverick_spend, "money")
    add("Spend with no PO, share", a.maverick_pct / 100, "pct")
    if a.classification:
        add("Spend with a category, share", a.classified_pct / 100, "pct")
    if a.price_items:
        add("Paid above best price already achieved", a.price_gap_total, "money")
    if a.contracts:
        add("Spend under a live contract, share", a.contracts.covered_pct / 100, "pct")
    add("Savings opportunity (illustrative)", a.savings_total, "money",
        f"'Savings levers'!D{levers + 2}")
    return Sheet("Summary", rows, [46, 24], table=False)


def sheets(a: Analysis, title: str = "Spend Analysis") -> list[Sheet]:
    out = [_summary(a, title, len(a.savings_levers))]

    out.append(_table(
        "Duplicate suppliers",
        [("Merged supplier", "text", 32), ("Name as in your file", "text", 40),
         ("Cluster spend", "money", 18)],
        [[canon, variant, spend] for canon, variants, spend in a.duplicate_clusters
         for variant in variants]))

    out.append(_table(
        "Price gaps",
        [("Item", "text", 32), ("Category", "text", 22), ("Supplier", "text", 30),
         ("Average unit price", "money", 20), ("Best unit price", "money", 18),
         ("Above best", "pct", 13), ("Quantity", "dec", 12), ("Invoices", "int", 10),
         ("Gap value", "money", 16)],
        [[i.item, i.category, sup, price, i.best_price, price / i.best_price - 1, qty, count,
          qty * (price - i.best_price)]
         for i in a.price_items for sup, price, qty, count in i.suppliers]))

    out.append(_table(
        "Price trends",
        [("Item", "text", 32), ("Category", "text", 22), ("Direction", "text", 11),
         ("Change", "pct", 11), ("Basis", "text", 15), ("All-supplier change", "pct", 20),
         ("Early window", "text", 20), ("Early price", "money", 15), ("Late window", "text", 20),
         ("Late price", "money", 15), ("Cost impact", "money", 15)],
        [[t.item, t.category,
          "Up" if t.change_pct >= MOVE_THRESHOLD else "Down" if t.change_pct <= -MOVE_THRESHOLD else "Flat",
          t.change_pct / 100, t.basis, t.raw_change_pct / 100, t.early_span, t.early_price,
          t.late_span, t.late_price, t.impact_value] for t in a.trend_items]))

    if a.classification:
        out.append(_table(
            "Category review",
            [("Invoice", "text", 16), ("Supplier", "text", 30), ("Item", "text", 30),
             ("Description", "text", 44), ("Guessed category", "text", 22),
             ("How", "text", 10), ("Confidence", "dec", 12), ("Amount", "money", 15)],
            [[r.get("invoice_id", ""), r["supplier"], r.get("item", ""), r.get("description", ""),
              r["category"], r["category_source"], r["category_conf"], r["amount"]]
             for r in a.review_all]))

    c = a.contracts
    if c:
        out.append(_table(
            "Contract coverage",
            [("Supplier", "text", 32), ("Total spend", "money", 16), ("Covered", "money", 16),
             ("Outside contract dates", "money", 24), ("No contract", "money", 16),
             ("Undated", "money", 12), ("Covered share", "pct", 16)],
            [[s.supplier, s.total, s.covered, s.outside, s.none, s.undated, s.covered / s.total]
             for s in c.suppliers]))
        out.append(_table(
            "Expiring contracts",
            [("Supplier", "text", 32), ("Contract ID", "text", 16), ("Category", "text", 22),
             ("End date", "text", 13), ("Days left", "int", 11), ("Spend under it", "money", 18)],
            [[sup, k.contract_id, k.category, k.end.isoformat(), days, spend]
             for k, sup, days, spend in c.expiring]))
        if c.unmatched:
            out.append(_table(
                "Unmatched contracts",
                [("Supplier in contracts file", "text", 36), ("Contract ID", "text", 16),
                 ("Start date", "text", 13), ("End date", "text", 13)],
                [[k.supplier, k.contract_id, k.start.isoformat(), k.end.isoformat()]
                 for k in c.unmatched]))

    out.append(_savings(a))
    return out


def export_xlsx(path: str, a: Analysis, title: str = "Spend Analysis") -> list[str]:
    """Write the workbook and return the sheet names."""
    book = sheets(a, title)
    write_xlsx(path, book)
    return [s.name for s in book]
