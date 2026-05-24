"""Consumidor Kafka — aplica el modelo de riesgo a los datos en streaming.

Consume los mensajes del topic de Kafka, aplica el modelo XGBoost de
predicción de riesgo de inundación y registra las alertas generadas.
"""
import json
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
from kafka import KafkaConsumer

# --- Configuración ---
TOPIC = "lluvia-saih"
BOOTSTRAP = "localhost:9092"

RAIZ = Path(__file__).resolve().parents[2]
MODELO_PATH = RAIZ / "models/modelo_riesgo_inundacion.pkl"
SALIDA_PATH = RAIZ / "data/processed/alertas_streaming.csv"

# Umbral de probabilidad a partir del cual se emite alerta
UMBRAL_ALERTA = 0.30

# Las features que espera el modelo, EN EL MISMO ORDEN que en el entrenamiento
FEATURES = [
    "precip_dia", "precip_3d", "precip_7d", "precip_previa_7d",
    "elevacion", "pendiente", "mes", "temporada_lluvias",
    "precip_tendencia", "ratio_reciente", "precip_max_3d",
    "dias_consecutivos_lluvia",
]


def main():
    print("=" * 55)
    print("CONSUMIDOR KAFKA — Modelo de riesgo de inundación")
    print("=" * 55)

    # Cargamos el modelo entrenado
    modelo = joblib.load(MODELO_PATH)
    print(f"Modelo cargado: {MODELO_PATH.name}")

    # Creamos el consumidor Kafka
    consumidor = KafkaConsumer(
        TOPIC,
        bootstrap_servers=BOOTSTRAP,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",   # leer desde el principio del topic
        consumer_timeout_ms=15000,      # si pasan 15s sin mensajes, termina
        group_id="grupo-modelo-riesgo",
    )
    print(f"Escuchando el topic '{TOPIC}'...\n")

    alertas = []
    procesados = 0

    for mensaje in consumidor:
        dato = mensaje.value
        procesados += 1

        # Preparamos las features en el formato que espera el modelo
        X = pd.DataFrame([{f: dato[f] for f in FEATURES}])

        # El modelo predice la probabilidad de riesgo
        probabilidad = float(modelo.predict_proba(X)[0, 1])
        hay_alerta = probabilidad >= UMBRAL_ALERTA

        # Si supera el umbral, lo registramos como alerta
        if hay_alerta:
            alerta = {
                "fecha": dato["fecha"],
                "estacion": dato["estacion"],
                "subcuenca": dato["subcuenca"],
                "lat": dato["lat"],
                "lon": dato["lon"],
                "precip_dia": dato["precip_dia"],
                "probabilidad_riesgo": round(probabilidad, 3),
            }
            alertas.append(alerta)
            print(f"  ALERTA  [{dato['fecha']}] {dato['estacion'][:40]:40s} "
                  f"prob={probabilidad:.2f}  precip={dato['precip_dia']:.0f}mm")

    consumidor.close()

    # Guardamos todas las alertas generadas
    print(f"\n{'='*55}")
    print(f"Mensajes procesados: {procesados}")
    print(f"Alertas generadas: {len(alertas)}")

    if alertas:
        df_alertas = pd.DataFrame(alertas)
        SALIDA_PATH.parent.mkdir(parents=True, exist_ok=True)
        df_alertas.to_csv(SALIDA_PATH, index=False, encoding="utf-8")
        print(f"Alertas guardadas en: {SALIDA_PATH}")


if __name__ == "__main__":
    main()