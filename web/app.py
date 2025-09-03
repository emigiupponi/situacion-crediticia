# web/app.py

import sys
from pathlib import Path

# --- bootstrap para que Python vea src/ ---
_here = Path(__file__).resolve()
_root = _here
for _ in range(6):
    cand = _root.parent / "src"
    if cand.exists() and cand.is_dir():
        if str(cand) not in sys.path:
            sys.path.insert(0, str(cand))
        break
    _root = _root.parent

import streamlit as st
import pandas as pd
import plotly.express as px

from consultor_bcra import (
    deudas_por_cuit,
    deudas_historicas_por_cuit,
    cheques_rechazados_por_cuit,
)

st.set_page_config(page_title="Central de Deudores BCRA", page_icon="💳", layout="wide")

st.title("Central de Deudores – BCRA")

cuit = st.text_input("CUIT (11 dígitos)", value="30573819256", max_chars=11)
consultar = st.button("Consultar", type="primary")

if consultar and cuit:
    tab1, tab2, tab3 = st.tabs(["Deudas actuales", "Deudas históricas", "Cheques rechazados"])

    with tab1:
        try:
            data = deudas_por_cuit(cuit)
            if "periodos" in data.get("results", {}):
                entidades = data["results"]["periodos"][0]["entidades"]
                df = pd.DataFrame(entidades)
                st.dataframe(df)
                if not df.empty:
                    fig = px.bar(df, x="entidad", y="monto", title="Deuda por entidad")
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Sin datos de deudas para este CUIT.")
        except Exception as e:
            st.error(f"Error consultando deudas: {e}")

    with tab2:
        try:
            data = deudas_historicas_por_cuit(cuit)
            periodos = data.get("results", {}).get("periodos", [])
            if periodos:
                rows = []
                for p in periodos:
                    total = sum(ent["monto"] for ent in p["entidades"])
                    rows.append({"periodo": p["periodo"], "total_monto": total})
                df = pd.DataFrame(rows)
                st.dataframe(df)
                if not df.empty:
                    fig = px.line(df, x="periodo", y="total_monto", title="Deuda total histórica")
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Sin datos históricos para este CUIT.")
        except Exception as e:
            st.error(f"Error consultando deudas históricas: {e}")

    with tab3:
        try:
            data = cheques_rechazados_por_cuit(cuit)
            causales = data.get("results", {}).get("causales", [])

            if causales:
                rows = []
                for c in causales:
                    causal = c.get("causal")
                    for ent in c.get("entidades", []):
                        entidad = ent.get("entidad")
                        for det in ent.get("detalle", []):
                            row = {
                                "causal": causal,
                                "entidad": entidad,
                                "nroCheque": det.get("nroCheque"),
                                "fechaRechazo": det.get("fechaRechazo"),
                                "monto": det.get("monto"),
                                "estadoMulta": det.get("estadoMulta"),
                                "enRevision": det.get("enRevision"),
                                "procesoJud": det.get("procesoJud"),
                            }
                            rows.append(row)
                df = pd.DataFrame(rows)
                st.dataframe(df)
            else:
                st.warning("Sin cheques rechazados para este CUIT.")
        except Exception as e:
            st.error(f"Error consultando cheques rechazados: {e}")
