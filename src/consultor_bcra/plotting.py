# src/consultor_bcra/plotting.py
import pandas as pd

def series_total_por_periodo(df: pd.DataFrame) -> pd.DataFrame:
    """
    Espera un DF con columnas: 'periodo' (YYYY-MM o YYYYMM) y 'monto'.
    Devuelve DF con columnas: 'periodo' (YYYY-MM) y 'monto' (sumado por mes),
    ordenado cronológicamente.
    """
    if "periodo" not in df.columns or "monto" not in df.columns:
        return pd.DataFrame({"periodo": [], "monto": []})

    out = df.copy()
    out["monto"] = pd.to_numeric(out["monto"], errors="coerce").fillna(0.0)
    out["periodo"] = out["periodo"].astype(str)

    # Normalizar: 202507 -> 2025-07 (si ya viene 2025-07 se mantiene)
    out["periodo"] = out["periodo"].str.replace(r"^(\d{4})(\d{2})$", r"\1-\2", regex=True)

    # Ordenar cronológicamente usando el 1° de cada mes
    out["dt"] = pd.to_datetime(out["periodo"] + "-01", errors="coerce")

    res = (
        out.dropna(subset=["dt"])
           .groupby("dt", as_index=False)["monto"].sum()
           .sort_values("dt")
    )
    res["periodo"] = res["dt"].dt.strftime("%Y-%m")
    return res[["periodo", "monto"]]
