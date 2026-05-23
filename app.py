"""
app.py
Punto de entrada de Trading Pipeline.
Streamlit >= 1.28 — define las 2 páginas independientes de la app.
"""

import streamlit as st

st.set_page_config(
    page_title="Trading Pipeline",
    page_icon="📈",
    layout="wide",
)

pg = st.navigation([
    st.Page("pages/nivel_instrumento.py", title="Nivel Instrumento", icon="📋"),
    st.Page("pages/nivel_mercado.py",     title="Nivel Mercado",     icon="🌍"),
])
pg.run()
