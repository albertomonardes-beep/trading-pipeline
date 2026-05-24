"""
fetch_weekly_snapshot.py
Para cada ticker en la coleccion `tickers`, descarga:
  - Precio semanal, volumen semanal
  - EMA21, SMA50, SMA200 (calculados desde historico semanal, solo se guarda el valor actual)
  - Sector, subsector, market cap
  - Disponibilidad en Capital.com y Pepperstone (lookup en CSV locales)
  - Fundamentales trimestrales: revenue, earnings, FCF (ultimos 3 trimestres)
  - Metricas: ROE, P/E, PEG, Debt/Equity, Current Ratio
  - Crecimientos: revenue, earnings, FCF

Resultado: coleccion `weekly_snapshot` en MongoDB, un documento por ticker.

Ejecutar:
  python scripts/fetch_weekly_snapshot.py            # todos los tickers
  python scripts/fetch_weekly_snapshot.py --test 50  # solo 50 tickers (para pruebas)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import time
import argparse
import pandas as pd
import yfinance as yf
from datetime import datetime
from pymongo import UpdateOne
from setup_db import get_db

# --- Configuracion ---
BATCH_SIZE            = 100   # tickers por lote en descarga de precios
DELAY_BETWEEN_BATCHES = 5     # segundos entre lotes (respetar rate limit de Yahoo)
DELAY_FUNDAMENTALS    = 1.5   # segundos entre llamadas individuales de fundamentales
RETRY_WAIT            = 20    # segundos de espera al detectar rate limit
MAX_RETRIES           = 2     # reintentos por ticker ante respuesta vacia
HISTORY_PERIOD        = "1y"  # suficiente para calcular SMA200 diaria (~252 dias habiles)
INTERVAL              = "1d"

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


# ---------------------------------------------------------------------------
# Brokers
# ---------------------------------------------------------------------------

def load_broker_sets() -> tuple[set, set]:
    """Lee los CSV locales y devuelve sets de tickers disponibles en cada broker."""
    capital_com = set()
    pepperstone  = set()

    cap_path = os.path.join(DATA_DIR, "capital_com_list.csv")
    pep_path = os.path.join(DATA_DIR, "pepperstone_list.csv")

    if os.path.exists(cap_path):
        df = pd.read_csv(cap_path)
        if "ticker" in df.columns:
            capital_com = set(df["ticker"].dropna().str.upper().tolist())

    if os.path.exists(pep_path):
        df = pd.read_csv(pep_path)
        if "ticker" in df.columns:
            pepperstone = set(df["ticker"].dropna().str.upper().tolist())

    return capital_com, pepperstone


# ---------------------------------------------------------------------------
# Indicadores tecnicos
# ---------------------------------------------------------------------------

def calculate_indicators(closes: pd.Series) -> tuple:
    """
    Calcula EMA21, SMA50 y SMA200 sobre cierres semanales.
    Devuelve (ema21, sma50, sma200) o (None, None, None) si no hay suficientes datos.
    """
    if len(closes) < 21:
        return None, None, None

    ema21 = closes.ewm(span=21, adjust=False).mean().iloc[-1]
    sma50  = closes.rolling(50).mean().iloc[-1]  if len(closes) >= 50  else None
    sma200 = closes.rolling(200).mean().iloc[-1] if len(closes) >= 200 else None

    def _round(v):
        return round(float(v), 4) if v is not None and not pd.isna(v) else None

    return _round(ema21), _round(sma50), _round(sma200)


# ---------------------------------------------------------------------------
# Fundamentales
# ---------------------------------------------------------------------------

def _get_annual_values(df: pd.DataFrame, row_name: str, n: int = 3) -> list | None:
    """
    Extrae los ultimos n valores anuales de una fila del estado financiero.
    Devuelve lista con valores en MM USD (mas reciente primero), o None.
    """
    if df is None or df.empty or row_name not in df.index:
        return None
    series = df.loc[row_name].dropna()
    if series.empty:
        return None
    values = series.head(n).tolist()
    return [round(v / 1_000_000, 2) for v in values]


def fetch_fundamentals(symbol: str) -> dict:
    """
    Descarga datos fundamentales de un ticker via yfinance.
    Reintenta hasta MAX_RETRIES veces si Yahoo devuelve respuesta vacia (rate limit suave).
    Devuelve un dict con los campos disponibles; campos no disponibles se omiten.
    """
    for attempt in range(MAX_RETRIES + 1):
        result = {}
        try:
            t    = yf.Ticker(symbol)
            info = t.info or {}

            # Respuesta vacia = rate limit suave → esperar y reintentar
            if not info and attempt < MAX_RETRIES:
                print(f"    [retry {attempt+1}] {symbol} — respuesta vacia, esperando {RETRY_WAIT}s")
                time.sleep(RETRY_WAIT)
                continue

            # --- Datos de info ---
            def _safe(key, divisor=1, decimals=4):
                v = info.get(key)
                if v is None or not isinstance(v, (int, float)):
                    return None
                return round(v / divisor, decimals)

            result["sector"]        = info.get("sector")   or None
            result["industry"]      = info.get("industry") or None
            result["market_cap"]    = _safe("marketCap", divisor=1_000_000, decimals=2)
            result["pe"]            = _safe("trailingPE")
            result["peg"]           = _safe("pegRatio")
            result["roe"]           = _safe("returnOnEquity")
            result["debt_equity"]   = _safe("debtToEquity")
            result["current_ratio"] = _safe("currentRatio")

            # --- Income statement anual ---
            try:
                stmt = t.income_stmt
            except AttributeError:
                stmt = t.financials  # compatibilidad versiones anteriores

            revenue  = _get_annual_values(stmt, "Total Revenue")
            earnings = _get_annual_values(stmt, "Net Income")
            if revenue:
                result["revenue"] = revenue
            if earnings:
                result["earnings"] = earnings

            # --- Cash flow anual: FCF = OCF - |CapEx| ---
            try:
                cf = t.cashflow
                if cf is not None and not cf.empty:
                    ocf_key   = "Operating Cash Flow"
                    capex_key = "Capital Expenditure"
                    if ocf_key in cf.index and capex_key in cf.index:
                        ocf   = cf.loc[ocf_key].dropna()
                        capex = cf.loc[capex_key].dropna()
                        common_dates = ocf.index.intersection(capex.index)[:3]
                        if len(common_dates) > 0:
                            fcf = [
                                round((ocf[d] + abs(capex[d])) / 1_000_000, 2)
                                for d in common_dates
                            ]
                            result["fcf"] = fcf
            except Exception:
                pass

            return result

        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT)
                continue

    return result


# ---------------------------------------------------------------------------
# Calculos de crecimiento
# ---------------------------------------------------------------------------

def calc_growth(values: list) -> float | None:
    """
    Calcula el crecimiento porcentual desde el trimestre mas antiguo al mas reciente.
    values[0] = mas reciente, values[-1] = mas antiguo.
    """
    if not values or len(values) < 2:
        return None
    newest = values[0]
    oldest = values[-1]
    if oldest is None or oldest == 0:
        return None
    return round(((newest - oldest) / abs(oldest)) * 100, 2)


# ---------------------------------------------------------------------------
# Procesamiento por lotes
# ---------------------------------------------------------------------------

def process_batch(
    batch_tickers: list[dict],
    capital_com_set: set,
    pepperstone_set: set,
    db,
) -> int:
    """
    Procesa un lote de tickers:
      1. Descarga datos de precios en bulk (una sola llamada a yfinance).
      2. Para cada ticker, descarga fundamentales individualmente.
      3. Hace upsert en MongoDB.
    """
    symbols = [t["ticker"] for t in batch_tickers]
    ticker_meta = {t["ticker"]: t for t in batch_tickers}

    # --- Descarga de precios en bulk ---
    bulk_data   = None
    is_multi    = len(symbols) > 1

    try:
        bulk_data = yf.download(
            symbols if is_multi else symbols[0],
            period=HISTORY_PERIOD,
            interval=INTERVAL,
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        print(f"    [warn] bulk download fallido: {e}")

    today = datetime.utcnow().strftime("%Y-%m-%d")
    ops   = []

    for symbol in symbols:
        meta = ticker_meta.get(symbol, {})

        doc = {
            "ticker":      symbol,
            "name":        meta.get("name"),
            "exchange":    meta.get("exchange"),
            "is_etf":      meta.get("is_etf", False),
            "capital_com": symbol.upper() in capital_com_set,
            "pepperstone": symbol.upper() in pepperstone_set,
            "updated_at":  today,
        }

        # --- Precio e indicadores ---
        try:
            if bulk_data is not None and not bulk_data.empty:
                if is_multi:
                    closes  = bulk_data["Close"][symbol].dropna()
                    volumes = bulk_data["Volume"][symbol].dropna()
                else:
                    closes  = bulk_data["Close"].dropna()
                    volumes = bulk_data["Volume"].dropna()

                if not closes.empty:
                    doc["price"]         = round(float(closes.iloc[-1]), 4)
                    last_vol      = volumes.iloc[-1]
                    doc["volume"] = int(last_vol) if not pd.isna(last_vol) else None

                    ema21, sma50, sma200 = calculate_indicators(closes)
                    doc["ema21"]  = ema21
                    doc["sma50"]  = sma50
                    doc["sma200"] = sma200
        except Exception:
            pass

        # --- Fundamentales ---
        time.sleep(DELAY_FUNDAMENTALS)
        fundamentals = fetch_fundamentals(symbol)
        doc.update(fundamentals)

        # --- Crecimientos ---
        for field in ("revenue", "earnings", "fcf"):
            if doc.get(field):
                doc[f"{field}_growth"] = calc_growth(doc[field])

        ops.append(UpdateOne({"ticker": symbol}, {"$set": doc}, upsert=True))

    if ops:
        db.weekly_snapshot.bulk_write(ops, ordered=False)

    return len(ops)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(batch_size: int = BATCH_SIZE, test_n: int | None = None) -> None:
    db = get_db()
    capital_com_set, pepperstone_set = load_broker_sets()

    # Leer tickers desde MongoDB (con metadata de nombre y exchange)
    cursor = db.tickers.find({}, {"ticker": 1, "name": 1, "exchange": 1, "is_etf": 1})
    all_tickers = list(cursor)

    if test_n:
        all_tickers = all_tickers[:test_n]

    total = len(all_tickers)
    print(f"Iniciando snapshot para {total} tickers "
          f"(lotes de {batch_size}, delay {DELAY_BETWEEN_BATCHES}s)...")

    processed = 0
    for i in range(0, total, batch_size):
        batch = all_tickers[i : i + batch_size]
        n = process_batch(batch, capital_com_set, pepperstone_set, db)
        processed += n
        pct = round(processed / total * 100, 1)
        print(f"  {processed}/{total} ({pct}%) — ultimo: {batch[-1]['ticker']}")
        if i + batch_size < total:
            time.sleep(DELAY_BETWEEN_BATCHES)

    print("Snapshot semanal completado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descarga snapshot semanal de acciones y ETFs.")
    parser.add_argument(
        "--test", type=int, default=None,
        metavar="N",
        help="Procesar solo los primeros N tickers (para pruebas).",
    )
    parser.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE,
        help=f"Tickers por lote en descarga de precios (default: {BATCH_SIZE}).",
    )
    args = parser.parse_args()
    run(batch_size=args.batch_size, test_n=args.test)
