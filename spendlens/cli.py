"""Command line interface: spendlens generate | analyze | classify | taxonomy."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .analyze import analyze, load
from .generate import write_csv
from . import report
from .report import money, render
from .trend import MOVE_THRESHOLD


def _taxonomy(args):
    """Resolve --taxonomy into (merged taxonomy, label), or (None, "") when not given."""
    if not args.taxonomy:
        return None, ""
    from .classify import TAXONOMY
    from .taxonomy import describe, load_taxonomy, merge_taxonomy
    custom = load_taxonomy(args.taxonomy)
    merged = merge_taxonomy(TAXONOMY, custom, args.taxonomy_mode)
    return merged, describe(custom, merged, args.taxonomy_mode)


def _taxonomy_export(args) -> int:
    from .classify import TAXONOMY
    from .taxonomy import write_csv as write_taxonomy
    n = write_taxonomy(args.out, TAXONOMY)
    print(f"Wrote {n} keywords across {len(TAXONOMY)} categories to {args.out}")
    print("Edit it, then run: spendlens analyze spend.csv --taxonomy " + args.out)
    return 0


def _classify(args) -> int:
    import csv
    from .classify import classify_rows
    try:
        rows = load(args.csv)
        taxonomy, label = _taxonomy(args)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    stats = classify_rows(rows, overwrite=args.overwrite, min_confidence=args.min_confidence,
                          taxonomy=taxonomy)
    cols = list(rows[0].keys())
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    for k, label in (("given", "kept as provided"), ("keyword", "classified by keywords"),
                     ("supplier", "inferred from supplier history"), ("none", "left unclassified")):
        print(f"{stats[k]['rows']:>7,} rows ({stats[k]['rows'] / n * 100:4.1f}%)  {label}")
    if label:
        print(f"Taxonomy     {label}")
    print(f"Wrote {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="spendlens", description="Procurement spend analytics in one command.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="create a synthetic spend CSV")
    g.add_argument("-o", "--out", default="spend.csv")
    g.add_argument("-n", "--rows", type=int, default=4000)
    g.add_argument("--seed", type=int, default=42)

    a = sub.add_parser("analyze", help="analyze a spend CSV and write an HTML report")
    a.add_argument("csv")
    a.add_argument("-o", "--out", default="report.html")
    a.add_argument("--title", default="Spend Analysis")
    a.add_argument("--units", choices=["intl", "indian"], default="intl",
                   help="number format: K/M/B or Lakh/Crore (default: intl)")
    a.add_argument("--fuzzy", type=float, default=0.88, help="supplier-name match threshold (0-1)")

    a.add_argument("--no-classify", action="store_true", help="skip category auto-classification")
    a.add_argument("--min-confidence", type=float, default=0.0,
                   help="ignore keyword guesses below this confidence (0-1)")
    a.add_argument("--taxonomy", metavar="FILE", help="your own category list (.csv or .json)")
    a.add_argument("--taxonomy-mode", choices=["extend", "replace"], default="extend",
                   help="add to the built-in categories (default) or use only your file")
    a.add_argument("--trend-period", choices=["month", "quarter"], default="month",
                   help="period for the price trend view (default: month)")

    c = sub.add_parser("classify", help="fill missing categories and write a new CSV")
    c.add_argument("csv")
    c.add_argument("-o", "--out", default="classified.csv")
    c.add_argument("--min-confidence", type=float, default=0.0)
    c.add_argument("--overwrite", action="store_true", help="re-classify rows that already have a category")
    c.add_argument("--taxonomy", metavar="FILE", help="your own category list (.csv or .json)")
    c.add_argument("--taxonomy-mode", choices=["extend", "replace"], default="extend")

    t = sub.add_parser("taxonomy", help="write the built-in category list as a CSV you can edit")
    t.add_argument("-o", "--out", default="taxonomy.csv")

    args = p.parse_args(argv)

    if args.cmd == "generate":
        n = write_csv(args.out, args.rows, args.seed)
        print(f"Wrote {n:,} rows to {args.out}")
        return 0

    if args.cmd == "classify":
        return _classify(args)

    if args.cmd == "taxonomy":
        return _taxonomy_export(args)

    try:
        rows = load(args.csv)
        taxonomy, label = _taxonomy(args)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not rows:
        print("error: no valid rows found", file=sys.stderr)
        return 1

    report.UNITS["mode"] = args.units
    res = analyze(rows, fuzzy_threshold=args.fuzzy, classify=not args.no_classify,
                  min_confidence=args.min_confidence, taxonomy=taxonomy, taxonomy_label=label,
                  trend_period=args.trend_period)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(render(res, args.title))

    print(f"Spend        {money(res.total_spend)} across {res.rows:,} invoices")
    print(f"Suppliers    {res.unique_suppliers:,} unique ({res.supplier_records:,} records)")
    print(f"Maverick     {res.maverick_pct:.1f}% of spend has no PO")
    if res.classification:
        print(f"Categories   {res.classified_pct:.0f}% of spend classified "
              f"({res.auto_classified_pct:.0f}% filled in by SpendLens)")
    if res.price_items:
        print(f"Price gaps   {money(res.price_gap_total)} above best price paid, "
              f"{len(res.price_items)} items compared")
    if res.trend_items:
        up = sum(1 for t in res.trend_items if t.change_pct >= MOVE_THRESHOLD)
        down = sum(1 for t in res.trend_items if t.change_pct <= -MOVE_THRESHOLD)
        print(f"Price trend  {up} items up, {down} down by {MOVE_THRESHOLD:.0f}%+ "
              f"({len(res.trend_items)} items, by {res.trend_period})")
    print(f"Savings      ~{money(res.savings_total)} identified")
    print(f"Report       {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
