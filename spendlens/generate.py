"""Synthetic spend data generator (seeded, deterministic)."""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta

CATEGORIES = {
    "Packaging": ["Northwind Packaging", "BlueLeaf Cartons", "Apex Pack Solutions", "Orbit Films"],
    "Raw Materials": ["Titan Metals", "Granite Polymers", "Helix Chemicals", "Ironbridge Steel"],
    "Logistics": ["SwiftHaul Freight", "Meridian Logistics", "Coastline Shipping", "Redline Cargo"],
    "IT & Software": ["Cloudpine Systems", "Bytewise Technologies", "Nimbus Data", "Quanta Software"],
    "MRO": ["Boltworks Supply", "Gearhead Industrial", "Fixwell Tools", "Sparkline Electricals"],
    "Facilities": ["Evergreen Facilities", "Brightside Cleaning", "SafeGuard Security"],
    "Professional Services": ["Clarion Advisory", "Pinnacle Consulting", "LexBridge Legal"],
    "Marketing": ["Pixelcraft Studio", "Amplify Media", "Brandforge Agency"],
}

# Messy variants of the same supplier, the kind real ERPs are full of.
SUFFIXES = ["", " Pvt Ltd", " Private Limited", " Ltd.", " LLC", " Inc", " Co."]

# Spend weight per category (rough share of total).
WEIGHTS = {
    "Packaging": 18, "Raw Materials": 30, "Logistics": 20, "IT & Software": 10,
    "MRO": 8, "Facilities": 6, "Professional Services": 5, "Marketing": 3,
}


def _variant(name: str, rng: random.Random) -> str:
    style = rng.random()
    out = name
    if style < 0.25:
        out = name.upper()
    elif style < 0.40:
        out = name.replace(" ", "  ")
    elif style < 0.50:
        out = name.split()[0] + " " + name.split()[1][:3] + "."
    return out + rng.choice(SUFFIXES)


def generate(rows: int = 4000, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    suppliers: list[tuple[str, str, float]] = []  # (name, category, popularity)

    for cat, names in CATEGORIES.items():
        for i, base in enumerate(names):
            pop = 1.0 / (i + 1) ** 1.3  # Zipf-ish: a few suppliers dominate
            variants = {base}
            for _ in range(rng.choice([0, 1, 1, 2])):
                variants.add(_variant(base, rng))
            for v in variants:
                suppliers.append((v, cat, pop / len(variants)))
        # long tail of one-off suppliers
        for t in range(rng.randint(8, 22)):
            suppliers.append((f"{cat.split()[0]} Vendor {rng.randint(100, 999)}-{t}", cat, 0.02))

    pops = [s[2] * WEIGHTS[s[1]] for s in suppliers]
    start = date(2025, 1, 1)
    out = []
    for n in range(rows):
        name, cat, _ = rng.choices(suppliers, weights=pops, k=1)[0]
        d = start + timedelta(days=rng.randint(0, 364))
        amount = round(rng.lognormvariate(9.2, 1.1), 2)
        has_po = rng.random() > (0.28 if "Vendor" in name else 0.12)
        out.append({
            "invoice_id": f"INV-{100000 + n}",
            "date": d.isoformat(),
            "supplier": name,
            "category": cat,
            "amount": amount,
            "po_number": f"PO-{rng.randint(10000, 99999)}" if has_po else "",
            "payment_terms_days": rng.choice([15, 30, 30, 45, 45, 60, 90]),
        })
    return out


def write_csv(path: str, rows: int = 4000, seed: int = 42) -> int:
    data = generate(rows, seed)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
        w.writeheader()
        w.writerows(data)
    return len(data)
