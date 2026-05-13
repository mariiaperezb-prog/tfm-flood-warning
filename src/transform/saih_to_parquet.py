"""Procesa los PDFs SAIH descargados y los unifica en un Parquet."""
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pdfplumber

from src.config import RAW_DIR, PROCESSED_DIR

PATRON_FILA = re.compile(r"^(.+?)\s+\(([A-Z]{1,2})\)\s+(\d+\.?\d*)\s*$")
PATRON_SUBCUENCA = re.compile(r"^\*\s*CUENCA\s+(.+?)(?:\.|$)", re.IGNORECASE)
PATRON_FECHA = re.compile(r"Fecha\s+inicial:\s+(\d{1,2})\s+(\w+)\s+(\d{4})")

PROVINCIAS_VALIDAS = {"V", "CS", "TE", "T", "CU", "AB", "A"}
MESES_ES = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}


def extraer_fecha_inicial(texto: str):
    """Encuentra la fecha inicial del periodo cubierto por el PDF."""
    m = PATRON_FECHA.search(texto)
    if not m:
        return None
    dia = int(m.group(1))
    mes = MESES_ES.get(m.group(2)[:3].upper())
    anio = int(m.group(3))
    if mes is None:
        return None
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def parsear_saih_pdf(pdf_path: Path) -> pd.DataFrame:
    """Extrae todas las filas de datos de un PDF del SAIH."""
    filas = []
    subcuenca = None
    fecha = None

    with pdfplumber.open(pdf_path) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            if fecha is None:
                fecha = extraer_fecha_inicial(texto)
            for linea in texto.splitlines():
                linea = linea.strip()
                m_sub = PATRON_SUBCUENCA.match(linea)
                if m_sub:
                    subcuenca = m_sub.group(1).strip().rstrip(".")
                    continue
                m = PATRON_FILA.match(linea)
                if m and m.group(2) in PROVINCIAS_VALIDAS:
                    filas.append({
                        "fecha": fecha,
                        "subcuenca": subcuenca,
                        "descripcion": m.group(1).strip(),
                        "provincia": m.group(2),
                        "precipitacion_mm": float(m.group(3)),
                    })
    return pd.DataFrame(filas)


def unificar_pdfs_saih(dir_pdfs: Path) -> pd.DataFrame:
    """Procesa todos los PDFs SAIH del directorio y los une."""
    dfs = []
    for pdf_path in sorted(dir_pdfs.glob("*.pdf")):
        df = parsear_saih_pdf(pdf_path)
        if df.empty:
            print(f"  {pdf_path.name}: 0 filas extraídas")
            continue
        fecha = df["fecha"].iloc[0]
        print(f"  {pdf_path.name}: {len(df)} filas (fecha: {fecha})")
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


if __name__ == "__main__":
    print("Procesando PDFs del SAIH-CHJ...")
    df = unificar_pdfs_saih(RAW_DIR / "saih")

    if df.empty:
        print("No se extrajo ningún dato.")
        raise SystemExit(0)

    df["fecha"] = pd.to_datetime(df["fecha"])
    df = (df.sort_values(["fecha", "subcuenca", "descripcion"])
            .drop_duplicates(["fecha", "descripcion"])
            .reset_index(drop=True))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "saih_dana_2024.parquet"
    df.to_parquet(out, index=False)

    print(f"\nGuardado: {out}")
    print(f"  Filas totales: {len(df)}")
    print(f"  Estaciones únicas: {df['descripcion'].nunique()}")
    print(f"  Periodo: {df['fecha'].min().date()} → {df['fecha'].max().date()}")
    print(f"  Tamaño: {out.stat().st_size / 1024:.1f} KB")