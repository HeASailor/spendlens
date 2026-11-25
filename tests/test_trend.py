import pytest

from spendlens.analyze import analyze
from spendlens.cli import main
from spendlens.generate import ITEM_DRIFT, generate
from spendlens.trend import MIN_PERIODS, period_of, price_trend


def month_rows(supplier, prices, item="Widget", n=2, qty=10, start_month=1):
    """n invoices per month for each price in `prices` (one price per month)."""
    rows = []
    for i, price in enumerate(prices):
        for d in range(n):
            rows.append({"supplier": supplier, "item": item, "quantity": str(qty),
                         "unit_price": str(price), "amount": qty * price,
                         "date": f"2025-{start_month + i:02d}-{10 + d:02d}"})
    return rows


def test_period_of_handles_months_quarters_and_junk():
    assert period_of("2025-03-14") == "2025-03"
    assert period_of("2025-03-14", "quarter") == "2025-Q1"
    assert period_of("2025-12-01", "quarter") == "2025-Q4"
    for bad in ("", "03/14/2025", "2025-13-01", "soon", None):
        assert period_of(bad) is None


def test_steady_rise_is_found_and_ranked_by_cost_impact():
    rows = month_rows("A", [10] * 4 + [11] * 4 + [13] * 4)     # 20 units a month
    items, covered = price_trend(rows, {})
    t = items[0]
    assert t.change_pct == pytest.approx(30)               # 10 -> 13 between first and last third
    assert t.basis == "like-for-like" and t.lfl_change_pct == pytest.approx(30)
    assert (t.early_span, t.late_span) == ("2025-01 to 2025-04", "2025-09 to 2025-12")
    assert t.impact_value == pytest.approx(80 * 3)         # 80 units in the late window, 3 dearer each
    assert len(t.periods) == 12 and covered == pytest.approx(sum(p[1] * p[2] for p in t.periods))


def test_mix_shift_is_not_mistaken_for_a_price_rise():
    # Each supplier's own price never moves. Volume swings from the cheap one to the dear one.
    cheap = month_rows("Cheap", [10] * 8, n=4) + month_rows("Cheap", [10] * 4, n=1, start_month=9)
    dear = month_rows("Dear", [20] * 4, n=1) + month_rows("Dear", [20] * 8, n=4, start_month=5)
    items, _ = price_trend(cheap + dear, {})
    t = items[0]
    assert t.raw_change_pct > 20                           # the average climbs
    assert t.lfl_change_pct == pytest.approx(0, abs=1e-9)  # but no supplier raised its price
    assert t.change_pct == pytest.approx(0, abs=1e-9)
    assert t.mix_gap > 20


def test_falls_back_to_all_supplier_change_when_no_supplier_spans_both_windows():
    rows = month_rows("Early Co", [10] * 6, n=2) + month_rows("Late Co", [14] * 6, n=2, start_month=7)
    t = price_trend(rows, {})[0][0]
    assert t.lfl_change_pct is None and t.basis == "all suppliers"
    assert t.change_pct == pytest.approx(40)


def test_thin_data_is_skipped():
    few_periods = month_rows("A", [10, 11, 12])
    assert len(few_periods) // 2 < MIN_PERIODS and price_trend(few_periods, {})[0] == []
    one_invoice_a_month = month_rows("A", [10] * 12, n=1)
    assert price_trend(one_invoice_a_month, {})[0] == []


def test_undated_or_unpriced_rows_are_ignored():
    rows = month_rows("A", [10] * 6)
    rows += [{"supplier": "A", "item": "Widget", "amount": 5.0, "quantity": "1", "date": "sometime"},
             {"supplier": "A", "item": "Widget", "amount": 5.0, "date": "2025-02-02"}]
    items, _ = price_trend(rows, {})
    assert items and sum(p[3] for p in items[0].periods) == 12


def test_duplicate_supplier_names_are_merged_before_comparing():
    rows = month_rows("Acme Pvt Ltd", [10] * 6) + month_rows("ACME", [12] * 6, start_month=7)
    t = price_trend(rows, {"Acme Pvt Ltd": "Acme", "ACME": "Acme"})[0][0]
    assert t.lfl_change_pct == pytest.approx(20)           # one supplier, compared with itself


def test_quarter_grouping():
    rows = []
    for q, price in enumerate([10, 11, 12, 13]):
        rows += month_rows("A", [price] * 3, n=1, start_month=q * 3 + 1)
    items, _ = price_trend(rows, {}, period="quarter")
    assert [p[0] for p in items[0].periods] == ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
    with pytest.raises(ValueError):
        price_trend(rows, {}, period="week")


def test_analysis_needs_dates_and_prices_for_a_trend():
    assert analyze(month_rows("A", [10] * 6)).trend_items
    undated = [{k: v for k, v in r.items() if k != "date"} for r in month_rows("A", [10] * 6)]
    assert analyze(undated).trend_items == []
    assert analyze([{"supplier": "A", "amount": 5.0, "date": "2025-01-01"}]).trend_items == []


def test_synthetic_demo_recovers_the_planted_direction():
    a = analyze(generate(4000, 42))
    by_item = {t.item: t for t in a.trend_items}
    assert len(by_item) >= 25
    for item in ("Copper wire rod", "Cold rolled steel coil", "Corrugated carton 5-ply"):
        assert by_item[item].change_pct > 5
    for item in ("Container shipping 40ft", "Laptop business class"):
        assert by_item[item].change_pct < -3
    # a rise must never be reported where the planted drift is a fall, and vice versa
    for item, drift in ITEM_DRIFT.items():
        if abs(drift) >= 0.07 and item in by_item:
            assert (by_item[item].change_pct > 0) == (drift > 0), item


def test_cli_prints_trend_and_report_has_the_card(tmp_path, capsys):
    csv_path, out = str(tmp_path / "s.csv"), str(tmp_path / "r.html")
    main(["generate", "-o", csv_path, "-n", "2500"])
    assert main(["analyze", csv_path, "-o", out, "--trend-period", "quarter"]) == 0
    assert "Price trend" in capsys.readouterr().out
    html = open(out, encoding="utf-8").read()
    assert "Price trend per item" in html and "by quarter" in html
