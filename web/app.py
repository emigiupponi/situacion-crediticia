import os
import re
import json
import math
import time
import typing as t
from datetime import datetime, timedelta

import requests
import pandas as pd
import streamlit as st

# --- Preferencias de red / SSL ---
# Por pedido: NO verificar SSL por defecto (ideal solo en redes "difíciles")
VERIFY_SSL = False
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

BCRA_BASE = "https://api.bcra.gob.ar/centraldedeudores/v1.0"

# -------- Utilidades --------

def _requests_session() -> requests.Session:
    s = requests.Session()
    # respeta HTTP_PROXY/HTTPS_PROXY si están seteadas
    s.headers.update({"Accept": "application/json"})
    s.verify = VERIFY_SSL
    return s

def _fmt_miles(x: t.Optional[float]) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    try:
        # miles con punto y decimales con coma (formato AR)
        return f"{x:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except Exception:
        return str(x)

def _yyyy_mm_from_periodo(s: str) -> str:
    # admite "YYYYMM" o "YYYY-MM"
    s = str(s)
    if re.fullmatch(r"\d{6}", s):
        return f"{s[:4]}-{s[4:]}"
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return s
    # fallback: solo año-mes si hay fecha completa
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s[:7]
    return s

def _parse_date_maybe(s: str) -> t.Optional[datetime]:
    if not s:
        return None
    s = str(s)
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(s[:10], fmt if fmt != "%Y-%m" else "%Y-%m")
            if fmt == "%Y-%m":
                # primer día del mes para ordenar
                return datetime(dt.year, dt.month, 1)
            return dt
        except Exception:
            continue
    return None

def _get_json(path: str, identificacion: str) -> t.Tuple[int, t.Any]:
    """
    Devuelve (status_code, json|None). No levanta excepción.
    path: ej "Deudas", "DeudasHistoricas", "ChequesRechazados"
    """
    url = f"{BCRA_BASE}/{path}/{identificacion}"
    try:
        with _requests_session() as s:
            r = s.get(url, timeout=(5, 20))
            sc = r.status_code
            if sc >= 200 and sc < 300:
                try:
                    return sc, r.json()
                except Exception:
                    return sc, None
            else:
                return sc, None
    except Exception:
        return 0, None

def _flatten_deudas_json(payload: dict) -> pd.DataFrame:
    """
    Espera estructura tipo:
    {"status":200,"results":{"identificacion":..., "denominacion":..., "periodos":[
        {"periodo":"YYYYMM","entidades":[{"entidad":..., "situacion":1, "monto":... , ...}, ...]}
    ]}}
    Devuelve DF con columnas: periodo, periodo_str, entidad, situacion, monto, ... (monto_k)
    """
    if not payload or "results" not in payload:
        return pd.DataFrame()

    rows = []
    res = payload["results"]
    periodos = res.get("periodos", [])
    for p in periodos:
        periodo = str(p.get("periodo", ""))
        periodo_str = _yyyy_mm_from_periodo(periodo)
        for e in p.get("entidades", []) or []:
            row = {
                "periodo": periodo,
                "periodo_str": periodo_str,
                "entidad": e.get("entidad"),
                "situacion": e.get("situacion"),
                "monto": e.get("monto"),
                "diasAtrasoPago": e.get("diasAtrasoPago"),
                "enRevision": e.get("enRevision"),
                "procesoJud": e.get("procesoJud"),
                "refinanciaciones": e.get("refinanciaciones"),
                "recategorizacionOblig": e.get("recategorizacionOblig"),
            }
            rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # normalizar y crear monto_k
    if "monto" in df.columns:
        df["monto"] = pd.to_numeric(df["monto"], errors="coerce")
        df["monto_k"] = (df["monto"] / 1000.0).round(1)
    else:
        df["monto_k"] = None
    # ordenar cronológico por periodo_str
    try:
        df["_sort"] = pd.to_datetime(df["periodo_str"], errors="coerce")
        df = df.sort_values(["_sort", "entidad"], ascending=[True, True]).drop(columns=["_sort"])
    except Exception:
        pass
    return df

def _pick_topN_with_others(pivot_df: pd.DataFrame, top_n: int = 8) -> pd.DataFrame:
    """
    pivot_df: index = periodo_str, columns = entidad, values = monto_k
    Mantiene top_n columnas por suma total y agrega 'Otros' con el resto.
    """
    sums = pivot_df.sum(axis=0).sort_values(ascending=False)
    keep = list(sums.head(top_n).index)
    rest = [c for c in pivot_df.columns if c not in keep]
    out = pd.DataFrame(index=pivot_df.index)
    for c in keep:
        out[c] = pivot_df[c]
    if rest:
        out["Otros"] = pivot_df[rest].sum(axis=1)
    return out.fillna(0)

def _limit_horizon(df: pd.DataFrame, months: int) -> pd.DataFrame:
    if df.empty or "periodo_str" not in df.columns:
        return df
    # tomar últimos N meses disponibles
    unique = sorted(df["periodo_str"].dropna().unique())
    take = set(unique[-months:]) if months and len(unique) > months else set(unique)
    return df[df["periodo_str"].isin(take)].copy()

# -------- UI --------

st.set_page_config(page_title="Consultor BCRA", page_icon="🏦", layout="wide")

st.title("🏦 Consultor BCRA – Central de Deudores")
st.caption("Montos expresados **en miles**. Separador miles `.` y decimales `,`. (Conexión SSL sin verificación activada por defecto.)")

# CUIT arriba, único
if "cuit" not in st.session_state:
    st.session_state.cuit = ""

cuit = st.text_input("CUIT (11 dígitos):", value=st.session_state.cuit, max_chars=11, help="Ej. 20281584503")
st.session_state.cuit = cuit.strip()

if not (st.session_state.cuit.isdigit() and len(st.session_state.cuit) == 11):
    st.info("Ingresá un **CUIT válido de 11 dígitos** para consultar.")
    st.stop()

ident = st.session_state.cuit

tabs = st.tabs(["Deudas (último período)", "Histórico", "Cheques rechazados"])

# --- TAB 1: Deudas último período ---
with tabs[0]:
    st.subheader("Deudas (último período)")
    sc, data = _get_json("Deudas", ident)
    if sc == 0 or data is None:
        st.info("No disponible por el momento.")
        st.stop()
    df = _flatten_deudas_json(data)
    if df.empty:
        st.info("No disponible para este CUIT.")
    else:
        # KPI período + total
        periodo_disp = df["periodo_str"].dropna().unique()
        periodo_txt = periodo_disp[-1] if len(periodo_disp) else "-"
        total_k = df["monto_k"].sum(skipna=True)
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Período", periodo_txt)
        with c2:
            st.metric("Total del período (miles)", _fmt_miles(total_k))

        # Tabla por entidad (último período solamente)
        ultimo = df[df["periodo_str"] == periodo_txt].copy()
        cols = ["entidad", "situacion", "monto_k", "enRevision", "procesoJud"]
        for c in cols:
            if c not in ultimo.columns:
                ultimo[c] = None
        ultimo_show = ultimo[cols].rename(columns={
            "entidad": "Entidad",
            "situacion": "Situación",
            "monto_k": "Monto (miles)",
            "enRevision": "En revisión",
            "procesoJud": "Proc. judicial",
        })
        # formateo de miles
        ultimo_show["Monto (miles)"] = ultimo_show["Monto (miles)"].apply(_fmt_miles)
        st.dataframe(ultimo_show, use_container_width=None, width="stretch")

        # Barras horizontales (top por monto del último período)
        try:
            top = ultimo.sort_values("monto_k", ascending=False).head(12)
            chart_df = top.set_index("entidad")["monto_k"]
            st.bar_chart(chart_df, use_container_width=True)  # mantener use_container_width para charts
        except Exception:
            pass

# --- TAB 2: Histórico ---
with tabs[1]:
    st.subheader("Evolución histórica")
    horizon = st.selectbox("Horizonte (meses):", [12, 24, 36], index=0)
    sc_h, data_h = _get_json("DeudasHistoricas", ident)
    if sc_h == 0 or data_h is None:
        st.info("No disponible para este CUIT o la API no ofrece histórico.")
    else:
        dfh = _flatten_deudas_json(data_h)
        if dfh.empty:
            st.info("No disponible para este CUIT.")
        else:
            dfh = _limit_horizon(dfh, months=horizon)

            # Serie total por mes
            serie = dfh.groupby("periodo_str", as_index=True)["monto_k"].sum().sort_index()
            st.caption("Serie total (miles)")
            st.line_chart(serie, use_container_width=True)

            # Barras apiladas por banco (top 8 + Otros)
            st.caption("Barras apiladas por banco (miles)")
            piv = dfh.pivot_table(index="periodo_str", columns="entidad", values="monto_k", aggfunc="sum").fillna(0)
            piv = piv.sort_index()
            piv_top = _pick_topN_with_others(piv, top_n=8)
            st.bar_chart(piv_top, use_container_width=True)

            # Distribución por situación (miles) – apiladas
            st.caption("Distribución por situación (miles)")
            if "situacion" in dfh.columns and dfh["situacion"].notna().any():
                piv_sit = dfh.pivot_table(index="periodo_str", columns="situacion", values="monto_k", aggfunc="sum").fillna(0)
                piv_sit = piv_sit.sort_index()
                # ordenar columnas por situación (1..n)
                try:
                    piv_sit = piv_sit.reindex(sorted(piv_sit.columns), axis=1)
                except Exception:
                    pass
                st.bar_chart(piv_sit, use_container_width=True)
            else:
                st.info("No hay información de situación disponible en el histórico.")

            # Tabla detalle (opcional, descargable)
            show = dfh[["periodo_str", "entidad", "situacion", "monto_k"]].copy()
            show = show.rename(columns={"periodo_str": "Periodo", "entidad": "Entidad", "situacion": "Situación", "monto_k": "Monto (miles)"})
            show["Monto (miles)"] = show["Monto (miles)"].apply(_fmt_miles)
            st.dataframe(show, use_container_width=None, width="stretch")

            # Botón de descarga
            csv = dfh.to_csv(index=False).encode("utf-8-sig")
            st.download_button("Descargar histórico (CSV)", data=csv, file_name=f"deudas_historicas_{ident}.csv", mime="text/csv")

# --- TAB 3: Cheques rechazados (por CUIT) ---
with tabs[2]:
    st.subheader("Cheques rechazados (últimos 12 meses)")
    # IMPORTANTE: este endpoint existe dentro de Central de Deudores según el catálogo.
    # Si el recurso no está habilitado para tu entorno/cuota, mostraremos 'No disponible'.
    # Intentamos con el nombre más probable documentado; si diera 404/None, no inventamos.
    sc_c, data_c = _get_json("ChequesRechazados", ident)
    if sc_c == 0 or data_c is None:
        st.info("No disponible para este CUIT o la API no ofrece cheques rechazados por identificación.")
    else:
        # Estructuras posibles: {"status":200,"results":[ {...}, {...} ]} o similar
        results = []
        if isinstance(data_c, dict) and "results" in data_c:
            rs = data_c.get("results") or []
            if isinstance(rs, list):
                results = rs
        elif isinstance(data_c, list):
            results = data_c

        if not results:
            st.info("No disponible para este CUIT.")
        else:
            # Filtrar últimos 12 meses
            corte = datetime.today() - timedelta(days=365)
            parsed = []
            for item in results:
                # Campos típicos a tantear
                fecha = (
                    item.get("fecha") or
                    item.get("fechaRechazo") or
                    item.get("periodo")  # a veces mensual
                )
                dt = _parse_date_maybe(str(fecha) if fecha is not None else "")
                if dt is None and "periodo" in item:
                    # si viene YYYYMM sin día
                    dt = _parse_date_maybe(_yyyy_mm_from_periodo(item.get("periodo")))
                if dt and dt >= corte:
                    parsed.append(item)

            if not parsed:
                st.info("Sin cheques rechazados en los últimos 12 meses (o no informados).")
            else:
                dfc = pd.DataFrame(parsed)
                # monto (si existiera)
                if "monto" in dfc.columns:
                    dfc["monto"] = pd.to_numeric(dfc["monto"], errors="coerce")
                    dfc["monto_k"] = (dfc["monto"] / 1000.0).round(1)
                # estado levantado/no si viniera
                # intentamos detectar bandera
                lev_col = None
                for cand in ["levantado", "fueLevantado", "levantadoFlag", "estado"]:
                    if cand in dfc.columns:
                        lev_col = cand
                        break

                # KPIs
                cant = len(dfc)
                total_k = dfc["monto_k"].sum(skipna=True) if "monto_k" in dfc.columns else None
                c1, c2 = st.columns(2)
                with c1:
                    st.metric("Cantidad (12 meses)", f"{cant}")
                with c2:
                    st.metric("Monto total (miles, 12m)", _fmt_miles(total_k) if total_k is not None else "—")

                # Tabla resumen
                show_cols = []
                for c in ["fecha", "fechaRechazo", "periodo", "entidad", "causal", lev_col, "monto_k"]:
                    if c and c in dfc.columns:
                        show_cols.append(c)
                if not show_cols:
                    show_cols = list(dfc.columns)[:8]
                show = dfc[show_cols].rename(columns={
                    "fecha": "Fecha",
                    "fechaRechazo": "Fecha",
                    "periodo": "Periodo",
                    "entidad": "Entidad",
                    "causal": "Causal",
                    lev_col if lev_col else "": "Levantado",
                    "monto_k": "Monto (miles)",
                })
                if "Monto (miles)" in show.columns:
                    show["Monto (miles)"] = show["Monto (miles)"].apply(_fmt_miles)
                st.dataframe(show, use_container_width=None, width="stretch")

                # Descarga
                csv = dfc.to_csv(index=False).encode("utf-8-sig")
                st.download_button("Descargar cheques (CSV)", data=csv, file_name=f"cheques_rechazados_{ident}.csv", mime="text/csv")
