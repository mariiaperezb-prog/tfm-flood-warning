"""Unifica los JSON de AEMET en un único DataFrame y lo guarda en Parquet."""
import json
import pandas as pd
from pathlib import Path

from src.config import RAW_DIR, PROCESSED_DIR
from src.ingest.aemet import parse_coord

# Columnas que AEMET devuelve como string con coma decimal española
COLS_NUMERICAS = [
    "tmed", "tmin", "tmax", "prec",
    "velmedia", "racha", "sol",
    "presMax", "presMin",
    "hrMedia", "hrMax", "hrMin",
]


def cargar_json_estacion(path: Path) -> pd.DataFrame:
    with open(path, encoding="utf-8") as f:
        return pd.DataFrame(json.load(f))


def limpiar_aemet(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte fecha a datetime y columnas numéricas (coma → punto)."""
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])

    for col in COLS_NUMERICAS:
        if col in df.columns:
            # AEMET usa 'Ip' (precipitación inapreciable, < 0.1 mm)
            df[col] = (
                df[col].astype(str)
                       .str.replace(",", ".")
                       .replace({"Ip": "0.05", "Acum": None, "nan": None})
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def unificar_historico(dir_historico: Path) -> pd.DataFrame:
    """Carga y une todos los JSON del directorio."""
    dfs = []
    for f in sorted(dir_historico.glob("*.json")):
        df = limpiar_aemet(cargar_json_estacion(f))
        dfs.append(df)
        print(f"  {f.name}: {len(df)} filas")
    return pd.concat(dfs, ignore_index=True)


def enriquecer_con_inventario(df: pd.DataFrame, inv_path: Path) -> pd.DataFrame:
    """Añade lat/lon/altitud_m al DataFrame combinando con el inventario."""
    with open(inv_path, encoding="utf-8") as f:
        inv = pd.DataFrame(json.load(f))
    inv["lat"] = inv["latitud"].apply(parse_coord)
    inv["lon"] = inv["longitud"].apply(parse_coord)
    inv["altitud_m"] = pd.to_numeric(inv["altitud"], errors="coerce")

    inv_min = inv[["indicativo", "lat", "lon", "altitud_m"]]
    return df.merge(inv_min, on="indicativo", how="left")


if __name__ == "__main__":
    base = RAW_DIR / "aemet"

    print("Cargando JSONs históricos...")
    df = unificar_historico(base / "historico")
    print(f"\nTotal filas combinadas: {len(df)}")

    print("\nEnriqueciendo con inventario (lat/lon/altitud)...")
    df = enriquecer_con_inventario(df, base / "inventario_estaciones.json")

    # Ordenar y eliminar duplicados (por si dos chunks se solaparon en una fecha)
    df = (df.sort_values(["indicativo", "fecha"])
            .drop_duplicates(["indicativo", "fecha"])
            .reset_index(drop=True))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "aemet_historico_2020_2024.parquet"
    df.to_parquet(out, index=False)

    print(f"\nGuardado: {out}")
    print(f"  Filas: {len(df)}")
    print(f"  Estaciones: {df['indicativo'].nunique()}")
    print(f"  Periodo: {df['fecha'].min().date()} → {df['fecha'].max().date()}")
    print(f"  Tamaño en disco: {out.stat().st_size / 1024:.1f} KB")