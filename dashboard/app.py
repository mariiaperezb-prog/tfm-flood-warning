"""Dashboard de alerta temprana de inundaciones — caso DANA 2024.

Cuadro de mando que reproduce la evolución del evento DANA, mostrando
las alertas de riesgo generadas por el sistema sobre un mapa interactivo.
"""
import time
from pathlib import Path

import pandas as pd
import folium
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

# --- Configuración de rutas ---
RAIZ = Path(__file__).resolve().parents[1]
FEATURES_PATH = RAIZ / "data/processed/features_modelo_RECONSTRUCCION.parquet"
ALERTAS_PATH = RAIZ / "data/processed/alertas_streaming.csv"

st.set_page_config(
    page_title="Alerta de Inundaciones — DANA 2024",
    page_icon="🌧️",
    layout="wide",
)


@st.cache_data
def cargar_datos():
    features = pd.read_parquet(FEATURES_PATH)
    features["fecha"] = pd.to_datetime(features["fecha"])
    features = features[
        (features["fecha"] >= "2024-10-25") & (features["fecha"] <= "2024-11-03")
    ]
    alertas = pd.read_csv(ALERTAS_PATH)
    alertas["fecha"] = pd.to_datetime(alertas["fecha"])
    return features, alertas


features, alertas = cargar_datos()
fechas = sorted(features["fecha"].dt.date.unique())


def preparar_datos_dia(fecha):
    """Devuelve las estaciones del día con su probabilidad y nivel de riesgo."""
    datos_dia = features[features["fecha"].dt.date == fecha].copy()
    alertas_dia = alertas[alertas["fecha"].dt.date == fecha]
    probs = dict(zip(alertas_dia["estacion"], alertas_dia["probabilidad_riesgo"]))

    datos_dia["probabilidad"] = datos_dia["descripcion"].map(probs).fillna(0.0)

    def nivel(p):
        if p >= 0.7:
            return "Alto"
        if p >= 0.4:
            return "Medio"
        if p >= 0.3:
            return "Bajo"
        return "Sin alerta"

    datos_dia["nivel"] = datos_dia["probabilidad"].apply(nivel)
    return datos_dia


def mostrar_indicadores(fecha):
    alertas_dia = alertas[alertas["fecha"].dt.date == fecha]
    datos_dia = features[features["fecha"].dt.date == fecha]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Fecha", fecha.strftime("%d %b %Y"))
    col2.metric("Estaciones monitorizadas", len(datos_dia))
    col3.metric("Alertas activas", len(alertas_dia))
    if len(alertas_dia) > 0:
        critica = alertas_dia.loc[alertas_dia["probabilidad_riesgo"].idxmax()]
        col4.metric("Estación más crítica", critica["estacion"][:22],
                    f"{critica['probabilidad_riesgo']:.0%} riesgo")
    else:
        col4.metric("Estación más crítica", "—")


def construir_mapa_plotly(fecha):
    """Mapa con Plotly: ligero y rápido, ideal para la animación."""
    datos = preparar_datos_dia(fecha)

    colores = {
        "Alto": "#d7191c", "Medio": "#fdae61",
        "Bajo": "#ffd633", "Sin alerta": "#3182bd",
    }

    fig = px.scatter_map(
        datos,
        lat="lat", lon="lon",
        color="nivel",
        size="probabilidad" if datos["probabilidad"].max() > 0 else None,
        size_max=20,
        color_discrete_map=colores,
        category_orders={"nivel": ["Alto", "Medio", "Bajo", "Sin alerta"]},
        hover_name="descripcion",
        hover_data={"precip_dia": ":.0f", "probabilidad": ":.0%",
                    "lat": False, "lon": False, "nivel": False},
        zoom=8,
        center={"lat": 39.5, "lon": -0.9},
        map_style="carto-positron",
        height=550,
    )
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0},
                      legend_title="Nivel de riesgo")
    return fig


def construir_mapa_folium(fecha):
    """Mapa con Folium: más detallado, para exploración manual."""
    datos = preparar_datos_dia(fecha)
    m = folium.Map(location=[39.5, -0.9], zoom_start=9, tiles="CartoDB positron")
    colores = {"Alto": "#d7191c", "Medio": "#fdae61",
               "Bajo": "#ffd633", "Sin alerta": "#3182bd"}
    radios = {"Alto": 12, "Medio": 9, "Bajo": 7, "Sin alerta": 4}

    for _, fila in datos.iterrows():
        folium.CircleMarker(
            location=[fila["lat"], fila["lon"]],
            radius=radios[fila["nivel"]],
            color="#333", weight=1, fill=True,
            fill_color=colores[fila["nivel"]], fill_opacity=0.85,
            popup=folium.Popup(
                f"<b>{fila['descripcion']}</b><br>"
                f"Precipitación: {fila['precip_dia']:.0f} mm<br>"
                f"Probabilidad de riesgo: {fila['probabilidad']:.0%}",
                max_width=280),
        ).add_to(m)
    return m

def mostrar_tabla_dia(fecha):
    """Tabla de detalle: estaciones del día ordenadas por probabilidad descendente."""
    datos = preparar_datos_dia(fecha)

    tabla = (
        datos[["descripcion", "subcuenca", "precip_dia", "probabilidad", "nivel"]]
        .sort_values("probabilidad", ascending=False)
        .rename(columns={
            "descripcion": "Estación",
            "subcuenca": "Subcuenca",
            "precip_dia": "Precipitación (mm)",
            "probabilidad": "Probabilidad de riesgo",
            "nivel": "Nivel",
        })
        .reset_index(drop=True)
    )

    st.dataframe(
        tabla,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Probabilidad de riesgo": st.column_config.ProgressColumn(
                "Probabilidad de riesgo",
                min_value=0.0,
                max_value=1.0,
                format="percent",
            ),
            "Precipitación (mm)": st.column_config.NumberColumn(
                "Precipitación (mm)",
                format="%.1f",
            ),
        },
        height=400,
    )
    

# --- Cabecera ---
st.title("🌧️ Sistema de Alerta Temprana de Inundaciones")
st.markdown("**Caso de estudio: DANA de Valencia — octubre/noviembre 2024**")
st.markdown("---")

# --- Controles ---
st.sidebar.header("Controles")
modo = st.sidebar.radio("Modo de visualización",
                        ["Exploración manual", "Reproducción automática"])

if modo == "Exploración manual":
    idx = st.sidebar.select_slider(
        "Día del evento",
        options=list(range(len(fechas))),
        format_func=lambda i: fechas[i].strftime("%d %b %Y"),
    )
    fecha_sel = fechas[idx]

    mostrar_indicadores(fecha_sel)
    st_folium(construir_mapa_folium(fecha_sel),
              width=1100, height=550, key="mapa_manual")
    st.markdown("### Detalle de estaciones")
    mostrar_tabla_dia(fecha_sel)

else:
    velocidad = st.sidebar.slider("Segundos por día", 1, 5, 2)
    placeholder_metricas = st.empty()
    placeholder_mapa = st.empty()
    placeholder_tabla = st.empty()

    if st.sidebar.button("▶ Iniciar reproducción"):
        for fecha in fechas:
            with placeholder_metricas.container():
                mostrar_indicadores(fecha)
            placeholder_mapa.plotly_chart(
                construir_mapa_plotly(fecha),
                use_container_width=True,
                key=f"mapa_{fecha}",
            )
            with placeholder_tabla.container():
                st.markdown("### Detalle de estaciones")
                mostrar_tabla_dia(fecha)
            time.sleep(velocidad)
        st.success("Reproducción completada.")
    else:
        st.info("Pulsa «Iniciar reproducción» en la barra lateral.")
        placeholder_mapa.plotly_chart(
            construir_mapa_plotly(fechas[0]),
            use_container_width=True, key="mapa_inicial",
        )
        with placeholder_tabla.container():
            st.markdown("### Detalle de estaciones")
            mostrar_tabla_dia(fechas[0])

# --- Gráfica de evolución ---
st.markdown("---")
st.subheader("Evolución de las alertas durante el evento")
alertas_por_dia = (alertas.groupby(alertas["fecha"].dt.date)
                          .size().reindex(fechas, fill_value=0))
st.bar_chart(alertas_por_dia, color="#d7191c")