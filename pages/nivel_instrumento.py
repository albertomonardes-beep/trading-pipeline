"""
pages/nivel_instrumento.py
Nivel 2 — Tabla interactiva con filtros por todos los campos del snapshot semanal.
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
            "Ticker":             d.get("ticker"),
            "Nombre":             d.get("name"),
            "Exchange":           d.get("exchange"),
            "ETF":                bool(d.get("is_etf", False)),
            "Sector":             d.get("sector"),
            "Sub-sector":         d.get("industry"),
            "Capital.com":        bool(d.get("capital_com", False)),
            "Pepperstone":        bool(d.get("pepperstone", False)),
            "Precio":             d.get("price"),
            "EMA21":              d.get("ema21"),
            "SMA50":              d.get("sma50"),
            "SMA200":             d.get("sma200"),
            "Volumen":            d.get("volume"),
            "Market Cap (MM)":    d.get("market_cap"),
            "Ing. A1 (MM)":       rev[0],
            "Ing. A2 (MM)":       rev[1],
            "Ing. A3 (MM)":       rev[2],
            "Crec. Ingresos (%)": d.get("revenue_growth"),
            "Gan. A1 (MM)":       ear[0],
            "Gan. A2 (MM)":       ear[1],
            "Gan. A3 (MM)":       ear[2],
            "Crec. Gan. (%)":     d.get("earnings_growth"),
            "FCF A1 (MM)":        fcf[0],
            "FCF A2 (MM)":        fcf[1],
            "FCF A3 (MM)":        fcf[2],
            "Crec. FCF (%)":      d.get("fcf_growth"),
            "ROE":                d.get("roe"),
            "P/E":                d.get("pe"),
            "PEG":                d.get("peg"),
            "Deuda/Patr.":        d.get("debt_equity"),
            "Current Ratio":      d.get("current_ratio"),
            "Actualizado":        d.get("updated_at"),
        })

    return pd.DataFrame(rows)


def num_filter(df_work: pd.DataFrame, df_ref: pd.DataFrame, col: str, label: str) -> pd.DataFrame:
    """
    Renderiza mín/máx para una columna numérica y filtra df_work.
    Usa df_ref (dataset completo) para calcular el rango.
    Si el usuario no cambió los valores, no aplica filtro (incluye NaN).
    """
    valid = df_ref[col].dropna()
    if valid.empty or valid.nunique() < 2:
        return df_work

    mn   = float(valid.min())
    mx   = float(valid.max())
    step = (mx - mn) / 100 if mx != mn else 1.0

    st.caption(label)
    c1, c2 = st.columns(2)
    lo = c1.number_input("Mín", value=mn, step=step, format="%.4g",
                         key=f"{col}_lo", label_visibility="collapsed")
    hi = c2.number_input("Máx", value=mx, step=step, format="%.4g",
                         key=f"{col}_hi", label_visibility="collapsed")

    if abs(lo - mn) < 1e-9 and abs(hi - mx) < 1e-9:
        return df_work   # sin cambio → no filtra

    return df_work[df_work[col].between(lo, hi)]


# ── Carga de datos ─────────────────────────────────────────────────────────

st.title("📋 Nivel Instrumento")

df_full = load_data()

if df_full.empty:
    st.warning("Sin datos en MongoDB. Ejecuta primero los workflows de GitHub Actions.")
    st.stop()

df = df_full.copy()

# ── Sidebar — Filtros ──────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filtros")

    # ── Tipo ──
    st.subheader("Tipo")
    tipo = st.radio("", ["Todos", "Solo acciones", "Solo ETFs"],
                    label_visibility="collapsed")
    if tipo == "Solo acciones":
        df = df[~df["ETF"]]
    elif tipo == "Solo ETFs":
        df = df[df["ETF"]]

    # ── Brokers ──
    st.subheader("Broker")
    bc1, bc2 = st.columns(2)
    if bc1.checkbox("Capital.com"):
        df = df[df["Capital.com"]]
    if bc2.checkbox("Pepperstone"):
        df = df[df["Pepperstone"]]

    # ── Mercado ──
    with st.expander("Mercado"):
        exchanges = sorted(df_full["Exchange"].dropna().unique())
        sel_exc = st.multiselect("Exchange", exchanges)
        if sel_exc:
            df = df[df["Exchange"].isin(sel_exc)]

        sectores = sorted(df_full["Sector"].dropna().unique())
        sel_sec = st.multiselect("Sector", sectores)
        if sel_sec:
            df = df[df["Sector"].isin(sel_sec)]

        subsectores = sorted(df_full["Sub-sector"].dropna().unique())
        sel_sub = st.multiselect("Sub-sector", subsectores)
        if sel_sub:
            df = df[df["Sub-sector"].isin(sel_sub)]

    # ── Técnico ──
    with st.expander("Técnico"):
        for col_name, lbl in [
            ("Precio",          "Precio (USD)"),
            ("EMA21",           "EMA 21"),
            ("SMA50",           "SMA 50"),
            ("SMA200",          "SMA 200"),
            ("Volumen",         "Volumen"),
            ("Market Cap (MM)", "Market Cap (MM USD)"),
        ]:
            df = num_filter(df, df_full, col_name, lbl)

    # ── Crecimiento ──
    with st.expander("Crecimiento"):
        for col_name, lbl in [
            ("Crec. Ingresos (%)", "Crec. Ingresos (%)"),
            ("Crec. Gan. (%)",     "Crec. Ganancias (%)"),
            ("Crec. FCF (%)",      "Crec. FCF (%)"),
        ]:
            df = num_filter(df, df_full, col_name, lbl)

    # ── Fundamentales ──
    with st.expander("Fundamentales"):
        for col_name, lbl in [
            ("Ing. A1 (MM)", "Ingresos A1 (MM)"),
            ("Ing. A2 (MM)", "Ingresos A2 (MM)"),
            ("Ing. A3 (MM)", "Ingresos A3 (MM)"),
            ("Gan. A1 (MM)", "Ganancias A1 (MM)"),
            ("Gan. A2 (MM)", "Ganancias A2 (MM)"),
            ("Gan. A3 (MM)", "Ganancias A3 (MM)"),
            ("FCF A1 (MM)",  "FCF A1 (MM)"),
            ("FCF A2 (MM)",  "FCF A2 (MM)"),
            ("FCF A3 (MM)",  "FCF A3 (MM)"),
        ]:
            df = num_filter(df, df_full, col_name, lbl)

    # ── Ratios ──
    with st.expander("Ratios"):
        for col_name, lbl in [
            ("ROE",           "ROE"),
            ("P/E",           "P/E"),
            ("PEG",           "PEG"),
            ("Deuda/Patr.",   "Deuda/Patrimonio"),
            ("Current Ratio", "Current Ratio"),
        ]:
            df = num_filter(df, df_full, col_name, lbl)

    st.divider()
    if st.button("Limpiar filtros", use_container_width=True):
        st.rerun()

# ── Tabla principal ────────────────────────────────────────────────────────

st.caption(f"**{len(df):,}** de **{len(df_full):,}** instrumentos")

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "ETF":                st.column_config.CheckboxColumn("ETF"),
        "Capital.com":        st.column_config.CheckboxColumn("Capital.com"),
        "Pepperstone":        st.column_config.CheckboxColumn("Pepperstone"),
        "Precio":             st.column_config.NumberColumn("Precio",          format="$%.2f"),
        "EMA21":              st.column_config.NumberColumn("EMA21",           format="$%.2f"),
        "SMA50":              st.column_config.NumberColumn("SMA50",           format="$%.2f"),
        "SMA200":             st.column_config.NumberColumn("SMA200",          format="$%.2f"),
        "Volumen":            st.column_config.NumberColumn("Volumen",         format="%d"),
        "Market Cap (MM)":    st.column_config.NumberColumn("Market Cap (MM)", format="%.0f"),
        "Crec. Ingresos (%)": st.column_config.NumberColumn("Crec. Ing. (%)", format="%.1f%%"),
        "Crec. Gan. (%)":     st.column_config.NumberColumn("Crec. Gan. (%)", format="%.1f%%"),
        "Crec. FCF (%)":      st.column_config.NumberColumn("Crec. FCF (%)",  format="%.1f%%"),
        "ROE":                st.column_config.NumberColumn("ROE",             format="%.2f"),
        "P/E":                st.column_config.NumberColumn("P/E",            format="%.1f"),
        "PEG":                st.column_config.NumberColumn("PEG",            format="%.2f"),
        "Deuda/Patr.":        st.column_config.NumberColumn("Deuda/Patr.",    format="%.2f"),
        "Current Ratio":      st.column_config.NumberColumn("Current Ratio",  format="%.2f"),
    },
)
