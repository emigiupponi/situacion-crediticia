# --- bootstrap para que Python vea src/ en Streamlit Cloud y local ---
import sys
from pathlib import Path

_here = Path(__file__).resolve()
_root = _here.parent            # <-- empezar desde la carpeta de app.py
SRC = None
for _ in range(6):              # subir como mucho 5 niveles
    cand = _root / "src"
    if cand.exists() and cand.is_dir():
        SRC = cand
        break
    _root = _root.parent

if SRC is not None and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
# --------------------------------------------------------------------

import streamlit as st
import pandas as pd
from typing import Optional, Tuple

# nuestros módulos (paquete dentro de src/consultor_bcra)
from consultor_bcra.http import make_session, HttpError
from consultor_bcra.central import (
    get_deudas,
    get_deudas_historicas,
    get_cheques_rechazados_cd,  # intenta cheques en Central de Deudores; si 404, mostramos mensaje
)
from consultor_bcra.transform import summarize_deudas, to_timeseries
from consultor_bcra.format import format_currency, period_to_label


# ---------------------------- UI helpers ---------------------------- #

def _title():
    st.set_page_config(page_title="Consultor BCRA", page_icon="📊", layout="centered")
    st.markdown(
        "<h1 style='text-align:center; margin-bottom:0.25rem'>Consultor BCRA</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Central de Deudores · datos públicos · sin token")


def _cuit_input() -> Optional[str]:
    with st.form("form_cuit", clear_on_submit=False):
        cuit = st.text_input("CUIT (11 dígitos)", value="", max_chars=11)
        submitted = st.form_submit_button("Consultar")
    if not submitted:
        return None
    cuit = cuit.strip()
    if not (cuit.isdigit() and len(cuit) == 11):
        st.error("El CUIT debe tener **11 dígitos numéricos**.")
        return None
    return cuit


def _make_session() -> Tuple:
    """
    Crea la sesión HTTP de forma consistente.
    Por defecto desactiva verificación SSL (algunos entornos corporativos hacen MITM).
    """
    # Si querés forzar verify=True, cambiá el parámetro.
    sess = make_session(verify=False, timeout_connect=5, timeout_read=20)
    return sess


def _render_deudas(df: pd.DataFrame):
    if df.empty:
        st.info("Sin registros de deudas para el CUIT en el último período disponible.")
        return

    # tabla compacta
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
    )

    # métricas clave (último período consolidado)
    ultimo_periodo = df["periodo"].max()
    df_last = df[df["periodo"] == ultimo_periodo]
    total_last = float(df_last["monto"].sum())

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Último período")
        st.markdown(f"**{period_to_label(ultimo_periodo)}**")
    with c2:
        st.subheader("Total (último período)")
        st.markdown(f"**{format_currency(total_last)}**")

    # serie temporal agregada (suma de montos por período)
    ts = to_timeseries(df)  # columnas: periodo (datetime), monto_total
    if not ts.empty and ts["monto_total"].notna().any():
        st.subheader("Serie de montos por período")
        st.bar_chart(
            ts.set_index("periodo")["monto_total"],
            use_container_width=True,  # más compatible que width='stretch'
        )

        # descarga CSV
        st.download_button(
            "Descargar CSV",
            data=ts.to_csv(index=False).encode("utf-8"),
            file_name="deudas_timeseries.csv",
            mime="text/csv",
        )
    else:
        st.info("No hay suficiente información para graficar series.")


def _render_historico(df_hist: pd.DataFrame):
    if df_hist.empty:
        st.info("No hay histórico disponible para este CUIT.")
        return

    # mostramos tabla (puede ser larga)
    st.dataframe(
        df_hist,
        hide_index=True,
        use_container_width=True,
    )

    # agregamos serie por período (suma)
    ts = to_timeseries(df_hist)
    if not ts.empty and ts["monto_total"].notna().any():
        st.subheader("Evolución histórica (monto total por período)")
        st.line_chart(
            ts.set_index("periodo")["monto_total"],
            use_container_width=True,
        )
    else:
        st.info("No hay suficiente información para graficar el histórico.")


def _render_cheques(df_cheq: Optional[pd.DataFrame], error_msg: Optional[str]):
    st.caption("Fuente: Central de Deudores (si el recurso no existe, se avisa).")
    if error_msg:
        st.warning(error_msg)
        return

    if df_cheq is None or df_cheq.empty:
        st.info("No hay cheques rechazados encontrados (o el recurso no está disponible).")
        return

    # mostrarlos simples
    st.dataframe(
        df_cheq,
        hide_index=True,
        use_container_width=True,
    )

# ---------------------------- App ---------------------------- #


def main():
    _title()
    cuit = _cuit_input()
    if not cuit:
        st.stop()

    # sesión HTTP
    session = _make_session()

    tabs = st.tabs(["Deudas", "Histórico", "Cheques rechazados"])

    # -------- Deudas (último período disponible) -------- #
    with tabs[0]:
        try:
            data = get_deudas(cuit, session=session)  # dict/json -> DataFrame dentro de summarize
            df = summarize_deudas(data)              # DataFrame con columnas: periodo, entidad, monto, situacion, ...
            _render_deudas(df)
        except HttpError as e:
            st.error(f"Error al consultar Deudas: {e}")
        except Exception as e:
            st.error(f"Error inesperado en Deudas: {e}")

    # -------- Deudas históricas -------- #
    with tabs[1]:
        try:
            data_h = get_deudas_historicas(cuit, session=session)
            df_h = summarize_deudas(data_h)
            _render_historico(df_h)
        except HttpError as e:
            st.error(f"Error al consultar Histórico: {e}")
        except Exception as e:
            st.error(f"Error inesperado en Histórico: {e}")

    # -------- Cheques rechazados (Central de Deudores) -------- #
    with tabs[2]:
        err = None
        df_cheques = None
        try:
            # Algunos despliegues de Central de Deudores NO exponen cheques por identificación.
            # En ese caso, la función puede levantar HttpError con 404.
            df_cheques = get_cheques_rechazados_cd(cuit, session=session)
        except HttpError as e:
            if getattr(e, "status", None) == 404:
                err = (
                    "El recurso de **cheques rechazados por identificación** no está disponible "
                    "en esta instancia de Central de Deudores pública (HTTP 404)."
                )
            else:
                err = f"Error al consultar cheques: {e}"
        except Exception as e:
            err = f"Error inesperado consultando cheques: {e}"

        _render_cheques(df_cheques, err)


if __name__ == "__main__":
    main()
