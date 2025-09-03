
from typing import Dict, List, Tuple
import pandas as pd

def _safe_get(d: dict, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def _norm_period(p: str) -> str:
    if not isinstance(p, str):
        return str(p)
    p = p.strip()
    if len(p) == 6 and p.isdigit():
        return f"{p[:4]}-{p[4:]}"
    return p

def flatten_deudas_json(data: Dict) -> pd.DataFrame:
    """Convierte el JSON de Central (Deudas / DeudasHistoricas) a un DataFrame plano
    con columnas: periodo, entidad, monto, situacion, en_revision, proceso_judicial.
    Tolera que falten campos.
    """
    rows: List[dict] = []
    periodos = _safe_get(data, "results", "periodos", default=[])
    if not isinstance(periodos, list):
        periodos = []

    for per in periodos:
        periodo = _norm_period(per.get("periodo") or per.get("mes") or "")
        entidades = per.get("entidades") or per.get("detalle") or []
        if not isinstance(entidades, list):
            continue
        for e in entidades:
            rows.append({
                "periodo": periodo,
                "entidad": e.get("entidad") or e.get("banco") or "",
                "monto": e.get("monto") or e.get("importe") or 0,
                "situacion": e.get("situacion") or e.get("sit") or None,
                "en_revision": bool(e.get("enRevision") or e.get("en_revision") or False),
                "proceso_judicial": bool(e.get("procesoJud") or e.get("proceso_judicial") or False),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        # asegurar tipos
        df["periodo"] = df["periodo"].astype(str)
        df["monto"] = pd.to_numeric(df["monto"], errors="coerce").fillna(0.0)
    return df

def agg_total_por_periodo(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "periodo" not in df or "monto" not in df:
        return pd.DataFrame(columns=["periodo","monto_k"])
    g = df.groupby("periodo", as_index=False)["monto"].sum()
    # convertir a miles
    g["monto_k"] = (g["monto"] / 1000.0).round(2)
    # ordenar por fecha (YYYY-MM)
    try:
        g = g.sort_values("periodo")
    except Exception:
        pass
    return g[["periodo","monto_k"]]

def topN_entidades(df: pd.DataFrame, n: int=10) -> pd.DataFrame:
    if df.empty:
        return df
    g = df.groupby("entidad", as_index=False)["monto"].sum().sort_values("monto", ascending=False)
    if len(g) <= n:
        return g
    top = g.head(n).copy()
    otros = pd.DataFrame([{"entidad":"Otros","monto": g["monto"][n:].sum()}])
    return pd.concat([top, otros], ignore_index=True)

