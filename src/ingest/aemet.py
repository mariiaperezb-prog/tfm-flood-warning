"""Cliente mínimo para AEMET OpenData.

La API funciona en dos pasos:
  1. Llamas al endpoint -> te devuelve un JSON con dos URLs
  2. Descargas la URL del campo "datos" -> ese es el contenido real
"""
import json
import time
import requests
from datetime import date, timedelta
from src.config import AEMET_API_KEY, RAW_DIR

BASE = "https://opendata.aemet.es/opendata/api"


def aemet_get(endpoint: str, retries: int = 5):
    """Devuelve el JSON de datos de un endpoint AEMET, con reintentos."""
    headers = {"api_key": AEMET_API_KEY}
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(f"{BASE}{endpoint}", headers=headers, timeout=60)
            if r.status_code == 429:                # rate limit
                time.sleep(15)
                continue
            r.raise_for_status()
            meta = r.json()
            if meta.get("estado") != 200 or "datos" not in meta:
                raise RuntimeError(f"Respuesta AEMET inesperada: {meta}")
            # Segunda petición: bajar la URL del campo "datos"
            d = requests.get(meta["datos"], timeout=60)
            d.raise_for_status()
            return d.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            espera = 5 * (attempt + 1)  # 5, 10, 15, 20, 25 segundos
            print(f"  Conexión interrumpida (intento {attempt+1}/{retries}). Reintento en {espera}s...")
            time.sleep(espera)
            continue
    raise RuntimeError(f"Demasiados reintentos. Último error: {last_err}")


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

def clima_diario_periodo_largo(estacion: str, anio_ini: int, anio_fin: int,
                                dias_chunk: int = 180):
    """Descarga datos diarios de una estación para varios años.

    AEMET no permite peticiones de varios años de golpe, así que partimos
    en bloques de `dias_chunk` días y concatenamos.
    """
    todos = []
    fecha = date(anio_ini, 1, 1)
    fin_total = date(anio_fin, 12, 31)

    while fecha <= fin_total:
        fecha_fin_chunk = min(fecha + timedelta(days=dias_chunk), fin_total)
        ini_str = fecha.strftime("%Y-%m-%dT00:00:00UTC")
        fin_str = fecha_fin_chunk.strftime("%Y-%m-%dT23:59:59UTC")
        try:
            chunk = clima_diario(estacion, ini_str, fin_str)
            todos.extend(chunk)
            print(f"  {estacion} {fecha} → {fecha_fin_chunk}: {len(chunk)} registros")
        except Exception as e:
            print(f"  {estacion} {fecha} → {fecha_fin_chunk}: ERROR {e}")
        time.sleep(2)  # cortesía con la API
        fecha = fecha_fin_chunk + timedelta(days=1)

    return todos

def inventario_estaciones():
    """Devuelve el inventario completo de estaciones AEMET."""
    return aemet_get("/valores/climatologicos/inventarioestaciones/todasestaciones")

def parse_coord(s: str):
    """Convierte coordenadas AEMET tipo '412319N' o '0023213W' a grados decimales.
    
    Formato: las dos últimas cifras son segundos, las dos previas minutos,
    el resto grados. La última letra es la dirección (N/S/E/W).
    """
    if not s or len(s) < 7:
        return None
    direccion = s[-1]
    nums = s[:-1]
    seg = int(nums[-2:])
    minu = int(nums[-4:-2])
    grad = int(nums[:-4])
    dec = grad + minu / 60 + seg / 3600
    if direccion in ("S", "W"):
        dec = -dec
    return dec

if __name__ == "__main__":

    # =========================================================
    # Directorios
    # =========================================================
    base_out = RAW_DIR / "aemet"
    base_out.mkdir(parents=True, exist_ok=True)

    hist_out = base_out / "historico"
    hist_out.mkdir(parents=True, exist_ok=True)

    # =========================================================
    # 1) INVENTARIO DE ESTACIONES
    # =========================================================
    inv_path = base_out / "inventario_estaciones.json"

    if not inv_path.exists():
        print("Descargando inventario completo de estaciones...")
        try:
            inventario = inventario_estaciones()

            inv_path.write_text(
                json.dumps(inventario, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            print(f"  OK: {len(inventario)} estaciones guardadas")

        except Exception as e:
            print(f"  ERROR inventario: {e}")

    else:
        print("Inventario ya existe, saltando.")

    # =========================================================
    # 2) EVENTO DANA 2024
    # =========================================================
    estaciones_dana = {
        "8414A": "Valencia (Manises)",
        "8293X": "Utiel",
        "8175": "Requena",
    }

    print("\n==============================")
    print("DESCARGA DANA 2024")
    print("==============================")

    for codigo, nombre in estaciones_dana.items():

        f = base_out / f"{codigo}_dana_2024.json"

        if f.exists():
            print(f"{nombre}: ya existe, saltando")
            continue

        print(f"Descargando {nombre} ({codigo})...")

        try:
            datos = clima_diario(
                estacion=codigo,
                ini="2024-10-25T00:00:00UTC",
                fin="2024-11-05T23:59:59UTC",
            )

            f.write_text(
                json.dumps(datos, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            print(f"  OK: {len(datos)} registros guardados")

        except Exception as e:
            print(f"  ERROR: {e}")

        time.sleep(2)

    # =========================================================
    # 3) HISTÓRICOS 2020-2024
    # =========================================================
    
    estaciones_historico = {
        "8414A": "Valencia (Manises)",
        "8416Y": "Valencia (ciudad)",
        "8293X": "Utiel",
        "8175": "Requena",
        "8058X": "Oliva",
        "8500A": "Castellón",
        "8025": "Buñol",
        "8203O": "Cuenca",
        "8175A": "Albacete (Los Llanos)", # eliminar
    }

    print("\n==============================")
    print("DESCARGA HISTÓRICA 2020-2024")
    print("==============================")

    for codigo, nombre in estaciones_historico.items():

        f = hist_out / f"{codigo}_2020_2024.json"

        if f.exists():
            print(f"{nombre} ({codigo}): ya descargado, saltando")
            continue

        print(f"\nDescargando histórico {nombre} ({codigo})...")

        try:
            datos = clima_diario_periodo_largo(
                codigo,
                anio_ini=2020,
                anio_fin=2024,
            )

            f.write_text(
                json.dumps(datos, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            print(f"  TOTAL: {len(datos)} registros guardados")

        except Exception as e:
            print(f"  ERROR: {e}")

        time.sleep(2)

    print("\nProceso completado.")