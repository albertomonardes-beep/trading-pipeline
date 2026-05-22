"""
app.py
Interfaz Streamlit para visualizar el snapshot semanal de acciones y ETFs.

Ejecutar localmente: streamlit run app.py
"""

import os
import pandas as pd
import streamlit as st
from pymongo import MongoClient

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME     = "trading"

st.set_page_config(page_title="Trading Watchlist", layout="wide")


@st.cache_resource
def get_client():
    return MongoClient(MONGODB_URI)


@st.cache_data(ttl=3600)
def load_data() -> pd.DataFrame:
    db   = get_client()[DB_NAME]
    docs = list(db.weekly_snapshot.find({}, {"_id": 0}))
    if not docs:
        return pd.DataFrame()

    rows = []
    for d in docs:
        def _pad(field, n=3):
            vals = d.get(field) or []
            return (vals + [None] * n)[:n]

        rev = _pad("revenue")
        ear = _pad("earnings")
        fcf = _pad("fcf")

        rows.append({
            "Accion":              d.get("ticker"),
            "Precio":              d.get("price"),
            "EMA21":               d.get("ema21"),
            "SMA50":               d.get("sma50"),
            "SMA200":              d.get("sma200"),
            "Sector":              d.get("sector"),
            "Sub sector":          d.get("industry"),
            "Capital.com":         d.get("capital_com", False),
            "Pepperstone":         d.get("pepperstone", False),
            "Volumen":             d.get("volume"),
            "Market Cap (MM USD)": d.get("market_cap"),
            "Ingreso A1 (MM USD)": rev[0],
            "Ingreso A2 (MM USD)": rev[1],
            "Ingreso A3 (MM USD)": rev[2],
            "Crec. Ingresos (%)":  d.get("revenue_growth"),
            "Ganancia A1 (MM USD)":ear[0],
            "Ganancia A2 (MM USD)":ear[1],
            "Ganancia A3 (MM USD)":ear[2],
            "Crec. Ganancias (%)": d.get("earnings_growth"),
            "ROE":                 d.get("roe"),
            "P/E":                 d.get("pe"),
            "PEG":                 d.get("peg"),
            "Debt/Equity":         d.get("debt_equity"),
            "Current Ratio":       d.get("current_ratio"),
            "FCF A1 (MM USD)":     fcf[0],
            "FCF A2 (MM USD)":     fcf[1],
            "FCF A3 (MM USD)":     fcf[2],
            "Crec. FCF (%)":       d.get("fcf_growth"),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

st.title("Trading Watchlist")

df = load_data()

if df.empty:
    st.warning("Sin datos. Ejecuta primero load_tickers.py y fetch_weekly_snapshot.py.")
    st.stop()

st.caption(f"{len(df):,} instrumentos cargados")

st.dataframe(df, use_container_width=True, hide_index=True)
