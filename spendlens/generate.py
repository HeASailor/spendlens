"""Synthetic spend data generator (seeded, deterministic).

Everything here is invented: supplier names, items and prices. Each supplier gets its own
price level, so the same item really does cost different amounts at different suppliers,
and about one row in five is written out without a category so the classifier has work to do.
"""

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

# item -> (unit, base unit price, spec text used in the free-text description)
ITEMS = {
    "Packaging": [
        ("Corrugated carton 5-ply", "each", 42, "40x30x20 cm export grade"),
        ("Stretch film 500mm", "roll", 310, "23 micron machine grade"),
        ("Printed product label", "1000 pcs", 95, "matte finish, 4 colour"),
        ("HDPE bottle 500ml", "each", 11, "screw cap included"),
    ],
    "Raw Materials": [
        ("Cold rolled steel coil", "100 kg", 6100, "1.2mm CRCA"),
        ("Polypropylene granules", "100 kg", 9800, "injection moulding grade"),
        ("Industrial solvent IPA", "drum", 14500, "99% purity 200L"),
        ("Copper wire rod", "100 kg", 78500, "8mm oxygen free"),
    ],
    "Logistics": [
        ("Full truckload freight", "trip", 38000, "Bengaluru to Pune 20T"),
        ("Container shipping 40ft", "container", 142000, "Nhava Sheva to Rotterdam"),
        ("Warehousing pallet", "pallet/month", 480, "ambient storage"),
        ("Courier parcel", "parcel", 160, "standard 2kg domestic"),
    ],
    "IT & Software": [
        ("Cloud hosting subscription", "month", 24000, "4 vCPU production cluster"),
        ("Software licence seat", "seat/year", 18500, "enterprise tier"),
        ("Laptop business class", "each", 78000, "16GB 512GB SSD"),
        ("Endpoint security licence", "seat/year", 2400, "managed EDR"),
    ],
    "MRO": [
        ("Deep groove bearing 6205", "each", 260, "sealed both sides"),
        ("Safety gloves nitrile", "pair", 85, "cut level 3"),
        ("Hydraulic gasket set", "kit", 1250, "viton, 12 pieces"),
        ("Welding electrode 3.15mm", "box", 640, "E7018 5kg"),
    ],
    "Facilities": [
        ("Housekeeping services", "person/month", 21500, "site cleaning staff"),
        ("Security guard shift", "shift", 950, "unarmed 12 hours"),
        ("HVAC maintenance visit", "visit", 7800, "quarterly service"),
        ("Pest control service", "visit", 3200, "monthly treatment"),
    ],
    "Professional Services": [
        ("Consulting day rate", "day", 52000, "senior consultant"),
        ("Statutory audit fee", "quarter", 160000, "quarterly review"),
        ("Legal counsel retainer", "month", 120000, "commercial contracts"),
        ("Recruitment service fee", "hire", 180000, "mid level hire"),
    ],
    "Marketing": [
        ("Digital campaign management", "month", 85000, "paid search and social"),
        ("Event stall design", "event", 260000, "10x10 ft exhibition stall"),
        ("Brand collateral printing", "lot", 48000, "brochures and banners"),
        ("Video production", "video", 210000, "60 second product film"),
    ],
}

# Invented annual price drift per item, applied smoothly across the year so the trend view has
# something to find. Items not listed drift by DEFAULT_DRIFT.
DEFAULT_DRIFT = 0.02
ITEM_DRIFT = {
    "Cold rolled steel coil": 0.14, "Copper wire rod": 0.19, "Polypropylene granules": 0.07,
    "Industrial solvent IPA": -0.06, "Container shipping 40ft": -0.12, "Full truckload freight": 0.09,
    "Corrugated carton 5-ply": 0.11, "Stretch film 500mm": 0.05, "Laptop business class": -0.07,
    "Cloud hosting subscription": -0.03, "Security guard shift": 0.08, "Housekeeping services": 0.06,
    "Consulting day rate": 0.05, "Deep groove bearing 6205": 0.0, "Video production": -0.04,
}

# Messy variants of the same supplier, the kind real ERPs are full of.
SUFFIXES = ["", " Pvt Ltd", " Private Limited", " Ltd.", " LLC", " Inc", " Co."]

# Spend weight per category (rough share of total).
WEIGHTS = {
    "Packaging": 18, "Raw Materials": 30, "Logistics": 20, "IT & Software": 10,
    "MRO": 8, "Facilities": 6, "Professional Services": 5, "Marketing": 3,
}

BLANK_CATEGORY_RATE = 0.20   # share of rows exported without a category
BLANK_TEXT_RATE = 0.10       # share of rows with no item or description text at all
FIELDS = ["invoice_id", "date", "supplier", "category", "item", "description",
          "quantity", "unit_price", "amount", "po_number", "payment_terms_days"]


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
    """Rows carry a hidden `_true_category` so tests can score the classifier."""
    rng = random.Random(seed)
    # (name, category, popularity, price level). Variants of one supplier share a price level.
    suppliers: list[tuple[str, str, float, float]] = []

    for cat, names in CATEGORIES.items():
        for i, base in enumerate(names):
            pop = 1.0 / (i + 1) ** 1.3  # Zipf-ish: a few suppliers dominate
            level = rng.lognormvariate(0, 0.08)
            variants = {base}
            for _ in range(rng.choice([0, 1, 1, 2])):
                variants.add(_variant(base, rng))
            for v in variants:
                suppliers.append((v, cat, pop / len(variants), level))
        # long tail of one-off suppliers (pricier: no volume leverage)
        for t in range(rng.randint(8, 22)):
            suppliers.append((f"{cat.split()[0]} Vendor {rng.randint(100, 999)}-{t}", cat, 0.02,
                              rng.lognormvariate(0.06, 0.10)))

    pops = [s[2] * WEIGHTS[s[1]] for s in suppliers]
    start = date(2025, 1, 1)
    out = []
    for n in range(rows):
        name, cat, _, level = rng.choices(suppliers, weights=pops, k=1)[0]
        item, unit, base_price, spec = rng.choice(ITEMS[cat])
        day = rng.randint(0, 364)
        d = start + timedelta(days=day)
        drift = (1 + ITEM_DRIFT.get(item, DEFAULT_DRIFT)) ** (day / 365)
        price = round(base_price * level * drift * rng.uniform(0.96, 1.04), 2)
        target = rng.lognormvariate(9.2, 1.1)
        qty = max(1, round(target / price))
        has_po = rng.random() > (0.28 if "Vendor" in name else 0.12)
        no_text = rng.random() < BLANK_TEXT_RATE
        out.append({
            "invoice_id": f"INV-{100000 + n}",
            "date": d.isoformat(),
            "supplier": name,
            "category": "" if rng.random() < BLANK_CATEGORY_RATE else cat,
            "item": "" if no_text else item,
            "description": "" if no_text else f"{item}, {spec} ({unit})",
            "quantity": qty,
            "unit_price": price,
            "amount": round(qty * price, 2),
            "po_number": f"PO-{rng.randint(10000, 99999)}" if has_po else "",
            "payment_terms_days": rng.choice([15, 30, 30, 45, 45, 60, 90]),
            "_true_category": cat,
        })
    return out


def write_csv(path: str, rows: int = 4000, seed: int = 42) -> int:
    data = generate(rows, seed)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(data)
    return len(data)
