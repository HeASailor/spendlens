import csv
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pytest

from hand_labelled import CASES
from spendlens.analyze import analyze, load
from spendlens.classify import classify_rows, classify_text
from spendlens.cli import main
from spendlens.generate import generate


def test_hand_labelled_set_is_mostly_right_and_abstains_when_unsure():
    hits = sum(classify_text(t)[0] == exp for t, exp in CASES)
    assert hits / len(CASES) >= 0.9
    for text, exp in CASES:
        if exp is None:
            assert classify_text(text)[0] is None, text


def test_ties_and_weak_evidence_abstain():
    assert classify_text("tool")[0] is None            # one weak hit
    assert classify_text("")[0] is None


def test_given_category_is_kept_unless_overwrite():
    rows = [{"supplier": "X Freight", "amount": 10.0, "category": "Marketing", "description": "freight"}]
    classify_rows(rows)
    assert rows[0]["category"] == "Marketing" and rows[0]["category_source"] == "given"
    classify_rows(rows, overwrite=True)
    assert rows[0]["category"] == "Logistics" and rows[0]["category_source"] == "keyword"


def test_supplier_history_fills_rows_with_no_text():
    rows = [
        {"supplier": "Zeta Co", "amount": 900.0, "category": "MRO"},
        {"supplier": "Zeta Co", "amount": 100.0, "category": ""},
        {"supplier": "Nobody Ltd", "amount": 50.0, "category": ""},
    ]
    stats = classify_rows(rows)
    assert rows[1]["category"] == "MRO" and rows[1]["category_source"] == "supplier"
    assert rows[2]["category"] == "" and rows[2]["category_source"] == "none"
    assert stats["none"]["rows"] == 1 and stats["supplier"]["rows"] == 1


def test_supplier_history_needs_a_clear_majority():
    rows = [
        {"supplier": "Split Co", "amount": 100.0, "category": "MRO"},
        {"supplier": "Split Co", "amount": 100.0, "category": "Facilities"},
        {"supplier": "Split Co", "amount": 10.0, "category": ""},
    ]
    classify_rows(rows)
    assert rows[2]["category"] == ""


def test_min_confidence_filters_keyword_guesses():
    rows = [{"supplier": "S", "amount": 1.0, "description": "bearing"}]
    classify_rows(rows, min_confidence=0.99)
    assert rows[0]["category"] == ""


def test_synthetic_blanks_are_recovered_without_wrong_guesses():
    rows = generate(2000, 3)
    truth = [r["_true_category"] for r in rows]
    blank = [i for i, r in enumerate(rows) if not r["category"]]
    classify_rows(rows)
    filled = [i for i in blank if rows[i]["category"]]
    assert len(filled) / len(blank) > 0.95
    assert sum(rows[i]["category"] == truth[i] for i in filled) / len(filled) > 0.97


def test_analyze_reports_coverage():
    rows = [{"supplier": "Acme Freight", "amount": 100.0, "category": "", "description": "freight"},
            {"supplier": "Q", "amount": 100.0, "category": "MRO"}]
    a = analyze(rows)
    assert a.classified_pct == pytest.approx(100.0)
    assert a.auto_classified_pct == pytest.approx(50.0)
    assert dict(a.categories)["Logistics"] == 100.0
    assert analyze(rows, classify=False).classification == {}


def test_cli_classify_writes_csv(tmp_path):
    src, out = tmp_path / "in.csv", tmp_path / "out.csv"
    src.write_text("supplier,amount,category,description\n"
                   "Acme,100,,corrugated carton\nBeta,50,MRO,anything\n")
    assert main(["classify", str(src), "-o", str(out)]) == 0
    got = list(csv.DictReader(open(out)))
    assert got[0]["category"] == "Packaging" and got[0]["category_source"] == "keyword"
    assert got[1]["category"] == "MRO" and got[1]["category_source"] == "given"
    assert len(load(str(out))) == 2
