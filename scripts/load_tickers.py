"""
load_tickers.py
Descarga el universo de tickers desde los archivos publicos de NASDAQ Trader
y los guarda en la coleccion `tickers` de MongoDB.

Fuentes:
  - nasdaqlisted.txt  -> acciones y ETFs listados en NASDAQ
  - otherlisted.txt   -> acciones y ETFs listados en NYSE, AMEX, NYSE Arca

Ejecutar: python scripts/load_tickers.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import requests
import pandas as pd
from io import StringIO
from pymongo import UpdateOne
from setup_db import get_db

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL  = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

EXCHANGE_MAP = {
    "A": "AMEX",
    "N": "NYSE",
    "P": "NYSE Arca",
    "Z": "BATS",
    "V": "IEX",
}


def _clean_symbol(symbol: str) -> str:
    """Convierte notacion NASDAQ (BRK.B) a notacion yfinance (BRK-B)."""
    return symbol.strip().replace(".", "-")


def _is_valid_symbol(symbol: str) -> bool:
    """Filtra warrants ($), indices (^) y simbolos vacios."""
    return bool(symbol) and "$" not in symbol and "^" not in symbol


def fetch_nasdaq_listed() -> list[dict]:
    print("Descargando nasdaqlisted.txt...")
    r = requests.get(NASDAQ_LISTED_URL, timeout=30)
    r.raise_for_status()

    df = pd.read_csv(StringIO(r.text), sep="|")
    # La ultima fila es "File Creation Time: ..."
    df = df[~df["Symbol"].astype(str).str.startswith("File")]
    # Solo issues reales (no test)
    df = df[df["Test Issue"] == "N"]

    tickers = []
    for _, row in df.iterrows():
        symbol = _clean_symbol(str(row["Symbol"]))
        if not _is_valid_symbol(symbol):
            continue
        tickers.append({
            "ticker":   symbol,
            "name":     str(row["Security Name"]).strip(),
            "exchange": "NASDAQ",
            "is_etf":   str(row["ETF"]).strip() == "Y",
        })
    return tickers


def fetch_other_listed() -> list[dict]:
    print("Descargando otherlisted.txt...")
    r = requests.get(OTHER_LISTED_URL, timeout=30)
    r.raise_for_status()

    df = pd.read_csv(StringIO(r.text), sep="|")
    df = df[~df["ACT Symbol"].astype(str).str.startswith("File")]
    df = df[df["Test Issue"] == "N"]

    tickers = []
    for _, row in df.iterrows():
        symbol = _clean_symbol(str(row["ACT Symbol"]))
        if not _is_valid_symbol(symbol):
            continue
        exchange = EXCHANGE_MAP.get(str(row["Exchange"]).strip(), str(row["Exchange"]).strip())
        tickers.append({
            "ticker":   symbol,
            "name":     str(row["Security Name"]).strip(),
            "exchange": exchange,
            "is_etf":   str(row["ETF"]).strip() == "Y",
        })
    return tickers


def load_tickers() -> None:
    db = get_db()

    nasdaq = fetch_nasdaq_listed()
    other  = fetch_other_listed()
    all_tickers = nasdaq + other

    # Deduplicar por ticker (NASDAQ tiene prioridad al ir primero)
    seen = set()
    unique = []
    for t in all_tickers:
        if t["ticker"] not in seen:
            seen.add(t["ticker"])
            unique.append(t)

    print(f"Total tickers unicos: {len(unique)} "
          f"({sum(t['is_etf'] for t in unique)} ETFs, "
          f"{sum(not t['is_etf'] for t in unique)} acciones)")

    # Upsert en MongoDB
    # $setOnInsert garantiza que capital_com y pepperstone no se sobreescriban
    # si ya existen (podrian haber sido actualizados por otro proceso)
    ops = [
        UpdateOne(
            {"ticker": t["ticker"]},
            {
                "$set": {
                    "name":     t["name"],
                    "exchange": t["exchange"],
                    "is_etf":   t["is_etf"],
                },
                "$setOnInsert": {
                    "capital_com": False,
                    "pepperstone": False,
                },
            },
            upsert=True,
        )
        for t in unique
    ]

    result = db.tickers.bulk_write(ops, ordered=False)
    print(f"Insertados: {result.upserted_count} | Actualizados: {result.modified_count}")


if __name__ == "__main__":
    load_tickers()
