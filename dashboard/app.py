"""Dashboard de alerta temprana de inundaciones — caso DANA 2024.

Cuadro de mando que reproduce la evolución del evento DANA, mostrando
las alertas de riesgo generadas por el sistema sobre un mapa interactivo.
"""
import time
from pathlib import Path

import pandas as pd
import folium
import streamlit as st
from streamlit_folium import st_folium

# --- Configuración de rutas ---
RAIZ = Path(__file__).resolve().parents[1]
FEATURES_PATH = RAIZ / "data/processed/features_modelo_RECONSTRUCCION.parquet"
ALERTAS_PATH = RAIZ / "data/processed/alertas_streaming.csv"

# --- Configuración de la página ---
st.set_page_config(
    page_title="Alerta de Inundaciones — DANA 2024",
    page_icon="🌧️",
    layout="wide",
)


# --- Carga de datos (con caché para que no recargue cada vez) ---
@st.cache_data
def cargar_datos():
    features = pd.read_parquet(FEATURES_PATH)
    features["fecha"] = pd.to_datetime(features["fecha"])
    # Filtramos al periodo del evento DANA
    features = features[
        (features["fecha"] >= "2024-10-25") & (features["fecha"] <= "2024-11-03")
    ]

    alertas = pd.read_csv(ALERTAS_PATH)
    alertas["fecha"] = pd.to_datetime(alertas["fecha"])

    return features, alertas


features, alertas = cargar_datos()

# Lista ordenada de fechas del evento
fechas = sorted(features["fecha"].dt.date.unique())


# --- Cabecera ---
st.title("🌧️ Sistema de Alerta Temprana de Inundaciones")
st.markdown("**Caso de estudio: DANA de Valencia — octubre/noviembre 2024**")
st.markdown("---")


# --- Barra lateral: controles ---
st.sidebar.header("Controles")

modo = st.sidebar.radio(
    "Modo de visualización",
    ["Exploración manual", "Reproducción automática"],
)

if modo == "Exploración manual":
    # Slider para elegir el día
    idx_fecha = st.sidebar.select_slider(
        "Día del evento",
        options=list(range(len(fechas))),
        format_func=lambda i: fechas[i].strftime("%d %b %Y"),
    )
    fecha_sel = fechas[idx_fecha]
else:
    velocidad = st.sidebar.slider("Segundos por día", 1, 5, 2)
    fecha_sel = fechas[0]  # se irá actualizando en el bucle


# --- Función que dibuja el mapa para una fecha ---
def construir_mapa(fecha):
    datos_dia = features[features["fecha"].dt.date == fecha].copy()
    alertas_dia = alertas[alertas["fecha"].dt.date == fecha]

    # Conjunto de estaciones que están en alerta ese día
    estaciones_alerta = dict(
        zip(alertas_dia["estacion"], alertas_dia["probabilidad_riesgo"])
    )

    m = folium.Map(location=[39.5, -0.9], zoom_start=9, tiles="CartoDB positron")

    for _, fila in datos_dia.iterrows():
        estacion = fila["descripcion"]
        prob = estaciones_alerta.get(estacion, 0.0)

        # Color según nivel de riesgo
        if prob >= 0.7:
            color, radio = "#d7191c", 12      # rojo — riesgo alto
        elif prob >= 0.4:
            color, radio = "#fdae61", 9       # naranja — riesgo medio
        elif prob >= 0.3:
            color, radio = "#ffff66", 7       # amarillo — riesgo bajo
        else:
            color, radio = "#3182bd", 4       # azul — sin alerta

        folium.CircleMarker(
            location=[fila["lat"], fila["lon"]],
            radius=radio,
            color="#333",
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            popup=folium.Popup(
                f"<b>{estacion}</b><br>"
                f"Precipitación: {fila['precip_dia']:.0f} mm<br>"
                f"Probabilidad de riesgo: {prob:.0%}",
                max_width=280,
            ),
        ).add_to(m)

    return m


# --- Función que muestra los indicadores ---
def mostrar_indicadores(fecha):
    alertas_dia = alertas[alertas["fecha"].dt.date == fecha]
    datos_dia = features[features["fecha"].dt.date == fecha]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Fecha", fecha.strftime("%d %b %Y"))
    col2.metric("Estaciones monitorizadas", len(datos_dia))
    col3.metric("Alertas activas", len(alertas_dia))

    if len(alertas_dia) > 0:
        critica = alertas_dia.loc[alertas_dia["probabilidad_riesgo"].idxmax()]
        col4.metric(
            "Estación más crítica",
            critica["estacion"][:22],
            f"{critica['probabilidad_riesgo']:.0%} riesgo",
        )
    else:
        col4.metric("Estación más crítica", "—")


# --- Visualización principal ---
if modo == "Exploración manual":
    mostrar_indicadores(fecha_sel)
    mapa = construir_mapa(fecha_sel)
    st_folium(mapa, width=1100, height=550, key="mapa_manual")

else:
    # Modo reproducción: animamos día a día
    placeholder_metricas = st.empty()
    placeholder_mapa = st.empty()

    if st.sidebar.button("▶ Iniciar reproducción"):
        for fecha in fechas:
            with placeholder_metricas.container():
                mostrar_indicadores(fecha)
            with placeholder_mapa.container():
                mapa = construir_mapa(fecha)
                st_folium(mapa, width=1100, height=550,
                          key=f"mapa_{fecha}")
            time.sleep(velocidad)
        st.success("Reproducción completada.")
    else:
        st.info("Pulsa «Iniciar reproducción» en la barra lateral.")


# --- Gráfica de evolución temporal (siempre visible, abajo) ---
st.markdown("---")
st.subheader("Evolución de las alertas durante el evento")

alertas_por_dia = (alertas.groupby(alertas["fecha"].dt.date)
                          .size()
                          .reindex(fechas, fill_value=0))

st.bar_chart(alertas_por_dia, color="#d7191c")