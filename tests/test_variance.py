import pytest

from spendlens.analyze import analyze
from spendlens.generate import generate
from spendlens.variance import item_key, price_variance, unit_price


def rows_for(supplier, price, n=3, qty=10, item="Widget"):
    return [{"supplier": supplier, "item": item, "quantity": str(qty), "unit_price": str(price),
             "amount": qty * price} for _ in range(n)]


def test_gap_is_spend_above_best_price():
    rows = rows_for("Cheap Co", 10) + rows_for("Dear Co", 15)
    items, covered = price_variance(rows, {})
    it = items[0]
    assert it.best_supplier == "Cheap Co" and it.best_price == pytest.approx(10)
    assert it.worst_price == pytest.approx(15)
    assert it.spread_pct == pytest.approx(50)
    assert it.gap_value == pytest.approx(30 * 5)      # 3 invoices x 10 units x 5 over best
    assert covered == pytest.approx(300 + 450)


def test_prices_are_volume_weighted_per_supplier():
    rows = [{"supplier": "A", "item": "W", "quantity": "1", "unit_price": "10", "amount": 10},
            {"supplier": "A", "item": "W", "quantity": "9", "unit_price": "20", "amount": 180},
            {"supplier": "A", "item": "W", "quantity": "10", "unit_price": "19", "amount": 190}]
    rows += rows_for("B", 30, item="W")
    items, _ = price_variance(rows, {})
    a = dict((s[0], s[1]) for s in items[0].suppliers)["A"]
    assert a == pytest.approx(380 / 20)


def test_single_supplier_or_thin_evidence_is_skipped():
    assert price_variance(rows_for("Only", 10), {})[0] == []
    thin = rows_for("A", 10) + rows_for("B", 20, n=2)       # B has under 3 invoices
    assert price_variance(thin, {})[0] == []


def test_duplicate_supplier_names_are_merged_before_comparing():
    rows = rows_for("Acme Pvt Ltd", 12, n=2) + rows_for("ACME", 12, n=2) + rows_for("Other", 18)
    items, _ = price_variance(rows, {"Acme Pvt Ltd": "Acme", "ACME": "Acme", "Other": "Other"})
    assert {s[0] for s in items[0].suppliers} == {"Acme", "Other"}


def test_unit_price_falls_back_to_amount_over_quantity():
    assert unit_price({"quantity": "4", "amount": 100.0}) == (4.0, 25.0)
    assert unit_price({"quantity": "0", "amount": 100.0}) is None
    assert unit_price({"quantity": "x", "amount": 100.0}) is None


def test_item_key_prefers_item_then_cleans_description():
    assert item_key({"item": "Steel  coil"}) == "Steel coil"
    assert item_key({"description": "Corrugated carton 5-ply, 40x30 cm (each)"}) == "Corrugated Carton -Ply"


def test_analysis_adds_price_lever_only_when_columns_exist():
    rows = rows_for("Cheap Co", 10) + rows_for("Dear Co", 15)
    a = analyze(rows)
    assert a.price_gap_total == pytest.approx(150)
    assert a.savings["Price harmonisation"] == pytest.approx(150 * 0.40)
    assert "Price harmonisation" not in analyze([{"supplier": "A", "amount": 5.0}]).savings


def test_synthetic_prices_vary_by_supplier():
    a = analyze(generate(4000, 42))
    assert len(a.price_items) >= 20
    assert 0 < a.price_gap_total < 0.3 * a.total_spend
