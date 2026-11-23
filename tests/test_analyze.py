import csv

import pytest

from spendlens.analyze import analyze, cluster_suppliers, load, normalize_name
from spendlens.cli import main
from spendlens.generate import generate


def test_normalize_strips_legal_suffixes():
    assert normalize_name("ACME Packaging Pvt. Ltd.") == "acme packaging"
    assert normalize_name("Acme  Packaging Private Limited") == "acme packaging"


def test_cluster_merges_variants_but_not_different_suppliers():
    names = ["Acme Packaging Pvt Ltd", "ACME PACKAGING", "Acme Packaging Inc",
             "Titan Metals", "Titan Metal Ltd", "Orbit Films"]
    groups = [sorted(g) for g in cluster_suppliers(names)]
    assert any(len(g) == 3 and "ACME PACKAGING" in g for g in groups)
    assert any(len(g) == 2 and "Titan Metals" in g for g in groups)
    assert ["Orbit Films"] in groups


def test_totals_and_maverick():
    rows = [
        {"supplier": "A", "amount": 100.0, "po_number": "PO-1", "category": "X", "date": "2025-01-05"},
        {"supplier": "B", "amount": 300.0, "po_number": "", "category": "X", "date": "2025-02-05"},
    ]
    a = analyze(rows)
    assert a.total_spend == 400.0
    assert a.maverick_spend == 300.0
    assert a.maverick_pct == pytest.approx(75.0)
    assert [m for m, _ in a.monthly] == ["2025-01", "2025-02"]


def test_hhi_single_supplier_is_10000():
    rows = [{"supplier": "Solo", "amount": 50.0, "category": "C"}]
    assert analyze(rows).hhi_by_category["C"] == 10000


def test_load_rejects_missing_columns(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("vendor,total\nA,1\n")
    with pytest.raises(ValueError):
        load(str(f))


def test_load_skips_bad_amounts(tmp_path):
    f = tmp_path / "x.csv"
    with open(f, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["supplier", "amount"])
        w.writerows([["A", "1,000.50"], ["B", "oops"], ["C", "-5"], ["", "10"]])
    rows = load(str(f))
    assert len(rows) == 1 and rows[0]["amount"] == 1000.5


def test_generator_is_deterministic():
    assert generate(200, seed=7) == generate(200, seed=7)


def test_end_to_end_cli(tmp_path):
    csv_path, out = tmp_path / "s.csv", tmp_path / "r.html"
    assert main(["generate", "-o", str(csv_path), "-n", "1500"]) == 0
    assert main(["analyze", str(csv_path), "-o", str(out)]) == 0
    html = out.read_text()
    assert "<svg" in html and "Savings opportunity" in html
    a = analyze(load(str(csv_path)))
    assert a.unique_suppliers < a.supplier_records  # duplicates were detected
    assert a.savings_total > 0


def test_numbered_vendors_are_not_merged():
    names = ["Packaging Vendor 127-12", "Packaging Vendor 130-6", "Packaging Vendor 127-12 Ltd"]
    groups = [sorted(g) for g in cluster_suppliers(names)]
    assert ["Packaging Vendor 130-6"] in groups
    assert any(len(g) == 2 for g in groups)
