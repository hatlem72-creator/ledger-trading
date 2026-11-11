#!/usr/bin/env python3
"""Fetch closing prices and FX, update state.json, append a history point.

Intended to run on weekdays after US markets close (after 22:15 Europe/Oslo).
Does not place trades. If a price cannot be fetched, the previous price is kept.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")
Q = Decimal("0.01")


def nok(x: Decimal) -> Decimal:
    return x.quantize(Q, rounding=ROUND_HALF_UP)


def fetch(url: str, timeout: int = 20) -> bytes | None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MarketLedger/1.0; +https://github.com/hatlem72-creator/ledger-trading)",
            "Accept": "application/json,text/html,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:
        print(f"fetch failed: {url} ({e})", file=sys.stderr)
        return None


def norges_bank_fx() -> dict | None:
    url = "https://data.norges-bank.no/api/data/EXR/B.USD+EUR+DKK.NOK.SP?lastNObservations=1&format=sdmx-json"
    body = fetch(url)
    if not body:
        return None
    data = json.loads(body)
    # values are ordered DKK, USD, EUR as in previous fetch; parse properly
    series = data["data"]["dataSets"][0]["series"]
    dims = data["data"]["structure"]["dimensions"]["series"]
    bases = [v["id"] for v in next(d["values"] for d in dims if d["id"] == "BASE_CUR")]
    # series keys like 0:0:0:0 — second index is BASE_CUR
    rates = {}
    for key, obj in series.items():
        parts = key.split(":")
        # find BASE_CUR position
        base_pos = next(i for i, d in enumerate(dims) if d["id"] == "BASE_CUR")
        cur = bases[int(parts[base_pos])] if len(bases) > int(parts[base_pos]) else None
        val = float(obj["observations"]["0"][0])
        if cur == "DKK":
            rates["DKKNOK"] = val / 100.0  # quoted per 100
        elif cur:
            rates[f"{cur}NOK"] = val
    meta_time = data["meta"].get("prepared")
    obs = data["data"]["structure"]["dimensions"]["observation"][0]["values"][0]["id"]
    return {
        "USDNOK": rates.get("USDNOK"),
        "EURNOK": rates.get("EURNOK"),
        "DKKNOK": rates.get("DKKNOK"),
        "as_of_date": obs,
        "source": "Norges Bank, offisielle midtkurser",
        "source_url": url,
        "fetched_at": datetime.now(OSLO).isoformat(timespec="seconds"),
        "prepared": meta_time,
    }


def yahoo_price(ticker: str) -> tuple[float, str] | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
    body = fetch(url)
    if not body:
        return None
    try:
        chart = json.loads(body)["chart"]["result"][0]
        meta = chart["meta"]
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        if price is None:
            return None
        ts = meta.get("regularMarketTime")
        if ts:
            when = datetime.fromtimestamp(ts, OSLO).isoformat(timespec="seconds")
        else:
            when = datetime.now(OSLO).isoformat(timespec="seconds")
        return float(price), when
    except Exception as e:
        print(f"yahoo parse failed for {ticker}: {e}", file=sys.stderr)
        return None


def recompute(state: dict, fx_rate_usd: Decimal) -> None:
    def side(acc: dict, use_fx: bool) -> None:
        market = Decimal("0")
        for h in acc["holdings"]:
            if use_fx and h["currency"] != "NOK":
                unit = nok(Decimal(str(h["current_price_local"])) * fx_rate_usd)
                h["fx_to_nok"] = float(fx_rate_usd)
            else:
                unit = nok(Decimal(str(h["current_price_local"])))
            h["current_price_nok"] = float(unit)
            mv = nok(Decimal(h["qty"]) * unit)
            h["market_value_nok"] = float(mv)
            cost = nok(Decimal(str(h["cost_basis_nok"])))
            h["unrealized_pl_nok"] = float(nok(mv - cost))
            market += mv
        cash = nok(Decimal(str(acc["cash_nok"])))
        total = nok(cash + market)
        start = nok(Decimal(str(acc["start_cash_nok"])))
        acc["market_value_nok"] = float(market)
        acc["total_value_nok"] = float(total)
        acc["return_nok"] = float(nok(total - start))
        acc["return_pct"] = float(nok((total / start - 1) * Decimal("100")))

    side(state["accounts"]["ASK"], False)
    side(state["accounts"]["IKZ"], True)
    ask, ikz = state["accounts"]["ASK"], state["accounts"]["IKZ"]
    cash = nok(Decimal(str(ask["cash_nok"])) + Decimal(str(ikz["cash_nok"])))
    market = nok(Decimal(str(ask["market_value_nok"])) + Decimal(str(ikz["market_value_nok"])))
    total = nok(cash + market)
    start = Decimal("100000")
    state["combined"] = {
        "start_cash_nok": 100000.0,
        "cash_nok": float(cash),
        "market_value_nok": float(market),
        "total_value_nok": float(total),
        "return_nok": float(nok(total - start)),
        "return_pct": float(nok((total / start - 1) * Decimal("100"))),
    }


def append_history(state: dict, kind: str, when: datetime) -> None:
    point = {
        "date": when.date().isoformat(),
        "time": when.isoformat(timespec="seconds"),
        "kind": kind,
        "combined": dict(state["combined"]),
        "ASK": {
            "cash_nok": state["accounts"]["ASK"]["cash_nok"],
            "market_value_nok": state["accounts"]["ASK"]["market_value_nok"],
            "total_value_nok": state["accounts"]["ASK"]["total_value_nok"],
            "return_nok": state["accounts"]["ASK"]["return_nok"],
            "return_pct": state["accounts"]["ASK"]["return_pct"],
        },
        "IKZ": {
            "cash_nok": state["accounts"]["IKZ"]["cash_nok"],
            "market_value_nok": state["accounts"]["IKZ"]["market_value_nok"],
            "total_value_nok": state["accounts"]["IKZ"]["total_value_nok"],
            "return_nok": state["accounts"]["IKZ"]["return_nok"],
            "return_pct": state["accounts"]["IKZ"]["return_pct"],
        },
    }
    hist = list(state.get("history") or [])
    # replace same-date close/update, keep opening
    hist = [p for p in hist if not (p.get("date") == point["date"] and p.get("kind") == kind)]
    hist.append(point)
    hist.sort(key=lambda p: (p["date"], p["time"]))
    state["history"] = hist


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: update_prices.py STATE.json", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    state = json.loads(path.read_text(encoding="utf-8"))
    now = datetime.now(OSLO)
    fx = norges_bank_fx()
    if fx and fx.get("USDNOK"):
        state["fx"].update({k: v for k, v in fx.items() if v is not None})
        print(f"FX USDNOK={fx['USDNOK']} as of {fx['as_of_date']}")
    else:
        print("keeping previous FX rates", file=sys.stderr)
    usd = Decimal(str(state["fx"]["USDNOK"]))

    notes = []
    for acc_id, acc in state["accounts"].items():
        for h in acc["holdings"]:
            got = yahoo_price(h["ticker"])
            if not got:
                notes.append(f"{h['ticker']}: beholdt forrige kurs")
                continue
            price, when = got
            h["current_price_local"] = price
            h["price_timestamp"] = when
            h["price_source"] = f"Yahoo Finance chart API ({h['ticker']})"
            h["price_note"] = f"Hentet {when} Europe/Oslo"
            print(f"{h['ticker']} -> {price} {h['currency']} at {when}")
    recompute(state, usd)
    state["updated_at"] = now.isoformat(timespec="seconds")
    state["prices_as_of_note"] = (
        "Kurser hentet "
        + now.strftime("%d.%m.%Y kl. %H:%M")
        + " Europe/Oslo. "
        + (" ".join(notes) if notes else "Alle papirer fikk ny kurs.")
    )
    append_history(state, "close", now)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"updated {path}; total {state['combined']['total_value_nok']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
