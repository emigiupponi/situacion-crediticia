
import os
from typing import Optional, Dict
from .http import make_session, get_json, HttpError

CENTRAL_BASE = os.getenv("CENTRAL_BASE", "https://api.bcra.gob.ar/centraldedeudores/v1.0")
EST_BASE = "https://api.estadisticasbcra.com"

def _join(*parts: str) -> str:
    return "/".join(p.strip("/") for p in parts)

def deudas(cuit: str, session=None) -> Optional[Dict]:
    session = session or make_session()
    url = _join(CENTRAL_BASE, "Deudas", cuit)
    return get_json(url, session)

def deudas_historicas(cuit: str, session=None) -> Optional[Dict]:
    session = session or make_session()
    url = _join(CENTRAL_BASE, "DeudasHistoricas", cuit)
    return get_json(url, session)

def cheques_rechazados_central(cuit: str, session=None) -> Optional[Dict]:
    session = session or make_session()
    url = _join(CENTRAL_BASE, "ChequesRechazados", cuit)
    return get_json(url, session)

def cheques_rechazados_estadisticas(cuit: str, token: str, session=None) -> Optional[Dict]:
    session = session or make_session()
    url = _join(EST_BASE, "cheques_rechazados_por_identificacion", cuit)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return get_json(url, session, headers=headers)
