# web/app.py
from __future__ import annotations

# --- bootstrap robusto para que Python vea src/ tanto local como en Streamlit Cloud ---
import sys
from pathlib import Path

_here = Path(__file__).resolve()
_root = _here
SRC = None
for _ in range(6):  # subir como mucho 6 niveles
    cand = _root.parent / "src"
    if cand.exists() and cand.is_dir():
        SRC = cand
        break
    _root = _root.parent

if SRC is not None and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
# --------------------------------------------------------------------

import streamlit as st
import pandas as pd
import altair as alt

from typing import Optional, Tuple

# módulos propios
from consultor_bcra.http import make_session, HttpError
from consultor_bcra.central import (
    get_deudas,
    get_deudas_historicas,
    get_cheques_rechazados_cd,
)
from consultor_bcra.transform import summarize_deudas, to_timeseries
from consultor_bcra.format import format_currency, period_to_label

st.set_page_config(page_title="Consultor BCRA", page_icon="💼", layout="wide")

st.markdown("# Consultor BCRA")

cuit = st.text_input("CUIT (11 dígitos)", value="20281584503", max_chars=11)
run = st.button("Consultar")

if run:
    if not (cuit.isdigit() and len(cuit) == 11):
        st.error("CUIT inválido (deben ser 11 dígitos).")
        st.stop()

    with st.spinner("Consultando Central de Deudores..."):
        session = make_session()  # respeta VERIFY_SSL y proxies del entorno

        # --- Solapa Deudas / Histórico / Cheques ---
        tab_deudas, tab_hist, tab_cheq = st.tabs(["Deudas", "Histórico", "Cheques"])

        # Deudas (último período + tabla)
        with tab_deudas:
            try:
                data_json, df_deu = get_deudas(session, cuit)
            except HttpError as e:
                st.error(f"Error de la API: {e}")
                st.stop()
            except Exception as e:
                st.error(f"Error inesperado: {e}")
                st.stop()

            # Encabezado con denominación
            denom = (data_json.get("results") or {}).get("denominacion") or ""
            st.subheader(f"Deudas: {denom}".strip() or "Deudas")

            st.dataframe(df_deu, use_container_width=True)

            last_period, total_last = summarize_deudas(df_deu)
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Último período**")
                st.title(period_to_label(last_period) if last_period else "—")
            with col2:
                st.markdown("**Total (último período)**")
                st.title(format_currency(total_last))

            # Serie de montos por período
            st.markdown("### Serie de montos por período")
            ts = to_timeseries(df_deu)
            if ts.empty:
                st.info("Sin datos de serie para graficar.")
            else:
                chart = (
                    alt.Chart(ts)
                    .mark_bar()
                    .encode(
                        x=alt.X("fecha:T", title="Período"),
                        y=alt.Y("monto:Q", title="Monto total"),
                        tooltip=["periodo:N","monto:Q"]
                    )
                )
                st.altair_chart(chart, use_container_width=True)

            # Descargar CSV del último período
            if not df_deu.empty:
                last_df = df_deu[df_deu["periodo"].astype(str) == (last_period or "")]
                st.download_button(
                    "Descargar CSV (último período)",
                    data=last_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"deudas_{cuit}_{period_to_label(last_period)}.csv" if last_period else f"deudas_{cuit}.csv",
                    mime="text/csv"
                )

        # Histórico
        with tab_hist:
            try:
                df_hist = get_deudas_historicas(session, cuit)
            except HttpError as e:
                st.error(f"Error de la API: {e}")
                df_hist = None
            except Exception as e:
                st.error(f"Error inesperado: {e}")
                df_hist = None

            if df_hist is None:
                st.info("Histórico no disponible para este CUIT (o el endpoint no existe).")
            elif df_hist.empty:
                st.info("Histórico vacío para este CUIT.")
            else:
                st.dataframe(df_hist, use_container_width=True)
                st.markdown("### Serie histórica (monto total por período)")
                try:
                    dfh = df_hist.copy()
                    dfh["fecha"] = pd.to_datetime(dfh["periodo"].astype(str).str[:7], format="%Y-%m", errors="coerce")
                    chart_h = (
                        alt.Chart(dfh.dropna(subset=["fecha"]))
                        .mark_line(point=True)
                        .encode(x="fecha:T", y="monto:Q", tooltip=["periodo:N","monto:Q"])
                    )
                    st.altair_chart(chart_h, use_container_width=True)
                except Exception:
                    st.info("No se pudo construir la serie histórica.")

        # Cheques
        with tab_cheq:
            try:
                df_cheq = get_cheques_rechazados_cd(session, cuit)
            except HttpError as e:
                st.error(f"Error de la API: {e}")
                df_cheq = None
            except Exception as e:
                st.error(f"Error inesperado: {e}")
                df_cheq = None

            if df_cheq is None:
                st.warning(
                    "No hay un endpoint público en Central de Deudores para cheques rechazados por CUIT, "
                    "o no está disponible para este CUIT. Si el BCRA lo habilita, lo mostraremos aquí."
                )
            elif df_cheq.empty:
                st.info("Sin cheques para mostrar.")
            else:
                st.dataframe(df_cheq, use_container_width=True)
