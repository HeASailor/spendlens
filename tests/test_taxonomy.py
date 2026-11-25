import json

import pytest

from spendlens.analyze import analyze
from spendlens.classify import TAXONOMY, classify_rows, classify_text
from spendlens.cli import main
from spendlens.generate import generate
from spendlens.taxonomy import describe, load_taxonomy, merge_taxonomy, write_csv


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def blank_categories(path):
    import csv
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["category"] = ""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def test_csv_loads_with_default_weight_comments_and_blank_lines(tmp_path):
    p = write(tmp_path, "t.csv",
              "category,keyword,weight\n# a note\nCivil,Cement,4\nCivil,rebar,\n\nPackaging,gunny bag,2\n")
    assert load_taxonomy(p) == {"Civil": {"cement": 4, "rebar": 3}, "Packaging": {"gunny bag": 2}}


def test_json_accepts_lists_and_weight_maps(tmp_path):
    p = write(tmp_path, "t.json", json.dumps({"Civil": ["cement", "rebar"], "Packaging": {"gunny bag": 2}}))
    assert load_taxonomy(p) == {"Civil": {"cement": 3, "rebar": 3}, "Packaging": {"gunny bag": 2}}


@pytest.mark.parametrize("text, msg", [
    ("category,keyword,weight\nCivil,cement,9\n", "between 1 and 5"),
    ("category,keyword,weight\nCivil,cement,heavy\n", "not a number"),
    ("category,keyword,weight\n,cement,3\n", "category name is empty"),
    ("name,word\nCivil,cement\n", "'category' and 'keyword'"),
    ("category,keyword,weight\n", "no keywords"),
])
def test_bad_csv_gives_a_clear_error(tmp_path, text, msg):
    with pytest.raises(ValueError, match=msg):
        load_taxonomy(write(tmp_path, "t.csv", text))


def test_error_names_the_line(tmp_path):
    p = write(tmp_path, "t.csv", "category,keyword,weight\nCivil,cement,3\nCivil,rebar,9\n")
    with pytest.raises(ValueError, match="line 3"):
        load_taxonomy(p)


def test_unknown_file_type_is_rejected(tmp_path):
    with pytest.raises(ValueError, match=".csv or .json"):
        load_taxonomy(write(tmp_path, "t.txt", "x"))


def test_extend_merges_case_insensitively_and_overrides_weights():
    merged = merge_taxonomy(TAXONOMY, {"packaging": {"gunny bag": 2, "label": 5}, "Civil": {"cement": 3}})
    assert "packaging" not in merged and merged["Packaging"]["gunny bag"] == 2
    assert merged["Packaging"]["label"] == 5            # custom weight wins
    assert merged["Packaging"]["carton"] == TAXONOMY["Packaging"]["carton"]   # built-in kept
    assert merged["Civil"] == {"cement": 3}
    assert "label" in TAXONOMY["Packaging"] and TAXONOMY["Packaging"]["label"] == 2   # input untouched


def test_replace_uses_only_the_custom_list():
    merged = merge_taxonomy(TAXONOMY, {"Civil": {"cement": 3}}, mode="replace")
    assert merged == {"Civil": {"cement": 3}}
    with pytest.raises(ValueError):
        merge_taxonomy(TAXONOMY, {"Civil": {"cement": 3}}, mode="blend")


def test_custom_keyword_classifies_text_the_builtin_list_misses():
    text = "OPC cement 53 grade bags"
    assert classify_text(text)[0] is None
    tax = merge_taxonomy(TAXONOMY, {"Construction": {"cement": 3, "opc": 2}})
    assert classify_text(text, tax)[0] == "Construction"


def test_given_categories_are_never_overwritten_by_a_custom_list():
    tax = merge_taxonomy(TAXONOMY, {"Construction": {"cement": 5}})
    rows = [{"supplier": "A", "item": "cement", "amount": 10.0, "category": "Raw Materials"},
            {"supplier": "B", "item": "cement", "amount": 10.0, "category": ""}]
    classify_rows(rows, taxonomy=tax)
    assert rows[0]["category"] == "Raw Materials" and rows[0]["category_source"] == "given"
    assert rows[1]["category"] == "Construction" and rows[1]["category_source"] == "keyword"


def test_exported_template_round_trips(tmp_path):
    p = str(tmp_path / "tax.csv")
    n = write_csv(p, TAXONOMY)
    assert n == sum(len(k) for k in TAXONOMY.values())
    assert load_taxonomy(p) == TAXONOMY


def test_analysis_carries_taxonomy_label_and_uses_custom_categories():
    rows = generate(1500, 7)
    for r in rows:
        r["category"] = ""
    tax = merge_taxonomy(TAXONOMY, {"Cloud & Hosting": {"cloud": 5, "hosting": 5}})
    a = analyze(rows, taxonomy=tax, taxonomy_label=describe({"Cloud & Hosting": {"cloud": 5}}, tax, "extend"))
    assert "Cloud & Hosting" in dict(a.categories)
    assert a.taxonomy_label.startswith("built-in plus your file")
    assert analyze(generate(500, 7)).taxonomy_label.startswith("built-in taxonomy")


def test_cli_taxonomy_flag_and_export(tmp_path, capsys):
    csv_path, tax, out = str(tmp_path / "s.csv"), str(tmp_path / "tax.csv"), str(tmp_path / "r.html")
    assert main(["generate", "-o", csv_path, "-n", "800"]) == 0
    blank_categories(csv_path)
    assert main(["taxonomy", "-o", tax]) == 0
    with open(tax, "a", encoding="utf-8") as f:
        f.write("Cloud & Hosting,hosting,5\nCloud & Hosting,cloud,5\n")
    assert main(["analyze", csv_path, "-o", out, "--taxonomy", tax]) == 0
    html = open(out, encoding="utf-8").read()
    assert "built-in plus your file" in html and "Cloud &amp; Hosting" in html
    assert main(["analyze", csv_path, "-o", out, "--taxonomy", str(tmp_path / "missing.csv")]) == 1
    assert "error:" in capsys.readouterr().err
