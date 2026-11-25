"""Custom category lists for the classifier.

Bring your own categories and keywords as a CSV (opens in Excel) or JSON file.

CSV, one keyword per line, weight optional (default 3):

    category,keyword,weight
    Construction & Civil,cement,3
    Construction & Civil,rebar,3
    Packaging,gunny bag,2

JSON, either a list of keywords or a keyword -> weight map per category:

    {"Construction & Civil": ["cement", "rebar"], "Packaging": {"gunny bag": 2}}

By default the file extends the built-in taxonomy: your keywords are added to matching
categories (names match case-insensitively), new category names are created, and a keyword
you list again overrides its built-in weight. With mode="replace" only your file is used.

Matching rules are the same as the built-in list: a word matches a keyword if it starts with
it (keywords under 4 characters must match the whole word), and multi-word keywords match as
a phrase. Weights run from 1 (weak hint) to 5 (decisive). A winner needs a score of 3, so a
single keyword at weight 3 or more is enough to classify a row on its own.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

DEFAULT_WEIGHT = 3
MAX_WEIGHT = 5


def _clean(category: str, keyword: str, weight, where: str) -> tuple[str, str, int]:
    category, keyword = str(category).strip(), str(keyword).strip().lower()
    if not category:
        raise ValueError(f"{where}: category name is empty")
    if not keyword:
        raise ValueError(f"{where}: keyword is empty for category '{category}'")
    if weight in (None, ""):
        return category, keyword, DEFAULT_WEIGHT
    try:
        w = int(float(str(weight)))
    except ValueError:
        raise ValueError(f"{where}: weight '{weight}' for '{keyword}' is not a number") from None
    if not 1 <= w <= MAX_WEIGHT:
        raise ValueError(f"{where}: weight {w} for '{keyword}' must be between 1 and {MAX_WEIGHT}")
    return category, keyword, w


def _from_csv(path: Path) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = {c.strip().lower(): c for c in (reader.fieldnames or [])}
        if "category" not in cols or "keyword" not in cols:
            raise ValueError("taxonomy CSV needs 'category' and 'keyword' columns (and optionally 'weight')")
        for n, row in enumerate(reader, start=2):
            cat = (row.get(cols["category"]) or "").strip()
            kw = (row.get(cols["keyword"]) or "").strip()
            if not cat and not kw:
                continue                          # blank line
            if cat.startswith("#"):
                continue                          # comment line
            w = row.get(cols["weight"]) if "weight" in cols else None
            c, k, wt = _clean(cat, kw, w, f"line {n}")
            out.setdefault(c, {})[k] = wt
    return out


def _from_json(path: Path) -> dict[str, dict[str, int]]:
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("taxonomy JSON must be an object mapping category -> keywords")
    out: dict[str, dict[str, int]] = {}
    for cat, kws in data.items():
        if isinstance(kws, list):
            pairs = [(k, None) for k in kws]
        elif isinstance(kws, dict):
            pairs = list(kws.items())
        else:
            raise ValueError(f"category '{cat}': expected a list of keywords or a keyword -> weight map")
        for k, w in pairs:
            c, kw, wt = _clean(cat, k, w, f"category '{cat}'")
            out.setdefault(c, {})[kw] = wt
    return out


def load_taxonomy(path: str) -> dict[str, dict[str, int]]:
    """Read a custom taxonomy from a .csv or .json file. Raises ValueError with the line on bad input."""
    p = Path(path)
    kind = p.suffix.lower()
    if kind == ".csv":
        tax = _from_csv(p)
    elif kind == ".json":
        tax = _from_json(p)
    else:
        raise ValueError(f"taxonomy file must be .csv or .json, got '{p.suffix or p.name}'")
    if not tax:
        raise ValueError("taxonomy file has no keywords")
    return tax


def merge_taxonomy(base: dict[str, dict[str, int]], custom: dict[str, dict[str, int]],
                   mode: str = "extend") -> dict[str, dict[str, int]]:
    """Combine a custom taxonomy with the built-in one. `extend` adds to it, `replace` swaps it out."""
    if mode == "replace":
        return {c: dict(k) for c, k in custom.items()}
    if mode != "extend":
        raise ValueError("mode must be 'extend' or 'replace'")
    merged = {c: dict(k) for c, k in base.items()}
    by_lower = {c.lower(): c for c in merged}
    for cat, kws in custom.items():
        name = by_lower.get(cat.lower())
        if name is None:
            name = cat
            by_lower[cat.lower()] = cat
            merged[name] = {}
        merged[name].update(kws)
    return merged


def describe(custom: dict[str, dict[str, int]], merged: dict[str, dict[str, int]], mode: str) -> str:
    """One line for the report: what the classifier was working from."""
    n_kw = sum(len(k) for k in custom.values())
    if mode == "replace":
        return f"your taxonomy only: {len(merged)} categories, {n_kw} keywords"
    return f"built-in plus your file: {len(merged)} categories, {n_kw} custom keywords"


def write_csv(path: str, taxonomy: dict[str, dict[str, int]]) -> int:
    """Write a taxonomy as category,keyword,weight. Handy as a starting template."""
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category", "keyword", "weight"])
        for cat, kws in taxonomy.items():
            for kw, wt in sorted(kws.items(), key=lambda kv: (-kv[1], kv[0])):
                w.writerow([cat, kw, wt])
                n += 1
    return n
