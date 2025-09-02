# web/app.py
import re, sys, pathlib, json
import pandas as pd
import streamlit as st
import urllib3
from typing import Any, Dict, List, Optional, Tuple

# Silenciar warning de TLS (usamos verify=False en la sesión)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- paths internos del repo
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from consultor_bcra.cuit import validar_cuit
from consultor_bcra.http import build_session
from consultor_bcra.deuda_client import consultar_deuda_por_cuit
from consultor_bcra.plotting import series_total_por_periodo

st.set_page_config(page_title="Consultor BCRA", page_icon="💼", layout="centered")
st.title("Consultor BCRA")

# --- Endpoints BCRA (públicos, sin token)
CD_BASE   = "https://api.bcra.gob.ar/centraldedeudores/v1.0"
URL_DEUDA = CD_BASE + "/Deudas/{cuit}"
URL_HIST  = CD_BASE + "/DeudasHistoricas/{cuit}"  # si 404, caemos a /Deudas

CHEQ_BASE = "https://api.bcra.gob.ar/cheques/v1.0"  # Cheques v1

# -------------------- util común --------------------
def _fmt_periodo(p: str) -> str:
    s = str(p or "")
    return f"{s[:4]}-{s[4:]}" if len(s) == 6 and s.isdigit() else s

def _fmt_ars(n):
    try:
        return f"${int(round(float(n))):,}".replace(",", ".")
    except Exception:
        return "-"

def _safe_json(r) -> Any:
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:1000]}

# ------------------ Deudas (CD) ---------------------
def _flatten_historico(json_obj) -> tuple[str, pd.DataFrame]:
    """
    Espera la forma:
      { status, results: { identificacion, denominacion, periodos: [
          { periodo: 'YYYYMM', entidades: [ { entidad, monto, situacion, ... } ] }
      ]}}
    Devuelve (nombre, DataFrame con columnas periodo, entidad, monto, situacion, en_revision, proceso_judicial)
    """
    node = json_obj.get("results", json_obj) if isinstance(json_obj, dict) else {}
    nombre = node.get("denominacion") or ""
    periodos = node.get("periodos") or []

    rows = []
    for per in periodos:
        periodo = per.get("periodo") or per.get("periodoInformado") or ""
        entidades = per.get("entidades") or []
        for e in entidades:
            rows.append({
                "periodo": periodo,
                "entidad": e.get("entidad") or e.get("banco") or "",
                "monto": e.get("monto") or e.get("importe") or 0,
                "situacion": e.get("situacion") or e.get("sit") or None,
                "en_revision": bool(e.get("enRevision") or e.get("en_revision") or False),
                "proceso_judicial": bool(e.get("procesoJudicial") or e.get("proceso_judicial") or False),
            })
    return nombre, pd.DataFrame(rows)

def _ui_deudas():
    st.subheader("Deudas (Central de Deudores)")
    cuit = st.text_input("CUIT (11 dígitos)", key="cuit_deuda")

    if st.button("Consultar", key="btn_deuda"):
        cu = re.sub(r"\D", "", cuit or "")
        if not validar_cuit(cu):
            st.error("CUIT inválido (deben ser 11 dígitos).")
            return

        try:
            s = build_session(target_url=CD_BASE, insecure=True)

            # Intento histórico primero
            df = pd.DataFrame()
            nombre = ""
            fuente = ""

            r = s.get(URL_HIST.format(cuit=cu))
            if r.status_code == 200:
                nombre, df = _flatten_historico(_safe_json(r))
                fuente = "Histórico (Central de Deudores)"
            elif r.status_code in (400, 404):
                # Fallback a último período
                resumen = consultar_deuda_por_cuit(s, cu, URL_DEUDA)
                nombre = resumen.nombre or ""
                df = pd.DataFrame([{
                    "periodo": e.periodo,
                    "entidad": e.entidad,
                    "monto": e.monto,
                    "situacion": e.situacion,
                    "en_revision": e.en_revision,
                    "proceso_judicial": e.proceso_judicial
                } for e in resumen.entidades])
                fuente = "Último período (Central de Deudores)"
            else:
                r.raise_for_status()

            if df.empty:
                st.info("Sin datos devueltos para ese CUIT.")
                return

            st.caption(f"Fuente: {fuente}")
            df["periodo_fmt"] = df["periodo"].map(_fmt_periodo)
            df = df.sort_values(["periodo_fmt", "monto"], ascending=[True, False])

            st.dataframe(
                df[["periodo_fmt","entidad","monto","situacion","en_revision","proceso_judicial"]]
                  .rename(columns={"periodo_fmt":"periodo"}),
                use_container_width=True
            )

            # Métricas último período
            ultimo_per = df["periodo_fmt"].max()
            total_ult  = pd.to_numeric(
                df.loc[df["periodo_fmt"] == ultimo_per, "monto"], errors="coerce"
            ).fillna(0).sum()
            colA, colB = st.columns(2)
            with colA: st.metric("Último período", ultimo_per or "-")
            with colB: st.metric("Total (último período)", _fmt_ars(total_ult))

            # Serie mensual
            serie_df = pd.DataFrame({
                "periodo": df["periodo"].map(_fmt_periodo),
                "monto": pd.to_numeric(df["monto"], errors="coerce").fillna(0)
            })
            serie = series_total_por_periodo(serie_df)
            if not serie.empty:
                st.subheader("Serie de montos por período")
                st.bar_chart(serie.set_index("periodo")["monto"], use_container_width=True)

            # Descargar CSV
            csv_df = df.drop(columns=["periodo"]).rename(columns={"periodo_fmt":"periodo"})
            st.download_button(
                "Descargar CSV",
                csv_df.to_csv(index=False).encode("utf-8"),
                file_name=f"deudas_{cu}.csv",
                mime="text/csv"
            )

        except Exception as e:
            st.error(f"Error: {e}")

# ---------------- Cheques denunciados ----------------
def _get_entidades(s) -> List[Dict[str, str]]:
    """Devuelve [{'codigo': '011', 'nombre':'BANCO...'}, ...] o []. Prueba variantes del endpoint."""
    urls = [f"{CHEQ_BASE}/Entidades", f"{CHEQ_BASE}/entidades"]
    for u in urls:
        r = s.get(u)
        if r.status_code == 200:
            data = _safe_json(r)
            out = []
            if isinstance(data, list):
                for it in data:
                    codigo = str(it.get("codigo") or it.get("id") or it.get("codigoEntidad") or "").strip()
                    nombre = str(it.get("nombre") or it.get("denominacion") or "").strip()
                    if codigo and nombre:
                        out.append({"codigo": codigo, "nombre": nombre})
            elif isinstance(data, dict):
                arr = data.get("results") or data.get("entidades") or []
                for it in arr:
                    codigo = str(it.get("codigo") or it.get("id") or it.get("codigoEntidad") or "").strip()
                    nombre = str(it.get("nombre") or it.get("denominacion") or "").strip()
                    if codigo and nombre:
                        out.append({"codigo": codigo, "nombre": nombre})
            if out:
                # Ordenar por nombre
                return sorted(out, key=lambda x: x["nombre"])
    return []

def _get_cheque_denunciado(s, cod_entidad: str, nro_cheque: str) -> Tuple[int, Any, str]:
    """
    Intenta rutas comunes:
      - /Denunciados/{entidad}/{numero}
      - /denunciados/{entidad}/{numero}
      - /Denunciados?entidad=..&numero=..
      - /denunciados?entidad=..&numero=..
    Devuelve (status_code, payload_json_o_texto, url_usada)
    """
    cod_entidad = cod_entidad.strip()
    nro_cheque  = re.sub(r"\D", "", nro_cheque or "")
    if not cod_entidad or not nro_cheque:
        return 400, {"error": "Faltan parámetros"}, ""

    candidates = [
        f"{CHEQ_BASE}/Denunciados/{cod_entidad}/{nro_cheque}",
        f"{CHEQ_BASE}/denunciados/{cod_entidad}/{nro_cheque}",
        f"{CHEQ_BASE}/Denunciados?entidad={cod_entidad}&numero={nro_cheque}",
        f"{CHEQ_BASE}/denunciados?entidad={cod_entidad}&numero={nro_cheque}",
    ]
    last = None
    for u in candidates:
        r = s.get(u)
        last = u
        if r.status_code == 200:
            return 200, _safe_json(r), u
        if r.status_code not in (404, 400, 405):
            # Algo distinto a "no existe" -> devolvemos para que el usuario lo vea
            return r.status_code, _safe_json(r), u
    return 404, {"error": "Endpoint no encontrado para las variantes probadas."}, last or candidates[-1]

def _ui_cheques():
    st.subheader("Cheques denunciados (BCRA)")
    # Sesión con verify=False
    s = build_session(target_url=CHEQ_BASE, insecure=True)

    entidades = _get_entidades(s)
    col1, col2 = st.columns([2,1])

    if entidades:
        # Select de banco
        opciones = [f"{e['nombre']} — {e['codigo']}" for e in entidades]
        sel = col1.selectbox("Entidad bancaria", opciones, key="ent_sel")
        cod_ent = entidades[opciones.index(sel)]["codigo"]
    else:
        cod_ent = col1.text_input("Código de entidad bancaria", key="ent_cod").strip()

    nro = col2.text_input("Número de cheque", key="nro_cheq")

    if st.button("Consultar cheque", key="btn_cheq"):
        if not cod_ent or not nro:
            st.error("Ingresá código de entidad y número de cheque.")
            return

        status, payload, url_usada = _get_cheque_denunciado(s, cod_ent, nro)
        st.caption(f"URL consultada: {url_usada}  —  HTTP {status}")

        if status == 200:
            # Intento de interpretación básica
            texto = json.dumps(payload, ensure_ascii=False).lower()
            es_den = ("denunciado" in texto) or ("sustra" in texto) or ("extravi" in texto) or ("adulter" in texto)
            if es_den:
                st.error("Resultado: EL CHEQUE FIGURA COMO DENUNCIADO (ver detalle debajo).")
            else:
                st.success("Resultado: no figura como denunciado (según respuesta).")
            # Mostrar detalle crudo para transparencia
            st.json(payload)
        elif status in (400, 404):
            st.warning("El endpoint de denuncia de cheques no está disponible con las rutas probadas (o parámetros inválidos).")
            st.json(payload)
        else:
            st.error("Error de la API de cheques.")
            st.json(payload)

# ------------------------ UI ------------------------
tab1, tab2 = st.tabs(["Deudas (CD)", "Cheques denunciados"])

with tab1:
    _ui_deudas()

with tab2:
    _ui_cheques()
