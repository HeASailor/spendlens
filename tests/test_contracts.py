import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from spendlens.analyze import analyze
from spendlens.cli import main
from spendlens.contracts import (COVERED, NONE, OUTSIDE, UNDATED, Contract, load_contracts,
                                 parse_date)


def row(supplier, amount, day, category="Packaging"):
    return {"supplier": supplier, "amount": float(amount), "date": day, "category": category}


def contract(supplier, start, end, category="", cid=""):
    return Contract(supplier, date.fromisoformat(start), date.fromisoformat(end), category, cid)


def test_statuses_and_boundaries():
    rows = [row("Acme Ltd", 10, "2025-01-01"), row("Acme Ltd", 20, "2025-06-30"),
            row("Acme Ltd", 40, "2025-07-01"), row("Acme Ltd", 80, ""),
            row("Other", 160, "2025-03-01")]
    a = analyze(rows, contracts=[contract("ACME Private Limited", "2025-01-01", "2025-06-30")])
    assert [r["contract_status"] for r in rows] == [COVERED, COVERED, OUTSIDE, UNDATED, NONE]
    assert a.contracts.spend == {COVERED: 30, OUTSIDE: 40, NONE: 160, UNDATED: 80}
    assert a.contracts.covered_pct == pytest.approx(30 / 310 * 100)
    assert a.contracts.suppliers[0].supplier == "Other"


def test_category_limits_scope():
    rows = [row("Acme", 10, "2025-02-01", "Packaging"), row("Acme", 10, "2025-02-01", "MRO")]
    analyze(rows, contracts=[contract("Acme", "2025-01-01", "2025-12-31", "packaging")])
    assert [r["contract_status"] for r in rows] == [COVERED, NONE]


def test_contract_names_do_not_change_supplier_merging():
    rows = [row("Acme", 10, "2025-02-01"), row("Zenith", 10, "2025-02-01")]
    a = analyze(rows, contracts=[contract("Nobody Inc", "2025-01-01", "2025-12-31")])
    assert a.unique_suppliers == 2
    assert [c.supplier for c in a.contracts.unmatched] == ["Nobody Inc"]


def test_expiring_window_and_renewals():
    rows = [row(s, 100, "2025-12-31") for s in ("Soon", "Later", "Renewed", "Lapsed")]
    a = analyze(rows, contracts=[
        contract("Soon", "2025-01-01", "2026-02-28", cid="S"),
        contract("Later", "2025-01-01", "2026-06-30", cid="L"),
        contract("Renewed", "2025-01-01", "2026-01-31", cid="R1"),
        contract("Renewed", "2026-02-01", "2027-01-31", cid="R2"),
        contract("Lapsed", "2024-01-01", "2025-06-30", cid="X"),
    ])
    assert [(e[0].contract_id, e[2], e[3]) for e in a.contracts.expiring] == [("S", 59, 100)]


def test_overlapping_contracts_count_spend_once():
    rows = [row("Acme", 100, "2025-12-31")]
    a = analyze(rows, contracts=[contract("Acme", "2025-01-01", "2026-01-31"),
                                 contract("Acme", "2025-06-01", "2027-01-31")])
    assert a.contracts.spend[COVERED] == 100


def test_coverage_does_not_change_savings():
    rows = [row("Acme", 100, "2025-02-01")]
    with_c = analyze([dict(r) for r in rows],
                     contracts=[contract("Acme", "2025-01-01", "2025-12-31")])
    assert with_c.savings == analyze(rows).savings


def test_parse_date():
    assert parse_date("2025-3-4") == date(2025, 3, 4)
    assert parse_date("2025-03-04 10:30") == date(2025, 3, 4)
    for bad in ("", "2025-03", "04/03/2025", "2025-02-30", "2025-03-041"):
        assert parse_date(bad) is None


@pytest.mark.parametrize("body,message", [
    ("supplier,start_date\nA,2025-01-01\n", "end_date"),
    ("supplier,start_date,end_date\n,2025-01-01,2025-02-01\n", "line 2"),
    ("supplier,start_date,end_date\nA,01/01/2025,2025-02-01\n", "line 2"),
    ("supplier,start_date,end_date\nA,2025-03-01,2025-02-01\n", "before"),
    ("supplier,start_date,end_date\n", "no contracts"),
])
def test_load_errors_name_the_problem(tmp_path, body, message):
    f = tmp_path / "c.csv"
    f.write_text(body)
    with pytest.raises(ValueError, match=message):
        load_contracts(str(f))


def test_cli_end_to_end(tmp_path, capsys):
    spend, cons, out = tmp_path / "s.csv", tmp_path / "c.csv", tmp_path / "r.html"
    assert main(["generate", "-o", str(spend), "-n", "800", "--contracts", str(cons)]) == 0
    assert main(["analyze", str(spend), "--contracts", str(cons), "-o", str(out)]) == 0
    assert "Contract coverage" in out.read_text()
    assert "of spend covered" in capsys.readouterr().out
    assert main(["analyze", str(spend), "--contracts", str(tmp_path / "missing.csv")]) == 1


def test_generator_is_the_same_in_every_process(tmp_path):
    root = Path(__file__).resolve().parents[1]
    outputs = []
    for seed in ("1", "2"):
        f = tmp_path / f"s{seed}.csv"
        subprocess.run([sys.executable, "-m", "spendlens", "generate", "-o", str(f), "-n", "300"],
                       cwd=root, env={**os.environ, "PYTHONHASHSEED": seed}, check=True,
                       capture_output=True)
        outputs.append(f.read_bytes())
    assert outputs[0] == outputs[1]
