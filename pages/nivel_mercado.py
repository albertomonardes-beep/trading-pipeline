"""
pages/nivel_mercado.py
Nivel 1 — Análisis de condiciones generales de mercado.
"""

import os
import pandas as pd
import streamlit as st
from pymongo import MongoClient

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME     = "trading"


@st.cache_resource
def get_client():
    return MongoClient(MONGODB_URI)


@st.cache_data(ttl=3600)
def load_market_data() -> dict:
    db   = get_client()[DB_NAME]
    docs = list(db.market_data.find({}, {"_id": 0}))
    return {d["ticker"]: d for d in docs}


def signal_icon(above) -> str:
    if above is True:
        return "✅"
    if above is False:
        return "❌"
    return "—"


# ── Carga de datos ──────────────────────────────────────────────────────────

st.title("🌍 Nivel Mercado")

data = load_market_data()

if not data:
    st.warning("Sin datos en MongoDB. Ejecuta primero los workflows de GitHub Actions.")
    st.stop()

# ── VIX ────────────────────────────────────────────────────────────────────

vix_doc = data.get("^VIX", {})
vix     = vix_doc.get("price")

if vix is not None:
    if vix < 15:
        vix_label = "Calma extrema"
        vix_color = "green"
    elif vix < 20:
        vix_label = "Normal"
        vix_color = "green"
    elif vix < 25:
        vix_label = "Precaución"
        vix_color = "orange"
    elif vix < 30:
        vix_label = "Miedo"
        vix_color = "red"
    else:
        vix_label = "Miedo extremo"
        vix_color = "red"
else:
    vix_label = "Sin datos"
    vix_color = "gray"

# ── Señal general ───────────────────────────────────────────────────────────

BROAD = ["SPY", "QQQ", "DIA", "IWM"]
broad_docs = [data.get(t, {}) for t in BROAD]

above_200_count = sum(
    1 for d in broad_docs if d.get("above_sma200") is True
)

if vix is not None and vix < 20 and above_200_count >= 3:
    signal       = "FAVORABLE"
    signal_color = "green"
    signal_desc  = "Condiciones favorables. VIX bajo y mercado en tendencia alcista."
elif (vix is not None and vix > 30) or above_200_count <= 1:
    signal       = "DESFAVORABLE"
    signal_color = "red"
    signal_desc  = "Condiciones adversas. VIX elevado o mercado en tendencia bajista. Evitar nuevas posiciones."
else:
    signal       = "NEUTRAL"
    signal_color = "orange"
    signal_desc  = "Condiciones mixtas. Operar con selectividad y mayor exigencia en los filtros."

st.markdown(f"### Señal general: :{signal_color}[**{signal}**]")
st.caption(signal_desc)
st.divider()

# ── Fila superior: VIX + Mercado amplio ─────────────────────────────────────

col_vix, col_broad = st.columns([1, 2])

with col_vix:
    st.subheader("VIX")
    if vix is not None:
        st.metric("VIX", f"{vix:.2f}")
        st.markdown(f":{vix_color}[**{vix_label}**]")
        wc = vix_doc.get("weekly_change_pct")
        if wc is not None:
            st.caption(f"Cambio semanal: {wc:+.2f}%")
    else:
        st.info("Sin datos de VIX")

with col_broad:
    st.subheader("Mercado amplio")
    rows = []
    for ticker in BROAD:
        d = data.get(ticker, {})
        rows.append({
            "Ticker":     ticker,
            "Nombre":     d.get("name", "—"),
            "Precio":     d.get("price"),
            "Semana (%)": d.get("weekly_change_pct"),
            "> EMA21":    signal_icon(d.get("above_ema21")),
            "> SMA50":    signal_icon(d.get("above_sma50")),
            "> SMA200":   signal_icon(d.get("above_sma200")),
        })
    df_broad = pd.DataFrame(rows)
    st.dataframe(
        df_broad,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Precio":     st.column_config.NumberColumn("Precio",     format="$%.2f"),
            "Semana (%)": st.column_config.NumberColumn("Semana (%)", format="%.2f%%"),
        },
    )

st.divider()

# ── Sectores SPDR ───────────────────────────────────────────────────────────

st.subheader("Sectores SPDR")

SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLRE", "XLC", "XLB"]

sector_rows = []
for ticker in SECTORS:
    d = data.get(ticker, {})
    sector_rows.append({
        "Ticker":     ticker,
        "Sector":     d.get("name", "—"),
        "Precio":     d.get("price"),
        "Semana (%)": d.get("weekly_change_pct"),
        "> EMA21":    signal_icon(d.get("above_ema21")),
        "> SMA50":    signal_icon(d.get("above_sma50")),
        "> SMA200":   signal_icon(d.get("above_sma200")),
    })

df_sectors = pd.DataFrame(sector_rows)
df_sectors = df_sectors.sort_values("Semana (%)", ascending=False, na_position="last")

st.dataframe(
    df_sectors,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Precio":     st.column_config.NumberColumn("Precio",     format="$%.2f"),
        "Semana (%)": st.column_config.NumberColumn("Semana (%)", format="%.2f%%"),
    },
)

updated = next((d.get("updated_at") for d in data.values() if d.get("updated_at")), None)
if updated:
    st.caption(f"Última actualización: {updated}")
