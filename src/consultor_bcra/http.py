# src/consultor_bcra/http.py
from typing import Tuple, Optional, Dict
import os, platform, subprocess, re
import requests
from requests.adapters import HTTPAdapter, Retry

def _detect_proxy_for(url: str) -> Optional[Dict[str, str]]:
    # Respeta variables de entorno si existen
    http = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    https = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    if http or https:
        return {'http': http or https, 'https': https or http}

    # Autodetección (Windows) como el navegador
    try:
        if platform.system().lower().startswith('win'):
            ps = f"[System.Net.WebRequest]::GetSystemWebProxy().GetProxy([Uri]'{url}').AbsoluteUri"
            out = subprocess.check_output(
                ['powershell','-NoProfile','-Command', ps], timeout=4
            ).decode(errors='ignore').strip()
            if out and out.lower().startswith('http'):
                m = re.match(r'^http://([^/:]+)(?::(\d+))?/?', out)
                if m:
                    host, port = m.group(1), (m.group(2) or '80')
                    val = f'http://{host}:{port}'
                    return {'http': val, 'https': val}
    except Exception:
        pass
    return None

def build_session(
    target_url: Optional[str] = None,
    insecure: bool = True,                       # <— por defecto SIN verificación SSL
    timeout: Tuple[int,int] = (6, 30)
) -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=3, read=3, connect=3, backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(['GET']),
        raise_on_status=False
    )
    s.mount('https://', HTTPAdapter(max_retries=retries))
    s.mount('http://',  HTTPAdapter(max_retries=retries))

    s.verify   = (False if insecure else True)   # <— clave
    s.trust_env = True

    proxies = _detect_proxy_for(target_url or 'https://api.bcra.gob.ar/')
    if proxies:
        s.proxies.update(proxies)

    _orig = s.request
    def _wrap(method, url, **kw):
        kw.setdefault('timeout', timeout)
        return _orig(method, url, **kw)
    s.request = _wrap
    return s
