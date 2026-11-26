"""Supplier-name normalisation and similarity, shared by spend clustering and contract matching."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

LEGAL_SUFFIXES = {
    "pvt", "ltd", "private", "limited", "inc", "incorporated", "llc", "llp",
    "gmbh", "co", "corp", "corporation", "company", "plc", "sa", "bv", "ag",
}


def normalize_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    tokens = [t for t in s.split() if t not in LEGAL_SUFFIXES]
    return " ".join(tokens)


def name_similarity(a: str, b: str) -> float:
    """Similarity (0-1) of two normalised names. 0 when they cannot be the same entity."""
    if abs(len(a) - len(b)) > 6 or a[:2] != b[:2]:
        return 0.0
    # names that differ in their numbers are different entities
    if re.findall(r"\d+", a) != re.findall(r"\d+", b):
        return 0.0
    return SequenceMatcher(None, a, b).ratio()
