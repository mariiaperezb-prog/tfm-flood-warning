"""Cliente mínimo para AEMET OpenData.

La API funciona en dos pasos:
  1. Llamas al endpoint -> te devuelve un JSON con dos URLs
  2. Descargas la URL del campo "datos" -> ese es el contenido real
"""
import json
import time
import requests
from src.config import AEMET_API_KEY, RAW_DIR

BASE = "https://opendata.aemet.es/opendata/api"


def aemet_get(endpoint: str, retries: int = 3):
    """Devuelve el JSON de datos de un endpoint AEMET."""
    headers = {"api_key": AEMET_API_KEY}
    for _ in range(retries):
        r = requests.get(f"{BASE}{endpoint}", headers=headers, timeout=30)
        if r.status_code == 429:           # rate limit
            time.sleep(10)
            continue
        r.raise_for_status()
        meta = r.json()
        if meta.get("estado") != 200 or "datos" not in meta:
            raise RuntimeError(f"Respuesta AEMET inesperada: {meta}")
        # Segunda petición: bajar la URL del campo "datos"
        d = requests.get(meta["datos"], timeout=60)
        d.raise_for_status()
        return d.json()
    raise RuntimeError("Demasiados reintentos")


def clima_diario(estacion: str, ini: str, fin: str):
    """Datos climatológicos diarios de una estación.

    Fechas en formato 'YYYY-MM-DDTHH:MM:SSUTC'.
    Códigos útiles:
        8414A = Valencia (aeropuerto Manises)
        8416Y = Valencia (ciudad)
        8293X = Utiel
    """
    return aemet_get(
        f"/valores/climatologicos/diarios/datos"
        f"/fechaini/{ini}/fechafin/{fin}/estacion/{estacion}"
    )


if __name__ == "__main__":
    out = RAW_DIR / "aemet"
    out.mkdir(parents=True, exist_ok=True)

    # Tres estaciones representativas de la DANA: ciudad, interior y zona récord
    estaciones = {
        "8414A": "Valencia (Manises)",   # litoral, poco afectada
        "8293X": "Utiel",                # interior, devastada
        "8175": "Requena",               # interior, muy afectada
    }

    for codigo, nombre in estaciones.items():
        print(f"Descargando {nombre} ({codigo})...")
        try:
            datos = clima_diario(
                estacion=codigo,
                ini="2024-10-25T00:00:00UTC",
                fin="2024-11-05T23:59:59UTC",
            )
            f = out / f"{codigo}_dana_2024.json"
            f.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  OK: {len(datos)} registros guardados")
        except Exception as e:
            print(f"  ERROR: {e}")
        time.sleep(2)  # cortesía con la API