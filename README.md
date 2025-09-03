
# Situación Crediticia – Consultor BCRA (Demo)

App de Streamlit para consultar **Central de Deudores del BCRA** por CUIT.

## Endpoints usados (intentos)
- **Deudas (último período)**: `https://api.bcra.gob.ar/centraldedeudores/v1.0/Deudas/{CUIT}` ✅
- **Deudas históricas**: `https://api.bcra.gob.ar/centraldedeudores/v1.0/DeudasHistoricas/{CUIT}` *(si no existe, la app lo indica y no rompe)*
- **Cheques rechazados (Central)**: `https://api.bcra.gob.ar/centraldedeudores/v1.0/ChequesRechazados/{CUIT}` *(si no existe, la app lo indica y no rompe)*
- **Cheques rechazados (Estadísticas BCRA)**: `https://api.estadisticasbcra.com/cheques_rechazados_por_identificacion/{CUIT}` *(opcional, requiere token en `BCRA_TOKEN`)*

> La app **no inventa datos**: si un endpoint no está disponible o devuelve 404/empty, muestra “No disponible”.

## Variables de entorno
- `VERIFY_SSL` = `true` para verificar certs (por defecto **false**).
- `HTTP_PROXY` / `HTTPS_PROXY` si tu red usa proxy.
- `BCRA_TOKEN` si querés usar la ruta de **Estadísticas BCRA** para cheques.

## Correr local
```powershell
cd situacion-crediticia
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# opcional: certs verdaderos
# $env:VERIFY_SSL="true"

streamlit run web\app.py
```
