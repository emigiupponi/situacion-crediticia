from typing import Any, Dict, List
from datetime import datetime, timedelta
import requests
BASE='https://api.bcra.gob.ar/centraldedeudores/v1.0'
def _json(r: requests.Response): r.raise_for_status(); return r.json()
def _unwrap(p): return (p.get('results', p) if isinstance(p, dict) else p)
def consultar_cheques_rechazados_por_cuit(session: requests.Session, cuit: str, url_tpl: str=f'{BASE}/ChequesRechazados/{{cuit}}', meses:int=12)->List[Dict[str,Any]]:
    url = url_tpl.format(cuit=cuit) if '{cuit}' in url_tpl else url_tpl
    data=_unwrap(_json(session.get(url, headers={'Accept':'application/json'})))
    if isinstance(data, list): regs=data
    elif isinstance(data, dict): regs=data.get('registros') or data.get('items') or data.get('cheques') or data.get('data') or []
    else: regs=[]
    corte = datetime.today() - timedelta(days=30*meses)
    out=[]
    for row in regs:
        fecha=None
        if isinstance(row, dict):
            for k,v in row.items():
                if isinstance(k,str) and 'fecha' in k.lower() and isinstance(v,str):
                    s=v[:10]
                    for fmt in ('%Y-%m-%d','%Y%m%d','%d/%m/%Y'):
                        try:
                            fecha=datetime.strptime(s,fmt); break
                        except: pass
                    if fecha: break
        if fecha and fecha>=corte:
            r=dict(row); r['fecha_norm']=fecha.date().isoformat(); out.append(r)
    return out
