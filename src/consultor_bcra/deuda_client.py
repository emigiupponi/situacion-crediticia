from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import requests
@dataclass
class EntidadDeuda:
    entidad: str; situacion: int|str|None; monto: float; en_revision: bool; proceso_judicial: bool; periodo: str
@dataclass
class ResumenDeuda:
    cuit: str; nombre: Optional[str]; entidades: List[EntidadDeuda]
def _f(x):
    try: return float(x)
    except: return 0.0
def parse_deuda_response(payload: Dict[str,Any], cuit: str) -> ResumenDeuda:
    data = payload.get('results', payload) if isinstance(payload, dict) else {}
    nombre = data.get('denominacion') or data.get('nombre')
    entidades=[]
    for per in data.get('periodos', []):
        periodo=str(per.get('periodo',''))
        for e in per.get('entidades', []):
            entidades.append(EntidadDeuda(str(e.get('entidad','')), e.get('situacion'), _f(e.get('monto',0)), bool(e.get('enRevision', e.get('en_revision', False))), bool(e.get('procesoJud', e.get('proceso_judicial', False))), periodo))
    return ResumenDeuda(cuit, nombre, entidades)
def consultar_deuda_por_cuit(session: requests.Session, cuit: str, deuda_url: str) -> ResumenDeuda:
    url = deuda_url.format(cuit=cuit) if '{cuit}' in deuda_url else deuda_url
    r = session.get(url, headers={'Accept':'application/json'}); r.raise_for_status(); data=r.json()
    return parse_deuda_response(data, cuit)
