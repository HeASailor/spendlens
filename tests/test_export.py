import zipfile
from xml.etree import ElementTree as ET

from spendlens.analyze import analyze
from spendlens.cli import main
from spendlens.export import export_xlsx
from spendlens.generate import generate
from spendlens.xlsx import Cell, Sheet, col_letter, write_xlsx

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read(path):
    """{sheet name: [[(value, formula), ...], ...]} using only the standard library."""
    out = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            ET.fromstring(z.read(name))              # every part is well-formed XML
        names = [s.get("name") for s in
                 ET.fromstring(z.read("xl/workbook.xml")).findall("m:sheets/m:sheet", NS)]
        for i, name in enumerate(names, 1):
            root = ET.fromstring(z.read(f"xl/worksheets/sheet{i}.xml"))
            out[name] = [
                [(c.findtext("m:is/m:t", None, NS) or c.findtext("m:v", None, NS),
                  c.findtext("m:f", None, NS)) for c in r.findall("m:c", NS)]
                for r in root.findall("m:sheetData/m:row", NS)]
    return out


def test_col_letter():
    assert [col_letter(i) for i in (0, 25, 26, 51, 52)] == ["A", "Z", "AA", "AZ", "BA"]


def test_text_is_never_a_formula_and_bad_characters_are_dropped(tmp_path):
    f = tmp_path / "t.xlsx"
    write_xlsx(str(f), [Sheet("S", [[Cell("h", "header")], [Cell('=HYPERLINK("x")')],
                                    [Cell("a<b>&\x01c")]], [10])])
    rows = read(f)["S"]
    assert rows[1][0] == ('=HYPERLINK("x")', None)
    assert rows[2][0] == ("a<b>&c", None)


def test_export_sheets_totals_and_formulas(tmp_path):
    a = analyze(generate(1500))
    f = tmp_path / "f.xlsx"
    names = export_xlsx(str(f), a)
    assert names == ["Summary", "Duplicate suppliers", "Price gaps", "Price trends",
                     "Category review", "Savings levers"]
    book = read(f)
    gaps = sum(float(r[8][0]) for r in book["Price gaps"][1:])
    assert abs(gaps - a.price_gap_total) < 0.01
    assert len(book["Category review"]) - 1 == len(a.review_all)
    assert len(book["Price trends"]) - 1 == len(a.trend_items)
    levers = book["Savings levers"]
    assert levers[1][3][1] == "B2*C2"
    n = len(a.savings_levers)
    assert levers[n + 1][3][1] == f"SUM(D2:D{n + 1})"
    assert abs(float(levers[n + 1][3][0]) - a.savings_total) < 0.01
    assert book["Summary"][-1][1][1] == f"'Savings levers'!D{n + 2}"


def test_cli_writes_contract_sheets(tmp_path):
    spend, cons = tmp_path / "s.csv", tmp_path / "c.csv"
    xl = tmp_path / "f.xlsx"
    assert main(["generate", "-o", str(spend), "-n", "800", "--contracts", str(cons)]) == 0
    assert main(["analyze", str(spend), "--contracts", str(cons), "--excel", str(xl),
                 "-o", str(tmp_path / "r.html")]) == 0
    assert {"Contract coverage", "Expiring contracts"} <= set(read(xl))


def test_export_with_only_required_columns(tmp_path):
    a = analyze([{"supplier": "A", "amount": 10.0}], classify=False)
    f = tmp_path / "m.xlsx"
    export_xlsx(str(f), a)
    assert "Savings levers" in read(f)
