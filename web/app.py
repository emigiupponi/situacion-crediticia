
import os
import io
import pandas as pd
import streamlit as st
import altair as alt

from src.consultor_bcra.http import make_session, HttpError
from src.consultor_bcra import central
from src.consultor_bcra.transform import flatten_deudas_json, agg_total_por_periodo, topN_entidades
from src.consultor_bcra.format import fmt_miles

st.set_page_config(page_title="Consultor BCRA", layout="centered")

st.title("Consultor BCRA")

cuit = st.text_input("CUIT (11 dígitos)", value="20281584503")

if st.button("Consultar", type="primary"):
    if not (cuit.isdigit() and len(cuit)==11):
        st.error("CUIT inválido (11 dígitos numéricos).")
        st.stop()

    sess = make_session()

    tab_deuda, tab_hist, tab_cheq = st.tabs(["Deudas", "Histórico", "Cheques rechazados"])

    with tab_deuda:
        try:
            data = central.deudas(cuit, sess)
        except HttpError as e:
            st.error(str(e))
            data = None

        if not data:
            st.warning("No disponible (Deudas).")
        else:
            denom = (data.get("results") or {}).get("denominacion", "")
            st.subheader(f"Deudas: {denom or '—'}")
            df = flatten_deudas_json(data)
            if df.empty:
                st.info("Sin datos en el último período.")
            else:
                # último período y total
                ultimo = sorted(df["periodo"].unique())[-1]
                total_ult = df.loc[df["periodo"]==ultimo, "monto"].sum()
                st.dataframe(df, use_container_width=True)
                col1,col2 = st.columns(2)
                col1.metric("Último período", ultimo)
                col2.metric("Total (último período)", fmt_miles(total_ult))

    with tab_hist:
        st.caption("Montos en **miles**.")
        try:
            hist = central.deudas_historicas(cuit, sess)
        except HttpError as e:
            st.error(str(e))
            hist = None

        if not hist:
            st.warning("No disponible (Deudas históricas).")
        else:
            dfh = flatten_deudas_json(hist)
            if dfh.empty or dfh["periodo"].nunique() <= 1:
                st.info("No hay múltiples períodos para graficar.")
            else:
                serie = agg_total_por_periodo(dfh)
                chart = (
                    alt.Chart(serie)
                    .mark_bar()
                    .encode(
                        x=alt.X("periodo:N", title="Periodo (YYYY-MM)"),
                        y=alt.Y("monto_k:Q", title="Monto (miles)"),
                        tooltip=["periodo","monto_k"]
                    )
                )
                st.altair_chart(chart, theme=None, use_container_width=True)

                # Top entidades (último período)
                ultimo = sorted(dfh["periodo"].unique())[-1]
                top = topN_entidades(dfh[dfh["periodo"]==ultimo], 10)
                st.subheader("Top entidades (último período)")
                st.dataframe(top, use_container_width=True)

                # Descargar CSV
                csv = dfh.to_csv(index=False).encode("utf-8")
                st.download_button("Descargar CSV (histórico)", data=csv, file_name=f"deudas_historicas_{cuit}.csv", mime="text/csv")

    with tab_cheq:
        st.caption("Intento Central de Deudores; si no hay, podés probar con token de Estadísticas BCRA.")
        # Intento Central
        ok = False
        try:
            ch = central.cheques_rechazados_central(cuit, sess)
            if ch:
                # Mostrar plano lo que venga
                st.subheader("Central de Deudores")
                if isinstance(ch, dict):
                    # si trae results/lista
                    dfc = pd.json_normalize(ch)
                    if not dfc.empty:
                        st.dataframe(dfc, use_container_width=True)
                        ok = True
                elif isinstance(ch, list):
                    dfc = pd.DataFrame(ch)
                    if not dfc.empty:
                        st.dataframe(dfc, use_container_width=True)
                        ok = True
        except HttpError as e:
            st.info(f"Central de Deudores: {e}")

        # Opción Estadísticas (token)
        with st.expander("Usar Estadísticas BCRA (requiere token)", expanded=False):
            token = st.text_input("BCRA_TOKEN", value=os.getenv("BCRA_TOKEN",""), type="password")
            if st.button("Consultar estadísticas", key="btn_est"):
                if not token:
                    st.error("Falta token.")
                else:
                    try:
                        ch2 = central.cheques_rechazados_estadisticas(cuit, token, sess)
                        if ch2:
                            st.subheader("Estadísticas BCRA")
                            if isinstance(ch2, list):
                                dfe = pd.DataFrame(ch2)
                            else:
                                dfe = pd.json_normalize(ch2)
                            if not dfe.empty:
                                st.dataframe(dfe, use_container_width=True)
                                # descarga
                                csv2 = dfe.to_csv(index=False).encode("utf-8")
                                st.download_button("Descargar CSV (cheques)", data=csv2, file_name=f"cheques_{cuit}.csv", mime="text/csv")
                            else:
                                st.info("Sin filas para mostrar.")
                        else:
                            st.warning("No disponible en Estadísticas BCRA.")
                    except HttpError as e:
                        st.error(str(e))

        if not ok:
            st.info("Cheques rechazados: no disponible en Central; probá con token de Estadísticas si corresponde.")
