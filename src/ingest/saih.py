"""Cliente para descargar informes de lluvia del SAIH-CHJ.

Como la CHJ no expone una API REST, descargamos directamente los
PDFs de informes diarios publicados en saih.chj.es/docs/.
"""
import time
from pathlib import Path
import requests
from datetime import date, timedelta
from src.config import RAW_DIR

BASE = "https://saih.chj.es/docs"


def descargar_pdf(nombre_archivo: str, destino: Path, retries: int = 3) -> bool:
    """Descarga un PDF del SAIH si no existe ya en destino.

    Devuelve True si se ha descargado (o ya existía), False si falló.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        print(f"  {nombre_archivo}: ya existe, saltando")
        return True

    url = f"{BASE}/{nombre_archivo}"
    for attempt in range(retries):
        print("Comienza la descarga:")
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 404:
                print(f"  {nombre_archivo}: NO ENCONTRADO (404)")
                return False
            r.raise_for_status()
            destino.write_bytes(r.content)
            tamaño_kb = len(r.content) / 1024
            print(f"  {nombre_archivo}: OK ({tamaño_kb:.1f} KB)")
            return True
        except (requests.ConnectionError, requests.Timeout) as e:
            espera = 5 * (attempt + 1)
            print(f"  {nombre_archivo}: error (intento {attempt+1}). Reintento en {espera}s...")
            time.sleep(espera)
    print(f"  {nombre_archivo}: FALLO tras {retries} intentos")
    return False


# Sufijos de informes de 1 día (los que queremos para entrenar el modelo).
# Saltamos PLU2/PLU3/etc. porque son acumulados de varios días.
SUFIJOS_UN_DIA = ["PLU.pdf", "PLU1.pdf"]


def descargar_pdf_silencioso(nombre_archivo: str, destino: Path, retries: int = 2) -> bool:
    """Versión silenciosa de descargar_pdf, para usar en bucles largos.

    Devuelve True si descargó o ya existía, False si dio 404 o falló.
    """
    if destino.exists():
        return True
    url = f"{BASE}/{nombre_archivo}"
    for _ in range(retries):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 404:
                return False
            r.raise_for_status()
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(r.content)
            return True
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(3)
    return False


def descargar_historico(fecha_ini: date, fecha_fin: date, dir_out: Path):
    """Descarga todos los informes de 1 día publicados entre dos fechas.

    El archivo de cada día tiene como prefijo la fecha del día SIGUIENTE
    (porque el informe se publica al día siguiente del que cubre).
    Por cada día se prueba primero PLU.pdf; si no existe, se prueba PLU1.pdf.
    """
    dir_out.mkdir(parents=True, exist_ok=True)
    dias_totales = (fecha_fin - fecha_ini).days + 1

    descargados, ya_existian, omitidos = 0, 0, 0
    fecha = fecha_ini
    contador = 0

    print(f"Periodo: {fecha_ini} → {fecha_fin} ({dias_totales} días)")
    print("Esto tardará un rato. Imprimiré progreso cada 50 días.\n")

    while fecha <= fecha_fin:
        # El nombre del archivo lleva la fecha de PUBLICACIÓN (día siguiente).
        fecha_pub = fecha + timedelta(days=1)
        prefijo = fecha_pub.strftime("%Y%m%d")

        encontrado = False
        for sufijo in SUFIJOS_UN_DIA:
            destino = dir_out / (prefijo + sufijo)
            if destino.exists():
                ya_existian += 1
                encontrado = True
                break
            if descargar_pdf_silencioso(prefijo + sufijo, destino):
                descargados += 1
                encontrado = True
                break

        if not encontrado:
            omitidos += 1

        contador += 1
        if contador % 50 == 0:
            print(f"  Día {contador}/{dias_totales}: "
                  f"nuevos={descargados}, existían={ya_existian}, sin_informe={omitidos}")

        fecha += timedelta(days=1)
        time.sleep(0.8)  # cortesía con el servidor

    print(f"\n{'='*50}")
    print(f"RESUMEN FINAL")
    print(f"  Días procesados: {dias_totales}")
    print(f"  Descargados nuevos: {descargados}")
    print(f"  Ya existían: {ya_existian}")
    print(f"  Sin informe disponible (404): {omitidos}")


# Catálogo de informes correspondientes al evento DANA octubre-noviembre 2024.
# El nombre del archivo es siempre el día SIGUIENTE al que cubre el informe.
INFORMES_DANA_2024 = {
    "25-27 oct 2024": "20241028PLU3.pdf",
    "28 oct 2024":    "20241029PLU.pdf",
    "29 oct 2024":    "20241030PLU.pdf",   # El día catastrófico
    "30 oct 2024":    "20241031PLU.pdf",
    "31 oct 2024":    "20241101PLU.pdf",
    "1 nov 2024":     "20241102PLU.pdf",
    "3 nov 2024":     "20241104PLU.pdf",
    "6 nov 2024":     "20241107PLU.pdf",
    "12 nov 2024":    "20241113PLU.pdf",
    "13 nov 2024":    "20241114PLU1.pdf",
}


if __name__ == "__main__":
    out = RAW_DIR / "saih"
    out.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print("1) INFORMES PUNTUALES DANA 2024")
    print("=" * 50)
    for descripcion, nombre_archivo in INFORMES_DANA_2024.items():
        print(f"\n{descripcion}:")
        descargar_pdf(nombre_archivo, out / nombre_archivo)
        time.sleep(1)

    print("\n" + "=" * 50)
    print("2) HISTÓRICO COMPLETO 2020-2024 (solo informes de 1 día)")
    print("=" * 50)
    descargar_historico(
        fecha_ini=date(2020, 1, 1),
        fecha_fin=date(2024, 12, 31),
        dir_out=out,
    )