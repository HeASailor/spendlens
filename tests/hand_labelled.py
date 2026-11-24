"""Hand-written, messy, ERP-style descriptions with the category a buyer would pick.

Written independently of the synthetic generator so the classifier is not graded on text it
was tuned against. `None` means a careful human could not tell, and the right answer is to abstain.
"""

CASES = [
    ("TCI FREIGHT PVT LTD - FTL BLR-CHN", "Logistics"),
    ("Blue Dart courier charges Oct", "Logistics"),
    ("Customs clearing and forwarding agent fee", "Logistics"),
    ("AWS cloud hosting monthly invoice", "IT & Software"),
    ("Microsoft 365 licences annual subscription", "IT & Software"),
    ("Dell laptops 15 units", "IT & Software"),
    ("Firewall renewal and cyber security audit", "IT & Software"),
    ("SKF bearings 6205 2RS", "MRO"),
    ("Industrial gloves and PPE kit", "MRO"),
    ("Hydraulic pump spare parts", "MRO"),
    ("Welding electrodes and abrasives", "MRO"),
    ("Corrugated boxes 5 ply export", "Packaging"),
    ("Shrink wrap and stretch film rolls", "Packaging"),
    ("Printed labels for 500ml bottle", "Packaging"),
    ("HR-grade steel coil 1.5mm", "Raw Materials"),
    ("Polyethylene resin granules", "Raw Materials"),
    ("Copper and aluminium ingots", "Raw Materials"),
    ("Industrial solvent and pigment", "Raw Materials"),
    ("Housekeeping and janitorial services", "Facilities"),
    ("Security guards deployment Q3", "Facilities"),
    ("Canteen catering services", "Facilities"),
    ("HVAC AMC site 2", "Facilities"),
    ("Statutory audit fees FY25", "Professional Services"),
    ("Legal counsel retainer - contracts", "Professional Services"),
    ("Management consulting advisory phase 2", "Professional Services"),
    ("Recruitment and staffing agency fee", "Professional Services"),
    ("Digital marketing campaign Diwali", "Marketing"),
    ("Brand agency creative design", "Marketing"),
    ("Trade show event sponsorship", "Marketing"),
    ("Outdoor advertising hoardings", "Marketing"),
    ("Misc expenses", None),
    ("Payment adjustment", None),
    ("Sundry vendor invoice 4471", None),
    ("Reimbursement", None),
]
