"""Configuración global del proyecto: rutas y variables de entorno."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # carga el .env

AEMET_API_KEY = os.getenv("AEMET_API_KEY")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"