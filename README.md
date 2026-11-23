# SpendLens

[![CI](https://github.com/HeASailor/spendlens/actions/workflows/ci.yml/badge.svg)](https://github.com/HeASailor/spendlens/actions/workflows/ci.yml) ![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white) ![Dependencies](https://img.shields.io/badge/dependencies-none-success) ![License: MIT](https://img.shields.io/badge/license-MIT-blue)

**Procurement spend analytics in one command.** Point it at a spend CSV and get a single, self-contained HTML report: duplicate suppliers, Pareto and tail spend, maverick (no-PO) spend, category concentration and an estimated savings opportunity.

No dependencies. No cloud. No data leaves your machine.

![SpendLens report](docs/screenshot.png)

## Why

Every Source-to-Pay engagement starts the same way: someone exports a year of invoices, and the first week goes into cleaning supplier names and building the same five pivot tables. SpendLens automates that first pass so the conversation can start from the findings.

## Quick start

```bash
git clone https://github.com/HeASailor/spendlens && cd spendlens
pip install -e .

spendlens generate -o spend.csv            # synthetic data, or use your own
spendlens analyze spend.csv -o report.html
open report.html
```

Prefer not to install? `python -m spendlens analyze spend.csv` works from the repo root.

## Input format

| column | required | notes |
|---|---|---|
| `supplier` | yes | raw supplier name as it appears in the ERP |
| `amount` | yes | invoice amount, any currency (commas are fine) |
| `category` | no | enables category and concentration views |
| `date` | no | `YYYY-MM-DD`, enables the monthly trend |
| `po_number` | no | blank means no PO, which feeds maverick spend |
| `payment_terms_days` | no | enables the short-terms metric |

Rows with a missing supplier or a non-positive or unparseable amount are skipped.

## What it computes

- **Duplicate suppliers.** Names are normalised (case, punctuation, legal suffixes like *Pvt Ltd / LLC / GmbH*) and then fuzzy-matched. "ACME Packaging Pvt. Ltd." and "Acme Packaging Private Limited" become one supplier. Names that differ in their numbers are never merged, so "Vendor 127" and "Vendor 130" stay separate.
- **Pareto and tail spend.** How many suppliers make up 80% of spend, and how many sit in the bottom 20%.
- **Maverick spend.** Share of spend with no PO.
- **Concentration.** Herfindahl-Hirschman Index per category, so you can see where you depend on one or two suppliers.
- **Savings opportunity.** Tail consolidation, maverick-to-PO and duplicate-merge levers, each with a configurable assumption.

> The savings figures are a **sizing exercise, not a forecast**. Defaults are 8% on tail spend, 5% on maverick spend and 3% on merged duplicates. Replace them with your own benchmarks via `analyze(rows, assumptions={...})`.

## CLI

```
spendlens generate [-o spend.csv] [-n 4000] [--seed 42]
spendlens analyze  spend.csv [-o report.html] [--title "..."] [--units intl|indian] [--fuzzy 0.88]
```

`--units indian` formats numbers as Lakh and Crore.

## Use as a library

```python
from spendlens.analyze import load, analyze

a = analyze(load("spend.csv"))
print(a.unique_suppliers, a.maverick_pct, a.savings_total)
for canonical, variants, spend in a.duplicate_clusters[:5]:
    print(canonical, variants, spend)
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Roadmap

- [ ] Category auto-classification from supplier and description text
- [ ] Price-variance analysis across suppliers for the same item
- [ ] Contract coverage view (spend vs. active contracts)
- [ ] Excel export alongside HTML

## About the data

`docs/sample_spend.csv` is fully synthetic and seeded, so the screenshot is reproducible. It contains no real supplier, client or company data.

## License

MIT
