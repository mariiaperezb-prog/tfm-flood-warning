"""Productor Kafka — reproduce el evento DANA como flujo en tiempo real.

Lee el dataset de features de la DANA y envía los registros a Kafka
día a día, simulando la llegada de datos de sensores en tiempo real.
"""
import json
import time
from pathlib import Path

import pandas as pd
from kafka import KafkaProducer

# --- Configuración ---
TOPIC = "lluvia-saih"
BOOTSTRAP = "localhost:9092"
DATASET = Path(__file__).resolve().parents[2] / "data/processed/features_modelo_RECONSTRUCCION.parquet"

# Periodo del evento DANA que vamos a reproducir
FECHA_INICIO = "2024-10-25"
FECHA_FIN = "2024-11-03"

# Segundos de pausa entre un día y el siguiente (controla la velocidad del replay)
SEGUNDOS_POR_DIA = 3


def crear_productor():
    """Crea el productor Kafka, serializando los mensajes como JSON."""
    return KafkaProducer(
        bootstrap_servers=BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def main():
    print("=" * 55)
    print("PRODUCTOR KAFKA — Reproducción del evento DANA 2024")
    print("=" * 55)

    # Cargamos el dataset y filtramos al periodo del evento
    df = pd.read_parquet(DATASET)
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df[
        (df["fecha"] >= FECHA_INICIO) & (df["fecha"] <= FECHA_FIN)
    ].sort_values("fecha")

    print(f"Registros a reproducir: {len(df)}")
    print(f"Periodo: {FECHA_INICIO} a {FECHA_FIN}")
    print(f"Velocidad: {SEGUNDOS_POR_DIA}s por día simulado\n")

    productor = crear_productor()

    # Recorremos día a día
    dias = sorted(df["fecha"].unique())
    total_enviados = 0

    for dia in dias:
        registros_dia = df[df["fecha"] == dia]
        fecha_str = pd.Timestamp(dia).strftime("%Y-%m-%d")

        print(f"[{fecha_str}] enviando {len(registros_dia)} estaciones...")

        for _, fila in registros_dia.iterrows():
            # Construimos el mensaje con los datos de la estación
            mensaje = {
                "fecha": fecha_str,
                "estacion": fila["descripcion"],
                "subcuenca": fila["subcuenca"],
                "lat": float(fila["lat"]),
                "lon": float(fila["lon"]),
                "precip_dia": float(fila["precip_dia"]),
                "precip_3d": float(fila["precip_3d"]),
                "precip_7d": float(fila["precip_7d"]),
                "precip_previa_7d": float(fila["precip_previa_7d"]),
                "elevacion": float(fila["elevacion"]),
                "pendiente": float(fila["pendiente"]),
                "mes": int(fila["mes"]),
                "temporada_lluvias": int(fila["temporada_lluvias"]),
                "precip_tendencia": float(fila["precip_tendencia"]),
                "ratio_reciente": float(fila["ratio_reciente"]),
                "precip_max_3d": float(fila["precip_max_3d"]),
                "dias_consecutivos_lluvia": int(fila["dias_consecutivos_lluvia"]),
            }
            productor.send(TOPIC, value=mensaje)
            total_enviados += 1

        # Forzamos el envío de todo lo acumulado antes de pasar al siguiente día
        productor.flush()
        print(f"           ...enviado. Total acumulado: {total_enviados}")

        # Pausa: simula el paso del tiempo
        time.sleep(SEGUNDOS_POR_DIA)

    productor.close()
    print(f"\n{'='*55}")
    print(f"Reproducción completada. {total_enviados} mensajes enviados.")


if __name__ == "__main__":
    main()