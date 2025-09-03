
import os
import requests
from typing import Any, Dict, Optional

def _bool_env(name: str, default: bool=False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1","true","t","yes","y","on")

def make_session() -> requests.Session:
    # Respetar proxies del entorno automáticamente (requests ya lo hace).
    sess = requests.Session()
    verify = _bool_env("VERIFY_SSL", False)
    sess.verify = verify
    # Si se desactiva verify, silenciar warnings ruidosos
    if not verify:
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
    return sess

class HttpError(RuntimeError):
    pass

def get_json(url: str, session: requests.Session, headers: Optional[Dict[str,str]]=None, timeout=(5,20)) -> Optional[dict]:
    try:
        r = session.get(url, headers=headers or {}, timeout=timeout)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        raise HttpError(f"GET {url} -> {e}")
    except ValueError as e:
        raise HttpError(f"Invalid JSON from {url}: {e}")
