"""Render an Analysis as a single self-contained HTML dashboard (no JS, no CDN)."""

from __future__ import annotations

from html import escape

from .analyze import Analysis


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
"""


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

    sav_rows = "".join(
        f"<tr><td>{escape(k)}</td><td class='n'>{money(v)}</td></tr>" for k, v in a.savings.items())

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>Spend<span>Lens</span> &middot; {escape(title)}</h1>
<div class="sub">Generated by SpendLens. Savings figures use illustrative assumptions.</div>
<div class="grid k4">{kpis}</div>
<div class="grid c2" style="margin-top:16px">
 <div class="card"><h2>Spend by category</h2>{_bars(a.categories[:8])}</div>
 <div class="card"><h2>Monthly spend</h2>{_line(a.monthly)}</div>
</div>
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
({a.short_terms_pct:.0f}% here).</div>
</div></body></html>"""
