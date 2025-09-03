
def fmt_miles(v) -> str:
    try:
        # v llega en unidades; presentamos en miles
        return f"${(float(v)/1000.0):,.0f}".replace(",", ".")
    except Exception:
        return "-"
