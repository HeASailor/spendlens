"""Render an Analysis as a single self-contained HTML dashboard (no JS, no CDN)."""

from __future__ import annotations

from html import escape

from . import __version__
from .analyze import Analysis
from .contracts import COVERED, NONE, OUTSIDE, UNDATED
from .trend import MIX_FLAG, MOVE_THRESHOLD


UNITS = {"mode": "intl"}


def money(x: float) -> str:
    if UNITS["mode"] == "indian":
        if x >= 1e7:
            return f"{x / 1e7:.2f} Cr"
        if x >= 1e5:
            return f"{x / 1e5:.2f} L"
    else:
        if x >= 1e9:
            return f"{x / 1e9:.2f}B"
        if x >= 1e6:
            return f"{x / 1e6:.2f}M"
    if x >= 1e3:
        return f"{x / 1e3:.1f}K"
    return f"{x:,.0f}"


def _bars(items: list[tuple[str, float]], width=560, bar_h=22, gap=10, color="#2dd4bf") -> str:
    if not items:
        return ""
    mx = max(v for _, v in items) or 1
    label_w = 170
    h = len(items) * (bar_h + gap)
    rows = []
    for i, (name, v) in enumerate(items):
        y = i * (bar_h + gap)
        w = (width - label_w - 70) * v / mx
        rows.append(
            f'<text x="0" y="{y + 15}" class="lbl">{escape(name[:24])}</text>'
            f'<rect x="{label_w}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="4" fill="{color}" opacity=".9"/>'
            f'<text x="{label_w + w + 8:.1f}" y="{y + 15}" class="val">{money(v)}</text>')
    return f'<svg viewBox="0 0 {width} {h}" role="img">{"".join(rows)}</svg>'


def _line(points: list[tuple[str, float]], width=560, height=170) -> str:
    if len(points) < 2:
        return ""
    pad_l, pad_b, pad_t = 8, 24, 10
    vals = [v for _, v in points]
    lo, hi = min(vals) * 0.9, max(vals) * 1.05
    span = (hi - lo) or 1
    step = (width - pad_l - 10) / (len(points) - 1)
    xy = [(pad_l + i * step, pad_t + (height - pad_b - pad_t) * (1 - (v - lo) / span))
          for i, (_, v) in enumerate(points)]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(xy))
    area = path + f" L{xy[-1][0]:.1f},{height - pad_b} L{xy[0][0]:.1f},{height - pad_b} Z"
    labels = "".join(
        f'<text x="{x:.1f}" y="{height - 6}" class="lbl" text-anchor="middle">{points[i][0][5:]}</text>'
        for i, (x, _) in enumerate(xy) if i % max(1, len(points) // 6) == 0)
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#fbbf24"/>' for x, y in xy)
    return (f'<svg viewBox="0 0 {width} {height}" role="img">'
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="#fbbf24" stop-opacity=".35"/>'
            f'<stop offset="1" stop-color="#fbbf24" stop-opacity="0"/></linearGradient></defs>'
            f'<path d="{area}" fill="url(#g)"/><path d="{path}" fill="none" stroke="#fbbf24" stroke-width="2.2"/>'
            f'{dots}{labels}</svg>')


PALETTE = ["#2dd4bf", "#60a5fa", "#fbbf24", "#a78bfa", "#f472b6", "#34d399", "#fb923c", "#94a3b8"]


def _donut(items: list[tuple[str, float]], size=190) -> str:
    """Donut with legend. Items beyond the 7th are folded into Other."""
    from math import cos, pi, sin
    if not items:
        return ""
    items = list(items)
    if len(items) > 8:
        items = items[:7] + [("Other", sum(v for _, v in items[7:]))]
    tot = sum(v for _, v in items) or 1
    r, sw, c = size / 2 - 14, 26, size / 2
    ang, arcs = -pi / 2, []
    for i, (_, v) in enumerate(items):
        sweep = v / tot * 2 * pi
        if sweep >= 2 * pi - 1e-6:
            sweep = 2 * pi - 1e-4
        x1, y1 = c + r * cos(ang), c + r * sin(ang)
        x2, y2 = c + r * cos(ang + sweep), c + r * sin(ang + sweep)
        arcs.append(f'<path d="M{x1:.2f},{y1:.2f} A{r},{r} 0 {1 if sweep > pi else 0} 1 {x2:.2f},{y2:.2f}" '
                    f'fill="none" stroke="{PALETTE[i % 8]}" stroke-width="{sw}"/>')
        ang += sweep
    legend = "".join(
        f'<div class="lg"><i style="background:{PALETTE[i % 8]}"></i>{escape(n[:22])}'
        f'<b>{v / tot * 100:.0f}%</b></div>' for i, (n, v) in enumerate(items))
    return (f'<div class="donut"><svg viewBox="0 0 {size} {size}" role="img">{"".join(arcs)}'
            f'<text x="{c}" y="{c - 2}" text-anchor="middle" class="dv">{money(tot)}</text>'
            f'<text x="{c}" y="{c + 15}" text-anchor="middle" class="lbl">total</text></svg>'
            f'<div class="legend">{legend}</div></div>')


def _stack(parts: list[tuple[str, float, str]]) -> str:
    """Single horizontal stacked bar (label, value, colour) with a legend underneath."""
    tot = sum(v for _, v, _ in parts) or 1
    segs = "".join(f'<span style="width:{v / tot * 100:.2f}%;background:{col}"></span>'
                   for _, v, col in parts if v > 0)
    leg = "".join(f'<div class="lg"><i style="background:{col}"></i>{escape(n)}'
                  f'<b>{v / tot * 100:.0f}%</b></div>' for n, v, col in parts)
    return f'<div class="stack">{segs}</div><div class="legend row">{leg}</div>'


def _dumbbell(items, width=560, row_h=40) -> str:
    """Per item: cheapest price paid (teal) to dearest (red), average marked in amber."""
    items = [i for i in items if i.spread_pct > 0]
    if not items:
        return ""
    label_w, right = 190, 62
    mx = max(i.spread_pct for i in items) or 1
    span = width - label_w - right
    out = []
    for n, it in enumerate(items):
        y = n * row_h + 14
        xb = label_w
        xa = label_w + (it.avg_price - it.best_price) / it.best_price * 100 / mx * span
        xw = label_w + it.spread_pct / mx * span
        out.append(
            f'<text x="0" y="{y + 4}" class="lbl">{escape(it.item[:27])}</text>'
            f'<line x1="{xb}" y1="{y}" x2="{xw:.1f}" y2="{y}" stroke="#334568" stroke-width="3" stroke-linecap="round"/>'
            f'<circle cx="{xb}" cy="{y}" r="5" fill="#2dd4bf"/>'
            f'<circle cx="{xa:.1f}" cy="{y}" r="4" fill="#fbbf24"/>'
            f'<circle cx="{xw:.1f}" cy="{y}" r="5" fill="#f87171"/>'
            f'<text x="{xw + 10:.1f}" y="{y + 4}" class="val">+{it.spread_pct:.0f}%</text>')
    h = len(items) * row_h + 6
    return f'<svg viewBox="0 0 {width} {h}" role="img">{"".join(out)}</svg>'


def _spark(values: list[float], rising: bool, width=130, height=34) -> str:
    """Tiny unit-price line for one item. Rising price is red, falling is teal."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = (width - 8) / (len(values) - 1)
    xy = [(4 + i * step, 4 + (height - 8) * (1 - (v - lo) / span)) for i, v in enumerate(values)]
    col = "#f87171" if rising else "#2dd4bf"
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    return (f'<svg viewBox="0 0 {width} {height}" role="img" style="width:{width}px">'
            f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2" stroke-linejoin="round"/>'
            f'<circle cx="{xy[-1][0]:.1f}" cy="{xy[-1][1]:.1f}" r="3" fill="{col}"/></svg>')


def _kpi(label: str, value: str, sub: str = "", tone: str = "") -> str:
    return (f'<div class="kpi {tone}"><div class="k">{escape(label)}</div>'
            f'<div class="v">{escape(value)}</div><div class="s">{escape(sub)}</div></div>')


CSS = """
:root{--bg:#0b1220;--card:#111a2e;--line:#1f2b45;--tx:#e6edf7;--mut:#8da2c0;--teal:#2dd4bf;--amb:#fbbf24;--red:#f87171}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1200px 600px at 10% -10%,#16223d,var(--bg));
color:var(--tx);font:15px/1.5 -apple-system,Segoe UI,Inter,Roboto,sans-serif;padding:40px 24px}
.wrap{max-width:1080px;margin:auto}h1{font-size:30px;margin:0 0 4px;letter-spacing:-.02em}
h1 span{color:var(--teal)}.sub{color:var(--mut);margin-bottom:28px}
.grid{display:grid;gap:16px}.k4{grid-template-columns:repeat(4,1fr)}.c2{grid-template-columns:1fr 1fr}
@media(max-width:820px){.k4{grid-template-columns:1fr 1fr}.c2{grid-template-columns:1fr}}
.card,.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
.kpi .k{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
.kpi .v{font-size:28px;font-weight:700;margin:4px 0}.kpi .s{color:var(--mut);font-size:13px}
.kpi.warn .v{color:var(--amb)}.kpi.bad .v{color:var(--red)}.kpi.good .v{color:var(--teal)}
h2{font-size:14px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em;margin:0 0 12px}
svg{width:100%;height:auto}.lbl{fill:var(--mut);font-size:11px}.val{fill:var(--tx);font-size:11px;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13.5px}th{color:var(--mut);text-align:left;font-weight:500}
td,th{padding:7px 6px;border-bottom:1px solid var(--line);vertical-align:top}td.n{text-align:right;white-space:nowrap}
.tag{display:inline-block;background:#1b2a49;border-radius:6px;padding:1px 7px;margin:1px 3px 1px 0;font-size:12px;color:#b9c8e0}
.big{font-size:38px;font-weight:800;color:var(--teal);letter-spacing:-.02em}
.foot{color:var(--mut);font-size:12px;margin-top:26px}
.donut{display:flex;align-items:center;gap:18px}.donut svg{width:190px;flex:none}
.dv{fill:var(--tx);font-size:19px;font-weight:700}
.legend{display:flex;flex-direction:column;gap:5px;font-size:12.5px;flex:1}.legend.row{flex-direction:row;flex-wrap:wrap;gap:6px 16px;margin-top:10px}
.lg{display:flex;align-items:center;gap:7px;color:#c3d0e6}.lg i{width:10px;height:10px;border-radius:3px;flex:none}.lg b{margin-left:auto;color:var(--mut);font-weight:600}.legend.row .lg b{margin-left:4px}
.stack{display:flex;height:16px;border-radius:8px;overflow:hidden;background:var(--line)}.stack span{display:block}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11.5px;background:#1b2a49;color:#b9c8e0}
.pill.hi{background:#3b1d24;color:#fca5a5}.pill.md{background:#3a2f12;color:#fcd34d}.pill.lo{background:#12332f;color:#5eead4}
.hero{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:26px}
.hero .sub{margin:0}.badge{border:1px solid var(--line);border-radius:99px;padding:4px 12px;color:var(--mut);font-size:12px}
.hint{color:var(--mut);font-size:12.5px;margin:-4px 0 10px}
@media(max-width:560px){.donut{flex-direction:column;align-items:stretch}.donut svg{width:170px;margin:auto}}
"""


def _contracts(a: Analysis) -> str:
    c = a.contracts
    if not c:
        return ""
    parts = [("Covered", c.spend[COVERED], "#2dd4bf"),
             ("Outside contract dates", c.spend[OUTSIDE], "#fbbf24"),
             ("No contract", c.spend[NONE], "#f87171")]
    if c.spend[UNDATED]:
        parts.append(("Undated", c.spend[UNDATED], "#94a3b8"))
    urows = "".join(
        f"<tr><td>{escape(s.supplier)}</td><td class='n'>{money(s.outside)}</td>"
        f"<td class='n'>{money(s.none)}</td><td class='n'>{money(s.uncovered)}</td></tr>"
        for s in c.suppliers[:8] if s.uncovered > 0) or "<tr><td colspan=4>Everything is covered.</td></tr>"
    erows = "".join(
        f"<tr><td>{escape(sup)}<br><span class='tag'>{escape(k.contract_id or 'no ID')}</span></td>"
        f"<td class='n'>{k.end.isoformat()}</td>"
        f"<td class='n'><span class='pill {'hi' if days <= 30 else 'md'}'>{days} days</span></td>"
        f"<td class='n'>{money(spend)}</td></tr>"
        for k, sup, days, spend in c.expiring[:8]) or (
        f"<tr><td colspan=4>None in the next {c.expiry_days} days.</td></tr>")
    notes = []
    if len(c.expiring) > 8:
        notes.append(f"{len(c.expiring) - 8} more expiring contracts are in the Excel export.")
    if c.unmatched:
        names = ", ".join(escape(k.supplier) for k in c.unmatched[:4])
        notes.append(f"{len(c.unmatched)} contract(s) matched no supplier in the spend file "
                     f"({names}{', ...' if len(c.unmatched) > 4 else ''}). Check the names.")
    note = "".join(f"<div class='hint' style='margin-top:10px'>{n}</div>" for n in notes)
    as_of = c.as_of.isoformat() if c.as_of else "n/a"
    return f"""<div class="grid c2" style="margin-top:16px">
 <div class="card"><h2>Contract coverage</h2>
  <div class="big" style="font-size:30px">{c.covered_pct:.0f}%</div>
  <div class="hint">of spend was with a supplier under a live contract on the invoice date
   ({c.contracts} contracts). Covered does not mean the price or terms were followed.</div>
  {_stack(parts)}
  <table style="margin-top:14px"><tr><th>Top uncovered suppliers</th><th class="n">Outside dates</th>
   <th class="n">No contract</th><th class="n">Total</th></tr>{urows}</table></div>
 <div class="card"><h2>Contracts expiring within {c.expiry_days} days</h2>
  <div class="hint">Counted from the latest invoice date ({as_of}).</div>
  <table><tr><th>Supplier</th><th class="n">Ends</th><th class="n">Left</th>
   <th class="n">Spend under it</th></tr>{erows}</table>{note}</div>
</div>"""


def render(a: Analysis, title: str = "Spend Analysis") -> str:
    dup_pct = (1 - a.unique_suppliers / a.supplier_records) * 100 if a.supplier_records else 0
    tail_pct = a.tail_spend / a.total_spend * 100 if a.total_spend else 0
    sav_pct = a.savings_total / a.total_spend * 100 if a.total_spend else 0

    kpis = "".join([
        _kpi("Total spend", money(a.total_spend), f"{a.rows:,} invoices"),
        _kpi("Suppliers", f"{a.unique_suppliers:,}",
             f"{a.supplier_records:,} records, {dup_pct:.0f}% duplicates", "warn" if dup_pct > 5 else "good"),
        _kpi("80% of spend", f"{a.pareto_suppliers_80} suppliers",
             f"{a.pareto_suppliers_80 / max(a.unique_suppliers, 1) * 100:.0f}% of the base"),
        _kpi("Maverick spend", f"{a.maverick_pct:.1f}%", f"{money(a.maverick_spend)} with no PO",
             "bad" if a.maverick_pct > 15 else "warn" if a.maverick_pct > 8 else "good"),
    ])

    sup_rows = "".join(
        f"<tr><td>{escape(n)}</td><td class='n'>{money(s)}</td><td class='n'>{c:.0f}%</td></tr>"
        for n, s, c in a.top_suppliers)

    dup_rows = "".join(
        f"<tr><td>{escape(c)}<br>{''.join(f'<span class=tag>{escape(v)}</span>' for v in [x for x in vs if x != c][:4])}{f'<span class=tag>+{len([x for x in vs if x != c]) - 4} more</span>' if len([x for x in vs if x != c]) > 4 else ''}</td>"
        f"<td class='n'>{money(s)}</td></tr>"
        for c, vs, s in a.duplicate_clusters[:8]) or "<tr><td>No duplicates found.</td><td></td></tr>"

    hhi_rows = "".join(
        f"<tr><td>{escape(c)}</td><td class='n'>{h:,}</td>"
        f"<td>{'High concentration' if h > 2500 else 'Moderate' if h > 1500 else 'Fragmented'}</td></tr>"
        for c, h in sorted(a.hhi_by_category.items(), key=lambda kv: -kv[1]))

    cls = a.classification
    class_card = ""
    if cls:
        parts = [("Provided", cls["given"]["spend"], "#60a5fa"),
                 ("Auto: keywords", cls["keyword"]["spend"], "#2dd4bf"),
                 ("Auto: supplier history", cls["supplier"]["spend"], "#a78bfa"),
                 ("Unclassified", cls["none"]["spend"], "#f87171")]
        src_rows = "".join(
            f"<tr><td>{n}</td><td class='n'>{cls[k]['rows']:,}</td><td class='n'>{money(cls[k]['spend'])}</td></tr>"
            for k, n in (("given", "Provided in the file"), ("keyword", "Auto: keyword match"),
                         ("supplier", "Auto: supplier history"), ("none", "Unclassified")))
        rev = "".join(
            f"<tr><td>{escape((r.get('item') or r.get('description') or r['supplier'])[:44])}</td>"
            f"<td>{escape(r['category'])}</td><td class='n'><span class='pill md'>{r['category_conf']:.2f}</span></td></tr>"
            for r in a.review_rows) or "<tr><td colspan=3>Nothing low-confidence. Nice.</td></tr>"
        class_card = f"""<div class="grid c2" style="margin-top:16px">
 <div class="card"><h2>Category coverage</h2>
  <div class="hint">{a.classified_pct:.0f}% of spend has a category; SpendLens filled in {a.auto_classified_pct:.0f}%.
   Working from the {escape(a.taxonomy_label)}.</div>
  {_stack(parts)}
  <table style="margin-top:14px"><tr><th>Source</th><th class="n">Invoices</th><th class="n">Spend</th></tr>{src_rows}</table></div>
 <div class="card"><h2>Auto-classified, worth a second look</h2>
  <table><tr><th>Item or supplier</th><th>Guess</th><th class="n">Conf.</th></tr>{rev}</table></div>
</div>"""

    price_card = ""
    if a.price_items:
        top = a.price_items[:8]
        prows = "".join(
            f"<tr><td>{escape(i.item)}<br><span class='tag'>{len(i.suppliers)} suppliers</span>"
            f"<span class='tag'>best: {escape(i.best_supplier[:22])}</span></td>"
            f"<td class='n'>{money(i.best_price)} to {money(i.worst_price)}</td>"
            f"<td class='n'>{money(i.gap_value)}</td></tr>" for i in top[:6])
        price_card = f"""<div class="grid c2" style="margin-top:16px">
 <div class="card"><h2>Price spread, same item across suppliers</h2>
  <div class="hint"><span style="color:#2dd4bf">&#9679;</span> cheapest paid
   <span style="color:#fbbf24">&#9679;</span> average <span style="color:#f87171">&#9679;</span> dearest paid</div>
  {_dumbbell(top)}</div>
 <div class="card"><h2>Biggest price gaps</h2>
  <div class="big" style="font-size:30px">{money(a.price_gap_total)}</div>
  <div class="sub" style="margin-bottom:8px">paid above the best price already achieved, across
   {len(a.price_items)} items ({a.price_covered_pct:.0f}% of spend)</div>
  <table><tr><th>Item</th><th class="n">Price range</th><th class="n">Gap</th></tr>{prows}</table></div>
</div>"""

    trend_card = ""
    if a.trend_items:
        top = a.trend_items[:8]
        up = sum(1 for t in a.trend_items if t.change_pct >= MOVE_THRESHOLD)
        down = sum(1 for t in a.trend_items if t.change_pct <= -MOVE_THRESHOLD)
        trows = ""
        for t in top:
            gap = t.mix_gap
            note = (f"<span class='tag'>mix: all-supplier avg {t.raw_change_pct:+.0f}%</span>"
                    if gap is not None and abs(gap) >= MIX_FLAG else
                    "<span class='tag'>no supplier in both windows</span>" if gap is None else "")
            tone = "hi" if t.change_pct >= MOVE_THRESHOLD else "lo" if t.change_pct <= -MOVE_THRESHOLD else ""
            trows += (f"<tr><td>{escape(t.item)}<br><span class='tag'>{escape(t.category)}</span>{note}</td>"
                      f"<td>{_spark([p[1] for p in t.periods], t.change_pct > 0)}</td>"
                      f"<td class='n'>{money(t.early_price)} to {money(t.late_price)}</td>"
                      f"<td class='n'><span class='pill {tone}'>{t.change_pct:+.1f}%</span></td></tr>")
        unit = "quarter" if a.trend_period == "quarter" else "month"
        ref = top[0]
        trend_card = f"""<div class="card" style="margin-top:16px"><h2>Price trend per item</h2>
  <div class="hint">{up} items up and {down} down by {MOVE_THRESHOLD:.0f}% or more, across {len(a.trend_items)} items
   ({a.trend_covered_pct:.0f}% of spend). Unit price by {unit}, early window ({ref.early_span}) against late window
   ({ref.late_span}). The change is like-for-like per supplier where possible, so a switch between a cheap and a
   dear supplier does not read as a price move. Ranked by cost impact.</div>
  <table><tr><th>Item</th><th>Unit price by {unit}</th><th class="n">Early to late</th><th class="n">Change</th></tr>{trows}</table></div>"""

    contract_card = _contracts(a)

    sav_rows = "".join(
        f"<tr><td>{escape(k)}</td><td class='n'>{money(v)}</td></tr>" for k, v in a.savings.items())

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<style>{CSS}</style></head><body><div class="wrap">
<div class="hero"><div><h1>Spend<span>Lens</span> &middot; {escape(title)}</h1>
<div class="sub">Generated by SpendLens. Savings figures use illustrative assumptions.</div></div>
<span class="badge">v{__version__} &middot; runs locally, no data leaves your machine</span></div>
<div class="grid k4">{kpis}</div>
<div class="grid c2" style="margin-top:16px">
 <div class="card"><h2>Spend by category</h2>{_donut(a.categories)}</div>
 <div class="card"><h2>Monthly spend</h2>{_line(a.monthly)}</div>
</div>
{class_card}{price_card}{trend_card}{contract_card}
<div class="grid c2" style="margin-top:16px">
 <div class="card"><h2>Top suppliers (after merging duplicates)</h2>
  <table><tr><th>Supplier</th><th class="n">Spend</th><th class="n">Cumul.</th></tr>{sup_rows}</table></div>
 <div class="card"><h2>Duplicate supplier clusters</h2>
  <table><tr><th>Canonical name and variants</th><th class="n">Spend</th></tr>{dup_rows}</table></div>
</div>
<div class="grid c2" style="margin-top:16px">
 <div class="card"><h2>Supplier concentration (HHI)</h2>
  <table><tr><th>Category</th><th class="n">HHI</th><th>Read</th></tr>{hhi_rows}</table></div>
 <div class="card"><h2>Savings opportunity</h2>
  <div class="big">{money(a.savings_total)}</div>
  <div class="sub" style="margin-bottom:10px">about {sav_pct:.1f}% of spend &middot;
   tail = {a.tail_suppliers} suppliers, {tail_pct:.0f}% of spend</div>
  <table>{sav_rows}</table></div>
</div>
<div class="foot">Tail = suppliers that together make up the bottom 20% of spend. HHI &gt; 2500 means a
category depends on very few suppliers. Short terms = share of spend paid in under 45 days
({a.short_terms_pct:.0f}% here). Savings levers can overlap (a tail supplier may also be the dear one),
so read the total as an upper-end sizing, not a sum to bank.</div>
</div></body></html>"""
