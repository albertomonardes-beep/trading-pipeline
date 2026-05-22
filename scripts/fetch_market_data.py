"""
fetch_market_data.py
Descarga datos semanales de indices de mercado y ETFs sectoriales,
calcula indicadores tecnicos y los guarda en la coleccion `market_data`.

Instrumentos:
  - Mercado amplio: SPY, QQQ, DIA, IWM
  - Volatilidad:    ^VIX
  - Sectores SPDR:  XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLU, XLRE, XLC, XLB

Ejecutar: python scripts/fetch_market_data.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import yfinance as yf
import pandas as pd
from datetime import datetime
from pymongo import UpdateOne
from setup_db import get_db

MARKET_INSTRUMENTS = {
    # Mercado amplio
    "SPY":  {"name": "S&P 500 ETF",          "type": "index"},
    "QQQ":  {"name": "Nasdaq 100 ETF",        "type": "index"},
    "DIA":  {"name": "Dow Jones ETF",         "type": "index"},
    "IWM":  {"name": "Russell 2000 ETF",      "type": "index"},
    # Volatilidad
    "^VIX": {"name": "CBOE Volatility Index", "type": "volatility"},
    # Sectores SPDR
    "XLK":  {"name": "Technology",            "type": "sector"},
    "XLF":  {"name": "Financials",            "type": "sector"},
    "XLE":  {"name": "Energy",                "type": "sector"},
    "XLV":  {"name": "Health Care",           "type": "sector"},
    "XLI":  {"name": "Industrials",           "type": "sector"},
    "XLY":  {"name": "Consumer Discretionary","type": "sector"},
    "XLP":  {"name": "Consumer Staples",      "type": "sector"},
    "XLU":  {"name": "Utilities",             "type": "sector"},
    "XLRE": {"name": "Real Estate",           "type": "sector"},
    "XLC":  {"name": "Communication Services","type": "sector"},
    "XLB":  {"name": "Materials",             "type": "sector"},
}

HISTORY_PERIOD = "1y"
INTERVAL       = "1d"


def calculate_indicators(closes: pd.Series) -> dict:
    """Calcula EMA21, SMA50 y SMA200 sobre cierres semanales."""
    result = {}
    if len(closes) < 21:
        return result

    def _round(v):
        return round(float(v), 4) if v is not None and not pd.isna(v) else None

    result["ema21"] = _round(closes.ewm(span=21, adjust=False).mean().iloc[-1])
    if len(closes) >= 50:
        result["sma50"]  = _round(closes.rolling(50).mean().iloc[-1])
    if len(closes) >= 200:
        result["sma200"] = _round(closes.rolling(200).mean().iloc[-1])

    return result


def above_sma(price: float | None, sma: float | None) -> bool | None:
    """True si el precio esta por encima de la SMA, None si faltan datos."""
    if price is None or sma is None:
        return None
    return price > sma


def run() -> None:
    db     = get_db()
    today  = datetime.utcnow().strftime("%Y-%m-%d")
    tickers = list(MARKET_INSTRUMENTS.keys())

    print(f"Descargando datos para {len(tickers)} instrumentos de mercado...")

    try:
        raw = yf.download(
            tickers,
            period=HISTORY_PERIOD,
            interval=INTERVAL,
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        print(f"Error en descarga: {e}")
        return

    if raw is None or raw.empty:
        print("Sin datos recibidos.")
        return

    ops = []

    for ticker in tickers:
        meta = MARKET_INSTRUMENTS[ticker]

        try:
            closes  = raw["Close"][ticker].dropna()
            volumes = raw["Volume"][ticker].dropna() if "Volume" in raw else pd.Series(dtype=float)
        except (KeyError, TypeError):
            print(f"  [warn] sin datos para {ticker}")
            continue

        if closes.empty:
            print(f"  [warn] closes vacios para {ticker}")
            continue

        price = round(float(closes.iloc[-1]), 4)
        indicators = calculate_indicators(closes)

        doc = {
            "ticker":     ticker,
            "name":       meta["name"],
            "type":       meta["type"],
            "price":      price,
            "updated_at": today,
            **indicators,
        }

        # Volumen (no aplica para VIX)
        if not volumes.empty:
            last_vol = volumes.iloc[-1]
            doc["volume"] = int(last_vol) if not pd.isna(last_vol) else None

        # Flags de tendencia: precio vs medias moviles
        doc["above_sma50"]  = above_sma(price, indicators.get("sma50"))
        doc["above_sma200"] = above_sma(price, indicators.get("sma200"))
        doc["above_ema21"]  = above_sma(price, indicators.get("ema21"))

        # Variacion semanal (%)
        if len(closes) >= 2:
            prev = float(closes.iloc[-2])
            if prev != 0:
                doc["weekly_change_pct"] = round((price - prev) / prev * 100, 2)

        ops.append(UpdateOne({"ticker": ticker}, {"$set": doc}, upsert=True))
        print(f"  {ticker}: ${price} | ema21={indicators.get('ema21')} "
              f"sma50={indicators.get('sma50')} sma200={indicators.get('sma200')}")

    if ops:
        result = db.market_data.bulk_write(ops, ordered=False)
        print(f"\nActualizados: {result.upserted_count + result.modified_count} instrumentos.")
    else:
        print("Sin operaciones a ejecutar.")


if __name__ == "__main__":
    run()
