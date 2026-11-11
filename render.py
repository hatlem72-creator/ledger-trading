#!/usr/bin/env python3
"""Render the virtual trading ledger as a newspaper-style HTML page from state.json."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")
MONTHS = [
    "",
    "januar",
    "februar",
    "mars",
    "april",
    "mai",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "desember",
]
WEEKDAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]


def load_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts).astimezone(OSLO)


def format_date_long(dt: datetime) -> str:
    return f"{WEEKDAYS[dt.weekday()]} {dt.day}. {MONTHS[dt.month]} {dt.year}"


def format_clock(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def nok(n: float, signed: bool = False) -> str:
    neg = n < 0
    s = f"{abs(n):,.2f}"
    s = s.replace(",", " ").replace(".", ",")
    # 1 234,56 — python uses 1,234.56 then we swap; for 1234.56 -> 1,234.56 in US
    # safer:
    sign = "−" if neg else ("+" if signed and n > 0 else "")
    whole, frac = f"{abs(n):.2f}".split(".")
    parts = []
    while whole:
        parts.append(whole[-3:])
        whole = whole[:-3]
    whole = "\u00a0".join(reversed(parts))
    return f"{sign}{whole},{frac}\u00a0kr"


def pct(n: float, signed: bool = True) -> str:
    sign = "−" if n < 0 else ("+" if signed and n > 0 else "")
    return f"{sign}{abs(n):.2f}%".replace(".", ",")


def cls_pl(n: float) -> str:
    if n > 0:
        return "up"
    if n < 0:
        return "down"
    return "flat"


def price_cell(currency: str, local: float, nok_price: float) -> str:
    if currency == "USD":
        loc = f"{local:.2f}".replace(".", ",")
        return f"{nok(nok_price)} <span class='ccy'>({loc}\u00a0USD)</span>"
    return nok(nok_price)


def ensure_history(state: dict) -> dict:
    if state.get("history"):
        return state
    combined = state["combined"]
    accounts = state["accounts"]
    opened = state.get("created_at") or state.get("updated_at")
    state["history"] = [
        {
            "date": parse_iso(opened).date().isoformat(),
            "time": opened,
            "kind": "opening",
            "combined": {
                "cash_nok": combined["cash_nok"],
                "market_value_nok": combined["market_value_nok"],
                "total_value_nok": combined["total_value_nok"],
                "return_nok": combined["return_nok"],
                "return_pct": combined["return_pct"],
            },
            "ASK": {
                "cash_nok": accounts["ASK"]["cash_nok"],
                "market_value_nok": accounts["ASK"]["market_value_nok"],
                "total_value_nok": accounts["ASK"]["total_value_nok"],
                "return_nok": accounts["ASK"]["return_nok"],
                "return_pct": accounts["ASK"]["return_pct"],
            },
            "IKZ": {
                "cash_nok": accounts["IKZ"]["cash_nok"],
                "market_value_nok": accounts["IKZ"]["market_value_nok"],
                "total_value_nok": accounts["IKZ"]["total_value_nok"],
                "return_nok": accounts["IKZ"]["return_nok"],
                "return_pct": accounts["IKZ"]["return_pct"],
            },
        }
    ]
    return state


def holdings_rows(holdings: list[dict]) -> str:
    rows = []
    for h in holdings:
        pl = h.get("unrealized_pl_nok") or 0.0
        rows.append(
            "<tr>"
            f"<td>{esc(h['ticker'])}</td>"
            f"<td>{esc(h['name'])}</td>"
            f"<td class='num'>{h['qty']}</td>"
            f"<td class='num'>{price_cell(h['currency'], h['buy_price_local'], h['buy_price_nok'])}</td>"
            f"<td class='num'>{price_cell(h['currency'], h['current_price_local'], h['current_price_nok'])}</td>"
            f"<td class='num'>{nok(h['market_value_nok'])}</td>"
            f"<td class='num {cls_pl(pl)}'>{nok(pl)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def rationale_list(holdings: list[dict]) -> str:
    items = "".join(
        f"<li><span class='tick'>{esc(h['ticker'])}</span> — {esc(h['rationale'])}</li>"
        for h in holdings
    )
    return f"<ul class='why'>{items}</ul>"


def trade_rows(trades: list[dict]) -> str:
    rows = []
    for t in trades:
        side = "Kjøp" if t["side"] == "buy" else "Salg"
        dt = parse_iso(t["time"])
        when = dt.strftime("%d.%m.%Y") + " kl.\u00a0" + format_clock(dt)
        realized = t.get("realized_pl_nok")
        if realized is None:
            real_html = "—"
            real_cls = "flat"
        else:
            real_html = nok(realized)
            real_cls = cls_pl(realized)
        rows.append(
            f"<tr data-account='{esc(t['account'])}'>"
            f"<td>{esc(when)}</td>"
            f"<td>{esc(t['account'])}</td>"
            f"<td>{esc(side)}</td>"
            f"<td>{esc(t['ticker'])} <span class='muted'>· {esc(t['name'])}</span></td>"
            f"<td class='num'>{t['qty']}</td>"
            f"<td class='num'>{price_cell(t['currency'], t['price_local'], t['price_nok'])}</td>"
            f"<td class='num'>{nok(t['fee_nok'])}</td>"
            f"<td class='num'>{nok(t['total_nok'])}</td>"
            f"<td class='num {real_cls}'>{real_html}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def chart_svg(history: list[dict], start: float = 100_000.0) -> str:
    values = [float(p["combined"]["total_value_nok"]) for p in history]
    labels = [p["date"] for p in history]
    if not values:
        return "<p class='note'>Ingen historikk ennå.</p>"
    w, h = 1000, 280
    pad_l, pad_r, pad_t, pad_b = 72, 24, 20, 44
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b
    lo = min(values + [start])
    hi = max(values + [start])
    span = max(hi - lo, 500.0)
    lo -= span * 0.12
    hi += span * 0.12
    span = hi - lo

    def x(i: int, n: int) -> float:
        if n <= 1:
            return pad_l + plot_w * 0.5
        return pad_l + plot_w * (i / (n - 1))

    def y(v: float) -> float:
        return pad_t + plot_h * (1 - (v - lo) / span)

    n = len(values)
    # baseline 100 000
    y0 = y(start)
    pts = " ".join(f"{x(i,n):.1f},{y(v):.1f}" for i, v in enumerate(values))
    circles = "\n".join(
        f'<circle cx="{x(i,n):.1f}" cy="{y(v):.1f}" r="4.5" fill="#111"/>'
        for i, v in enumerate(values)
    )
    # date labels
    label_els = []
    for i, (lab, v) in enumerate(zip(labels, values)):
        # 2026-11-11 -> 11.11
        parts = lab.split("-")
        short = f"{parts[2]}.{parts[1]}" if len(parts) == 3 else lab
        label_els.append(
            f'<text x="{x(i,n):.1f}" y="{h-14}" text-anchor="middle" class="chart-lab">{short}</text>'
        )
    # y labels
    ticks = [lo + span * k / 4 for k in range(5)]
    tick_els = []
    grid = []
    for t in ticks:
        yy = y(t)
        grid.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{w-pad_r}" y2="{yy:.1f}" class="grid"/>')
        tick_els.append(
            f'<text x="{pad_l-10}" y="{yy+4:.1f}" text-anchor="end" class="chart-lab">{nok(t).replace(chr(160)+"kr","")}</text>'
        )
    caption = (
        "Første målepunkt er åpningen 11. november 2026. Kurven fylles ut med daglige sluttkurser."
        if n == 1
        else "Totalverdi av ASK og IKZ etter hver oppdatering, i norske kroner."
    )
    return f"""
<figure class="chart">
  <svg viewBox="0 0 {w} {h}" role="img" aria-label="Verdi over tid">
    <line x1="{pad_l}" y1="{y0:.1f}" x2="{w-pad_r}" y2="{y0:.1f}" class="baseline"/>
    <text x="{w-pad_r}" y="{y0-6:.1f}" text-anchor="end" class="chart-lab">start 100 000</text>
    {''.join(grid)}
    {''.join(tick_els)}
    <polyline points="{pts}" fill="none" stroke="#111" stroke-width="2"/>
    {circles}
    {''.join(label_els)}
  </svg>
  <figcaption>{caption}</figcaption>
</figure>
"""


def esc(s: object) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


CSS = r"""
:root{
  --paper:#fbf9f3;
  --ink:#111;
  --muted:#555;
  --faint:#777;
  --line:#c8c4b8;
  --up:#0a6b2b;
  --down:#a40e0e;
}
*{box-sizing:border-box}
html{background:var(--paper)}
body{
  max-width:1100px;
  margin:0 auto;
  padding:22px 28px 48px;
  background:var(--paper);
  color:var(--ink);
  font-family:Georgia,"Times New Roman","Liberation Serif",serif;
  line-height:1.45;
}
@font-face{
  font-family:"UnifrakturMaguntia";
  src:url("fonts/UnifrakturMaguntia.woff") format("woff");
  font-display:swap;
}
.masthead{text-align:center;padding-bottom:10px;border-bottom:4px double #111}
.masthead .meta{
  display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;
  font-size:.78rem;letter-spacing:.12em;text-transform:uppercase;
  border-bottom:1px solid #111;padding:4px 0 8px;
}
.masthead h1{
  font-family:"UnifrakturMaguntia","Old English Text MT",Georgia,serif;
  font-size:clamp(2.8rem, 9vw, 4.4rem);
  font-weight:400;line-height:1.05;margin:.16em 0 .08em;
}
.tagline{font-style:italic;font-size:1.05rem;margin:0 0 4px}
.issue{font-size:.8rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0}
.disclaimer{
  margin:0;padding:10px 0 12px;text-align:center;font-style:italic;color:#333;
  border-bottom:2px solid #111;
}
.disclaimer strong{font-style:normal;font-variant:small-caps;letter-spacing:.06em}
.banner{
  display:grid;
  grid-template-columns:repeat(4,1fr);
  border-bottom:2px solid #111;
}
.stat{text-align:center;padding:16px 10px;border-right:1px solid #111}
.stat:last-child{border-right:0}
.stat h3{margin:0 0 4px;text-transform:uppercase;letter-spacing:.14em;font-size:.78rem;font-weight:600}
.stat .big{font-size:clamp(1.35rem, 2.6vw, 2rem);font-weight:700;line-height:1.15}
.stat .sub{font-size:.85rem;color:var(--muted);margin-top:3px}
.split{display:grid;grid-template-columns:1fr 1fr;border-bottom:2px solid #111}
.account{padding:16px 18px 18px;border-right:1px solid #111}
.account:last-child{border-right:0}
.account h3{margin:0 0 2px;text-transform:uppercase;letter-spacing:.12em;font-size:1rem}
.account .lead{margin:0 0 10px;color:var(--muted);font-style:italic;font-size:.92rem}
.kpis{display:grid;grid-template-columns:1fr 1fr;gap:8px 16px}
.kpis .k{font-size:.75rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.kpis .v{font-size:1.15rem;font-weight:700}
h2{
  border-bottom:2px solid #111;
  text-transform:uppercase;
  letter-spacing:.1em;
  font-size:1.25rem;
  margin:2rem 0 .7rem;
  padding-bottom:4px;
}
.lede{font-size:1.02rem;margin:.2rem 0 1rem}
.table-wrap{width:100%;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.95rem}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{text-align:right;font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid #111}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2),th:nth-child(3),td:nth-child(3),th:nth-child(4),td.left{text-align:left}
.num{text-align:right;font-variant-numeric:tabular-nums}
.ccy{display:block;font-size:.78rem;color:var(--muted);font-style:italic}
.up{color:var(--up)}
.down{color:var(--down)}
.flat{color:var(--ink)}
.muted{color:var(--muted)}
.why{margin:.6rem 0 0;padding:0;list-style:none}
.why li{margin:0 0 .35rem;padding-left:0;font-size:.92rem}
.why .tick{font-weight:700}
.filters{display:flex;gap:0;margin:0 0 10px;border-bottom:1px solid #111}
.filters button{
  appearance:none;background:none;border:0;border-bottom:2px solid transparent;
  font:inherit;font-variant:small-caps;letter-spacing:.12em;text-transform:uppercase;
  padding:6px 14px 8px;cursor:pointer;color:#333;
}
.filters button[aria-pressed="true"]{border-bottom-color:#111;font-weight:700;color:#111}
.filters button:focus-visible{outline:2px solid #111;outline-offset:2px}
.note,.chart figcaption{color:var(--faint);font-style:italic;font-size:.9rem}
.chart{margin:8px 0 0}
.chart svg{width:100%;height:auto;display:block;background:transparent}
.chart .grid{stroke:#e0dcd0;stroke-width:1}
.chart .baseline{stroke:#111;stroke-width:1;stroke-dasharray:4 4}
.chart-lab{font-family:Georgia,"Times New Roman",serif;font-size:11px;fill:#555}
footer{
  border-top:4px double #111;
  margin-top:2.2rem;padding-top:10px;
  font-size:.8rem;text-align:center;color:#333;
}
footer p{margin:.25rem 0}
@media(max-width:800px){
  body{padding:16px 14px 36px}
  .banner{grid-template-columns:1fr 1fr}
  .stat:nth-child(odd){border-bottom:1px solid #111}
  .stat:nth-child(2){border-right:0}
  .split{grid-template-columns:1fr}
  .account{border-right:0;border-bottom:1px solid #111}
  .account:last-child{border-bottom:0}
  table{font-size:.85rem}
  th,td{padding:6px 5px}
}
@media print{
  body{padding:0;max-width:none}
  .filters{display:none}
}
"""


JS = r"""
(function(){
  const buttons = document.querySelectorAll(".filters button");
  const rows = document.querySelectorAll("#trades tbody tr");
  function apply(filter){
    buttons.forEach(b => b.setAttribute("aria-pressed", b.dataset.filter === filter ? "true" : "false"));
    rows.forEach(r => {
      const show = filter === "Alle" || r.getAttribute("data-account") === filter;
      r.hidden = !show;
    });
  }
  buttons.forEach(b => b.addEventListener("click", () => apply(b.dataset.filter)));
  apply("Alle");
})();
"""


def render(state: dict, generated_at: datetime | None = None) -> str:
    state = ensure_history(state)
    generated_at = generated_at or datetime.now(OSLO)
    opened = parse_iso(state["created_at"])
    updated = parse_iso(state.get("updated_at") or state["created_at"])
    combined = state["combined"]
    ask = state["accounts"]["ASK"]
    ikz = state["accounts"]["IKZ"]
    fx = state.get("fx") or {}
    trades = state.get("trades") or []
    history = state.get("history") or []
    date_line = format_date_long(updated)
    updated_line = f"Oppdatert {format_clock(updated)} Europe/Oslo"
    prices_note = state.get("prices_as_of_note") or ""
    usd = fx.get("USDNOK")
    usd_s = f"{usd:.4f}".replace(".", ",") if usd else "—"

    def account_block(acc: dict, key: str) -> str:
        return f"""
        <div class="account">
          <h3>{esc(acc['name'])}</h3>
          <p class="lead">{esc(acc.get('eligible') or '')} Startet med {nok(acc['start_cash_nok'])}.</p>
          <div class="kpis">
            <div><div class="k">Kontanter</div><div class="v">{nok(acc['cash_nok'])}</div></div>
            <div><div class="k">Markedsverdi</div><div class="v">{nok(acc['market_value_nok'])}</div></div>
            <div><div class="k">Totalverdi</div><div class="v">{nok(acc['total_value_nok'])}</div></div>
            <div><div class="k">Avkastning</div><div class="v {cls_pl(acc['return_nok'])}">{nok(acc['return_nok'])} <span class="sub">({pct(acc['return_pct'])})</span></div></div>
          </div>
        </div>
        """

    html = f"""<!doctype html>
<html lang="nb">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>The Market Ledger — virtuell papirhandel</title>
<style>{CSS}</style>
</head>
<body>
  <header class="masthead">
    <div class="meta">
      <span>{esc(date_line)}</span>
      <span>{esc(updated_line)}</span>
    </div>
    <h1>The Market Ledger</h1>
    <p class="tagline">Virtuell papirhandel · ASK og IKZ</p>
    <p class="issue">1. årgang · nr. 1 · virtuell utgave · ikke investeringsråd</p>
  </header>

  <p class="disclaimer"><strong>Virtuell simulering.</strong> Ingen ekte penger er satt inn, og ingen ordre er sendt til en megler. Tallene er papirhandel. Kursene er per hentetidspunktet, ikke live.</p>

  <section>
    <h2>Samlet oversikt</h2>
    <p class="lede">Begge kontoene startet med 50&nbsp;000&nbsp;kr, til sammen 100&nbsp;000&nbsp;kr. Nesten all kasse er investert («cash is trash»); det som står igjen er bare rest etter hele aksjer og 75&nbsp;kr i kurtasje per handel. Målet er å tjene mest mulig.</p>
    <div class="banner">
      <div class="stat">
        <h3>Kontanter</h3>
        <div class="big">{nok(combined['cash_nok'])}</div>
        <div class="sub">{pct(combined['cash_nok']/100000*100, signed=False)} av start</div>
      </div>
      <div class="stat">
        <h3>Markedsverdi</h3>
        <div class="big">{nok(combined['market_value_nok'])}</div>
        <div class="sub">papirer til visningskurs</div>
      </div>
      <div class="stat">
        <h3>Totalverdi</h3>
        <div class="big">{nok(combined['total_value_nok'])}</div>
        <div class="sub">kontanter + papirer</div>
      </div>
      <div class="stat">
        <h3>Avkastning</h3>
        <div class="big {cls_pl(combined['return_nok'])}">{nok(combined['return_nok'])}</div>
        <div class="sub {cls_pl(combined['return_nok'])}">{pct(combined['return_pct'])} mot 100&nbsp;000&nbsp;kr</div>
      </div>
    </div>
    <div class="split">
      {account_block(ask, "ASK")}
      {account_block(ikz, "IKZ")}
    </div>
    <p class="note">{esc(prices_note)} USD er omregnet med Norges Banks midtkurs {esc(fx.get('as_of_date') or '')}: 1&nbsp;USD = {usd_s}&nbsp;NOK.</p>
  </section>

  <section>
    <h2>Beholdning på ASK</h2>
    <p class="lede">{esc(ask.get('eligible') or '')} Kontantrest: {nok(ask['cash_nok'])}.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Ticker</th><th>Navn</th><th>Antall</th><th>Kjøpskurs</th><th>Kurs nå</th><th>Verdi</th><th>Urealisert G/T</th></tr></thead>
      <tbody>
        {holdings_rows(ask['holdings'])}
      </tbody>
    </table></div>
    {rationale_list(ask['holdings'])}
  </section>

  <section>
    <h2>Beholdning på IKZ</h2>
    <p class="lede">{esc(ikz.get('eligible') or '')} Kontantrest: {nok(ikz['cash_nok'])}.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Ticker</th><th>Navn</th><th>Antall</th><th>Kjøpskurs</th><th>Kurs nå</th><th>Verdi</th><th>Urealisert G/T</th></tr></thead>
      <tbody>
        {holdings_rows(ikz['holdings'])}
      </tbody>
    </table></div>
    {rationale_list(ikz['holdings'])}
  </section>

  <section>
    <h2>Kjøpt og solgt</h2>
    <p class="lede">Alle registrerte handler i den virtuelle loggen. Åpningshandlene ble bokført {esc(format_date_long(opened))} kl.&nbsp;{esc(format_clock(opened))} Europe/Oslo. Totalbeløpet for kjøp er kurs × antall pluss 75&nbsp;kr i kurtasje. For salg er totalbeløpet kurs × antall minus 75&nbsp;kr. Realisert gevinst eller tap vises bare på salg.</p>
    <div class="filters" role="tablist" aria-label="Filtrer handler etter konto">
      <button type="button" data-filter="Alle" aria-pressed="true">Alle ({len(trades)})</button>
      <button type="button" data-filter="ASK" aria-pressed="false">ASK ({sum(1 for t in trades if t['account']=='ASK')})</button>
      <button type="button" data-filter="IKZ" aria-pressed="false">IKZ ({sum(1 for t in trades if t['account']=='IKZ')})</button>
    </div>
    <div class="table-wrap"><table id="trades">
      <thead>
        <tr>
          <th>Dato og tid (Europe/Oslo)</th>
          <th>Konto</th>
          <th>Side</th>
          <th>Ticker og navn</th>
          <th>Antall</th>
          <th>Kurs</th>
          <th>Kurtasje</th>
          <th>Totalbeløp</th>
          <th>Realisert G/T</th>
        </tr>
      </thead>
      <tbody>
        {trade_rows(trades)}
      </tbody>
    </table></div>
  </section>

  <section>
    <h2>Verdi over tid</h2>
    <p class="lede">Totalverdi av begge kontoene, mot start på 100&nbsp;000&nbsp;kr. Nye punkt settes inn etter sluttkurser når børsene er stengt.</p>
    {chart_svg(history)}
  </section>

  <footer>
    <p>Virtuell papirhandel. Ikke investeringsråd. Ingen ekte meglerordre.</p>
    <p>Kurtasje: fast 75&nbsp;kr per kjøp og per salg. Bare hele aksjer. Siden generert {esc(format_date_long(generated_at))} kl.&nbsp;{esc(format_clock(generated_at))} Europe/Oslo.</p>
    <p>Kilder: stockanalysis.com, Norges Bank, offisielle sluttkurser. The Market Ledger er stylet etter The Portfolio Times.</p>
  </footer>
  <script>{JS}</script>
</body>
</html>
"""
    return html


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: render.py STATE.json OUT.html", file=sys.stderr)
        return 2
    state_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    state = ensure_history(load_state(state_path))
    out_path.write_text(render(state), encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
