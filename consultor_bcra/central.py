"""
Funciones para consultar la API de la Central de Deudores del Banco Central.
"""

import requests

# Configuración fija
BASE_URL = "https://api.bcra.gob.ar/CentralDeDeudores/v1.0"
VERIFY_SSL = False   # no verificamos SSL porque estás fuera de la red del banco
TIMEOUT = 20


def deudas_por_cuit(cuit: str):
    """
    Consulta deudas del período más reciente para un CUIT.
    """
    url = f"{BASE_URL}/Deudas/{cuit}"
    r = requests.get(url, verify=VERIFY_SSL, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def deudas_historicas_por_cuit(cuit: str):
    """
    Consulta deudas históricas para un CUIT.
    """
    url = f"{BASE_URL}/Deudas/Historicas/{cuit}"
    r = requests.get(url, verify=VERIFY_SSL, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def cheques_rechazados_por_cuit(cuit: str):
    """
    Consulta cheques rechazados para un CUIT.
    """
    url = f"{BASE_URL}/Deudas/ChequesRechazados/{cuit}"
    r = requests.get(url, verify=VERIFY_SSL, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()