"""Command line interface: spendlens generate | analyze."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .analyze import analyze, load
from .generate import write_csv
from . import report
from .report import money, render


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

    args = p.parse_args(argv)

    if args.cmd == "generate":
        n = write_csv(args.out, args.rows, args.seed)
        print(f"Wrote {n:,} rows to {args.out}")
        return 0

    try:
        rows = load(args.csv)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not rows:
        print("error: no valid rows found", file=sys.stderr)
        return 1

    report.UNITS["mode"] = args.units
    res = analyze(rows, fuzzy_threshold=args.fuzzy)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(render(res, args.title))

    print(f"Spend        {money(res.total_spend)} across {res.rows:,} invoices")
    print(f"Suppliers    {res.unique_suppliers:,} unique ({res.supplier_records:,} records)")
    print(f"Maverick     {res.maverick_pct:.1f}% of spend has no PO")
    print(f"Savings      ~{money(res.savings_total)} identified")
    print(f"Report       {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
