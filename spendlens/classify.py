"""Category auto-classification from supplier name and item text.

Two passes, both pure standard library:

1. Keyword scoring. Supplier name, item and description are tokenised and scored
   against a weighted taxonomy. The winner needs a minimum score and a clear margin
   over the runner-up, otherwise the row is left alone rather than guessed.
2. Supplier history. A row that still has no category inherits the dominant
   category of the same supplier (by spend) from rows that did get one.

Rows that already carry a category are never overwritten unless asked to.
"""

from __future__ import annotations

import re
from collections import defaultdict

# category -> {keyword stem: weight}. A token matches a stem if it starts with it
# (stems under 4 characters must match exactly). Multi-word phrases match as substrings.
TAXONOMY: dict[str, dict[str, int]] = {
    "Packaging": {
        "packag": 3, "carton": 3, "corrugat": 3, "pallet wrap": 3, "stretch film": 3, "label": 2,
        "bottle": 2, "pouch": 2, "wrapper": 2, "shrink": 2, "box": 1, "tape": 1, "film": 1,
        "foam": 1, "bubble": 1, "crate": 1,
    },
    "Raw Materials": {
        "steel": 3, "metal": 3, "polymer": 3, "resin": 3, "chemical": 3, "aluminium": 3,
        "aluminum": 3, "copper": 3, "alloy": 2, "granule": 2, "pellet": 2, "ore": 2, "sheet": 1,
        "coil": 2, "rubber": 2, "solvent": 2, "pigment": 2, "ingot": 2, "powder": 1,
        "plastic": 2, "polyethylene": 3, "polypropylene": 3,
    },
    "Logistics": {
        "freight": 3, "logistic": 3, "shipping": 3, "cargo": 3, "courier": 3, "haulage": 3,
        "transport": 2, "warehous": 2, "container": 2, "customs": 2, "forwarding": 3,
        "trucking": 3, "delivery": 1, "pallet": 1, "line haul": 3, "last mile": 3,
    },
    "IT & Software": {
        "software": 3, "cloud": 3, "saas": 3, "licen": 2, "subscription": 2, "hosting": 3,
        "server": 2, "laptop": 3, "network": 1, "cyber": 2, "data": 1, "api": 2, "technolog": 1,
        "systems": 1, "digital": 1, "helpdesk": 2, "backup": 2, "endpoint": 2, "firewall": 3,
    },
    "MRO": {
        "bearing": 3, "spare": 3, "tool": 2, "fastener": 3, "bolt": 3, "gasket": 3, "valve": 3,
        "lubric": 3, "gloves": 2, "ppe": 3, "electrical": 2, "hardware": 2, "industrial": 1,
        "maintenance": 2, "wrench": 3, "drill": 2, "filter": 2, "belt": 1, "pump": 2,
        "supply": 1, "welding": 2, "abrasive": 3, "motor": 1, "cable": 1,
    },
    "Facilities": {
        "cleaning": 3, "janitorial": 3, "security": 3, "guard": 3, "facilit": 3, "catering": 3,
        "landscap": 3, "pest": 3, "housekeeping": 3, "hvac": 3, "elevator": 3, "canteen": 3,
        "garden": 2, "waste": 2, "utilities": 1, "office": 1, "uniform": 1,
    },
    "Professional Services": {
        "consult": 3, "advisory": 3, "legal": 3, "audit": 3, "law": 2, "attorney": 3, "tax": 2,
        "accounting": 3, "counsel": 3, "recruit": 3, "staffing": 3, "training": 2, "assurance": 3,
        "actuar": 3, "notary": 3, "retainer": 2, "partners": 1, "associates": 1,
    },
    "Marketing": {
        "marketing": 3, "media": 3, "agency": 2, "advertis": 3, "creative": 2, "brand": 3,
        "campaign": 3, "pr ": 1, "seo": 3, "design": 1, "print": 2, "event": 2, "promotion": 3,
        "studio": 2, "social": 1, "sponsor": 3, "pixel": 1,
    },
}

MIN_SCORE = 3          # a winning category needs at least this much evidence
MIN_MARGIN = 0.34      # and this share of the total score, or the row stays unclassified

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def score_text(text: str, taxonomy: dict[str, dict[str, int]] | None = None) -> dict[str, int]:
    """Raw keyword score per category for a piece of text."""
    taxonomy = taxonomy or TAXONOMY
    low = f" {text.lower()} "
    toks = _tokens(text)
    scores: dict[str, int] = {}
    for cat, kws in taxonomy.items():
        s = 0
        for kw, w in kws.items():
            if " " in kw:
                if kw in low:
                    s += w
            elif len(kw) < 4:
                if kw in toks:
                    s += w
            elif any(t.startswith(kw) for t in toks):
                s += w
        if s:
            scores[cat] = s
    return scores


def classify_text(text: str, taxonomy: dict[str, dict[str, int]] | None = None):
    """Return (category, confidence 0-1) or (None, 0.0)."""
    scores = score_text(text, taxonomy)
    if not scores:
        return None, 0.0
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top_cat, top = ranked[0]
    total = sum(scores.values())
    share = top / total
    if top < MIN_SCORE or share < MIN_MARGIN or (len(ranked) > 1 and ranked[1][1] == top):
        return None, 0.0
    # confidence blends how dominant the winner is with how much evidence it has
    strength = min(1.0, top / 8)
    return top_cat, round(0.5 * share + 0.5 * strength, 2)


def row_text(row: dict) -> str:
    return " ".join(row.get(k, "") for k in ("supplier", "item", "description") if row.get(k))


def classify_rows(rows: list[dict], canon_of: dict[str, str] | None = None,
                  overwrite: bool = False, min_confidence: float = 0.0) -> dict:
    """Fill missing categories in place. Returns coverage stats (spend and row counts).

    Sets on every row: `category`, `category_source` (given | keyword | supplier | none)
    and `category_conf` (1.0 for given values).
    """
    canon_of = canon_of or {}
    # pass 1: keep given categories, keyword-score the rest
    for r in rows:
        given = (r.get("category") or "").strip()
        if given and not overwrite:
            r["category"], r["category_source"], r["category_conf"] = given, "given", 1.0
            continue
        cat, conf = classify_text(row_text(r))
        if cat and conf >= min_confidence:
            r["category"], r["category_source"], r["category_conf"] = cat, "keyword", conf
        else:
            r["category"], r["category_source"], r["category_conf"] = "", "none", 0.0

    # pass 2: supplier history, weighted by spend, from rows that have a category
    hist: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if r["category"]:
            hist[canon_of.get(r["supplier"], r["supplier"])][r["category"]] += r["amount"]
    for r in rows:
        if r["category"]:
            continue
        h = hist.get(canon_of.get(r["supplier"], r["supplier"]))
        if not h:
            continue
        cat, spend = max(h.items(), key=lambda kv: kv[1])
        share = spend / sum(h.values())
        if share >= 0.6:
            r["category"], r["category_source"] = cat, "supplier"
            r["category_conf"] = round(0.4 + 0.4 * share, 2)

    stats = {s: {"rows": 0, "spend": 0.0} for s in ("given", "keyword", "supplier", "none")}
    for r in rows:
        st = stats[r["category_source"]]
        st["rows"] += 1
        st["spend"] += r["amount"]
    return stats
