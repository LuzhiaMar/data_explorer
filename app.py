"""Aplicación Streamlit para análisis exploratorio automático de datos."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Explorador automático de datos",
    page_icon="📊",
    layout="wide",
)

DATE_HINTS = ("fecha", "date")
ANALYTIC_LABELS = {
    "numeric": "Numérica",
    "categorical": "Categórica",
    "text": "Texto",
    "boolean": "Booleana",
    "datetime": "Fecha/hora",
}


@st.cache_data(show_spinner=False)
def read_csv_file(file_bytes: bytes) -> pd.DataFrame:
    """Lee un CSV probando codificaciones y detección automática de separador."""
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(BytesIO(file_bytes), sep=None, engine="python", encoding=encoding)
        except Exception as exc:
            last_error = exc
    raise ValueError(f"No fue posible interpretar el CSV: {last_error}")


@st.cache_data(show_spinner=False)
def read_excel_file(file_bytes: bytes, extension: str) -> pd.DataFrame:
    """Lee el primer libro de Excel con el motor apropiado."""
    engine = "openpyxl" if extension == ".xlsx" else "xlrd"
    return pd.read_excel(BytesIO(file_bytes), engine=engine)


@st.cache_data(show_spinner=False)
def load_dataset(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Carga, normaliza encabezados y reconoce fechas por el nombre de columna."""
    extension = Path(filename).suffix.lower()
    if extension == ".csv":
        df = read_csv_file(file_bytes)
    elif extension in {".xlsx", ".xls"}:
        df = read_excel_file(file_bytes, extension)
    else:
        raise ValueError("Formato no admitido. Use CSV, XLSX o XLS.")

    df = df.copy()
    df.columns = [str(column).strip() for column in df.columns]
    for column in df.columns:
        normalized_name = column.lower()
        if any(hint in normalized_name for hint in DATE_HINTS):
            converted = pd.to_datetime(df[column], errors="coerce")
            # Evita destruir columnas cuyo nombre sugiere fecha pero casi ningún valor lo es.
            original_non_null = int(df[column].notna().sum())
            conversion_rate = converted.notna().sum() / original_non_null if original_non_null else 0
            if original_non_null == 0 or conversion_rate >= 0.60:
                df[column] = converted
    return df


def analytic_type(series: pd.Series) -> str:
    """Interpreta el tipo analítico sin alterar los datos."""
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    non_null = series.dropna()
    unique_count = non_null.nunique(dropna=True)
    ratio = unique_count / len(non_null) if len(non_null) else 0
    return "categorical" if unique_count <= 30 or ratio <= 0.20 else "text"


def columns_by_type(df: pd.DataFrame, kinds: Iterable[str]) -> list[str]:
    accepted = set(kinds)
    return [column for column in df.columns if analytic_type(df[column]) in accepted]


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Genera CSV UTF-8 con BOM en memoria."""
    return df.to_csv(index=False).encode("utf-8-sig")


def type_summary(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Variable": df.columns,
            "Tipo de Pandas": [str(df[column].dtype) for column in df.columns],
            "Tipo analítico": [ANALYTIC_LABELS[analytic_type(df[column])] for column in df.columns],
            "Valores no nulos": [int(df[column].notna().sum()) for column in df.columns],
            "Valores únicos": [int(df[column].nunique(dropna=True)) for column in df.columns],
        }
    )


def missing_summary(df: pd.DataFrame) -> pd.DataFrame:
    missing = df.isna().sum()
    denominator = len(df)
    percentage = missing.div(denominator).mul(100) if denominator else missing.astype(float)
    return (
        pd.DataFrame(
            {
                "Variable": missing.index,
                "Valores faltantes": missing.values.astype(int),
                "Porcentaje faltante": percentage.values,
            }
        )
        .sort_values(["Porcentaje faltante", "Variable"], ascending=[False, True])
        .reset_index(drop=True)
    )


def descriptive_table(df: pd.DataFrame, option: str) -> pd.DataFrame:
    numeric = columns_by_type(df, ["numeric"])
    categorical = columns_by_type(df, ["categorical", "text", "boolean"])
    blocks: list[pd.DataFrame] = []

    if option in {"Todas las variables", "Solo variables numéricas"} and numeric:
        numeric_desc = df[numeric].describe().T.rename(
            columns={
                "count": "Conteo", "mean": "Media", "std": "Desviación estándar",
                "min": "Mínimo", "25%": "Primer cuartil", "50%": "Mediana",
                "75%": "Tercer cuartil", "max": "Máximo",
            }
        )
        numeric_desc.insert(0, "Tipo", "Numérica")
        blocks.append(numeric_desc)

    if option in {"Todas las variables", "Solo variables categóricas"} and categorical:
        categorical_desc = df[categorical].astype("object").describe().T.rename(
            columns={"count": "Conteo", "unique": "Valores únicos", "top": "Más frecuente", "freq": "Frecuencia dominante"}
        )
        categorical_desc.insert(0, "Tipo", "Categórica/texto")
        blocks.append(categorical_desc)

    if not blocks:
        raise ValueError("No existen variables del tipo seleccionado.")
    return pd.concat(blocks, axis=0, sort=False).rename_axis("Variable").reset_index()


def detect_outliers(df: pd.DataFrame, variables: list[str], factor: float) -> pd.DataFrame:
    """Devuelve una fila por cada detección IQR, conservando el índice original."""
    detections: list[pd.DataFrame] = []
    for variable in variables:
        values = pd.to_numeric(df[variable], errors="coerce")
        clean = values.dropna()
        if clean.empty:
            continue
        q1, q3 = clean.quantile([0.25, 0.75])
        iqr = q3 - q1
        lower, upper = q1 - factor * iqr, q3 + factor * iqr
        mask = values.lt(lower) | values.gt(upper)
        if mask.any():
            found = df.loc[mask].copy()
            found.insert(0, "Fila original", found.index)
            found.insert(1, "Variable atípica", variable)
            found.insert(2, "Valor atípico", values.loc[mask].values)
            found.insert(3, "Límite inferior", lower)
            found.insert(4, "Límite superior", upper)
            detections.append(found)
    return pd.concat(detections, ignore_index=True) if detections else pd.DataFrame()


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Dibuja filtros laterales y devuelve el conjunto filtrado."""
    filtered = df.copy()
    date_columns = columns_by_type(df, ["datetime"])
    categorical_columns = columns_by_type(df, ["categorical", "boolean"])
    numeric_columns = columns_by_type(df, ["numeric"])

    st.sidebar.header("Filtros interactivos")
    if date_columns:
        with st.sidebar.expander("Filtros por fecha"):
            selected_dates = st.multiselect("Variables de fecha", date_columns, key="date_filter_columns")
            for column in selected_dates:
                non_null = df[column].dropna()
                if non_null.empty:
                    st.info(f"{column}: no contiene fechas válidas.")
                    continue
                min_date, max_date = non_null.min().date(), non_null.max().date()
                start, end = st.date_input(
                    f"Rango de {column}", value=(min_date, max_date), min_value=min_date,
                    max_value=max_date, key=f"date_range_{column}",
                )
                if start > end:
                    start, end = end, start
                current = filtered[column]
                mask = current.isna() | current.dt.date.between(start, end)
                filtered = filtered.loc[mask]

    if categorical_columns:
        with st.sidebar.expander("Filtros categóricos"):
            selected_categorical = st.multiselect(
                "Variables categóricas", categorical_columns, key="categorical_filter_columns"
            )
            for column in selected_categorical:
                options = df[column].dropna().unique().tolist()
                selected = st.multiselect(
                    f"Categorías de {column}", options, default=options, key=f"categories_{column}"
                )
                current = filtered[column]
                filtered = filtered.loc[current.isna() | current.isin(selected)]

    if numeric_columns:
        with st.sidebar.expander("Filtros numéricos"):
            selected_numeric = st.multiselect("Variables numéricas", numeric_columns, key="numeric_filter_columns")
            for column in selected_numeric:
                non_null = pd.to_numeric(df[column], errors="coerce").dropna()
                if non_null.empty:
                    st.info(f"{column}: no contiene valores numéricos válidos.")
                    continue
                minimum, maximum = float(non_null.min()), float(non_null.max())
                if np.isclose(minimum, maximum):
                    st.caption(f"{column}: valor constante {minimum:g}")
                    continue
                selected_range = st.slider(
                    f"Rango de {column}", min_value=minimum, max_value=maximum,
                    value=(minimum, maximum), key=f"numeric_range_{column}",
                )
                current = pd.to_numeric(filtered[column], errors="coerce")
                filtered = filtered.loc[current.isna() | current.between(*selected_range)]

    st.sidebar.metric("Registros resultantes", len(filtered))
    return filtered


st.title("Explorador automático de datos")
st.write(
    "Carga un archivo y obtén un análisis exploratorio interactivo de su estructura, calidad, "
    "estadísticas, distribuciones, correlaciones y valores atípicos."
)

st.sidebar.header("Carga del dataset")
uploaded_file = st.sidebar.file_uploader(
    "Selecciona un archivo", type=["csv", "xlsx", "xls"],
    help="El archivo se procesa en memoria durante la sesión.",
)

if uploaded_file is None:
    st.info("Para comenzar, carga un archivo desde la barra lateral.")
    left, right = st.columns(2)
    with left:
        st.subheader("Etapas de uso")
        st.markdown("1. **Cargar** un archivo CSV, XLSX o XLS.\n2. **Explorar** los resultados y aplicar filtros.\n3. **Descargar** los datos filtrados y los valores atípicos.")
    with right:
        st.subheader("Análisis disponibles")
        st.markdown(
            "- Dimensiones, tipos y métricas generales\n- Duplicados y valores faltantes\n"
            "- Estadísticas descriptivas y distribuciones\n- Correlaciones\n"
            "- Detección IQR de valores atípicos\n- Tabla interactiva"
        )
    st.warning("No se generan datos ficticios. Debes proporcionar tu propio conjunto de datos.")
    st.stop()

try:
    original_df = load_dataset(uploaded_file.getvalue(), uploaded_file.name)
except Exception as exc:
    st.error(f"No fue posible procesar el archivo. Verifica su formato y contenido. Detalle: {exc}")
    st.stop()

if original_df.empty or len(original_df.columns) == 0:
    st.warning("El archivo está vacío o no contiene una tabla utilizable.")
    st.stop()

st.sidebar.success(f"Archivo cargado: {uploaded_file.name}")
filtered_df = apply_filters(original_df)
if filtered_df.empty:
    st.warning("Los filtros no producen registros. Ajusta los filtros de la barra lateral para continuar.")
    st.stop()

rows, columns = filtered_df.shape
duplicates_count = int(filtered_df.duplicated().sum())
missing_cells = int(filtered_df.isna().sum().sum())
metric_columns = st.columns(4)
metric_columns[0].metric("Filas", f"{rows:,}")
metric_columns[1].metric("Columnas", f"{columns:,}")
metric_columns[2].metric("Duplicados completos", f"{duplicates_count:,}")
metric_columns[3].metric("Celdas faltantes", f"{missing_cells:,}")
st.caption(f"Archivo: **{uploaded_file.name}** | Dimensión filtrada: **{filtered_df.shape[0]} filas × {filtered_df.shape[1]} columnas**")

(
    tab_summary, tab_quality, tab_stats, tab_distributions,
    tab_correlations, tab_outliers, tab_table,
) = st.tabs(
    ["Resumen y tipos", "Calidad de datos", "Estadísticas", "Distribuciones",
     "Correlaciones", "Valores atípicos", "Tabla ordenable"]
)

with tab_summary:
    st.subheader("Dimensiones del dataset")
    st.write(f"El archivo **{uploaded_file.name}** contiene, después de filtrar, **{rows} filas** y **{columns} columnas**.")
    st.subheader("Tipos de variables")
    st.dataframe(type_summary(filtered_df), use_container_width=True, hide_index=True)

with tab_quality:
    st.subheader("Registros duplicados")
    duplicate_rows = filtered_df.loc[filtered_df.duplicated(keep=False)]
    if duplicate_rows.empty:
        st.success("No se encontraron registros completamente duplicados.")
    else:
        st.warning(f"Se encontraron {duplicates_count} duplicados adicionales y {len(duplicate_rows)} filas involucradas.")
        st.dataframe(duplicate_rows, use_container_width=True)

    st.subheader("Valores faltantes")
    missing = missing_summary(filtered_df)
    st.dataframe(
        missing.style.format({"Porcentaje faltante": "{:.2f}%"}),
        use_container_width=True, hide_index=True,
    )
    chart_data = missing.loc[missing["Porcentaje faltante"] > 0]
    if chart_data.empty:
        st.success("No se encontraron valores faltantes.")
    else:
        figure = px.bar(
            chart_data, x="Variable", y="Porcentaje faltante", text_auto=".2f",
            title="Porcentaje de valores faltantes por variable",
        )
        figure.update_yaxes(range=[0, 100], ticksuffix="%")
        st.plotly_chart(figure, use_container_width=True)

with tab_stats:
    st.subheader("Estadísticas descriptivas")
    stats_option = st.radio(
        "Variables a incluir",
        ["Todas las variables", "Solo variables numéricas", "Solo variables categóricas"],
        horizontal=True,
    )
    try:
        st.dataframe(descriptive_table(filtered_df, stats_option), use_container_width=True, hide_index=True)
    except (ValueError, TypeError) as exc:
        st.info(str(exc))

with tab_distributions:
    st.subheader("Distribuciones")
    variable = st.selectbox("Selecciona una variable", filtered_df.columns)
    kind = analytic_type(filtered_df[variable])
    if kind == "numeric":
        bins = st.slider("Número de intervalos", 5, 100, 30)
        histogram = px.histogram(filtered_df, x=variable, nbins=bins, title=f"Histograma de {variable}")
        st.plotly_chart(histogram, use_container_width=True)
        group_candidates = columns_by_type(filtered_df, ["categorical", "boolean"])
        group = st.selectbox("Agrupar diagrama de caja por", ["Sin agrupación"] + group_candidates)
        box = px.box(
            filtered_df, x=None if group == "Sin agrupación" else group, y=variable,
            points="outliers", title=f"Diagrama de caja de {variable}",
        )
        st.plotly_chart(box, use_container_width=True)
    else:
        display_values = filtered_df[variable].astype("object").where(filtered_df[variable].notna(), "(Faltante)")
        frequency = display_values.value_counts(dropna=False).head(30).rename_axis("Categoría").reset_index(name="Frecuencia")
        if display_values.nunique(dropna=False) > 30:
            st.info("Se muestran las 30 categorías más frecuentes.")
        bar = px.bar(frequency, x="Categoría", y="Frecuencia", title=f"Frecuencias de {variable}")
        st.plotly_chart(bar, use_container_width=True)

with tab_correlations:
    st.subheader("Correlaciones")
    numeric_columns = columns_by_type(filtered_df, ["numeric"])
    if len(numeric_columns) < 2:
        st.info("Se requieren al menos dos variables numéricas para calcular correlaciones.")
    else:
        correlation_columns = st.multiselect("Variables", numeric_columns, default=numeric_columns)
        method_label = st.selectbox("Método", ["Pearson", "Spearman", "Kendall"])
        if len(correlation_columns) < 2:
            st.warning("Selecciona al menos dos variables numéricas.")
        else:
            correlation = filtered_df[correlation_columns].corr(method=method_label.lower())
            heatmap = go.Figure(
                data=go.Heatmap(
                    z=correlation.values, x=correlation.columns, y=correlation.index,
                    zmin=-1, zmax=1, colorscale="RdBu", reversescale=True,
                    text=np.round(correlation.values, 2), texttemplate="%{text}",
                    hovertemplate="%{y} vs %{x}: %{z:.3f}<extra></extra>",
                )
            )
            heatmap.update_layout(title=f"Matriz de correlación de {method_label}")
            st.plotly_chart(heatmap, use_container_width=True)
            st.dataframe(correlation.style.format("{:.3f}"), use_container_width=True)
    st.caption("Una correlación describe asociación estadística y no implica causalidad.")

with tab_outliers:
    st.subheader("Valores atípicos por rango intercuartílico")
    numeric_columns = columns_by_type(filtered_df, ["numeric"])
    if not numeric_columns:
        st.info("El dataset filtrado no contiene variables numéricas.")
        outlier_results = pd.DataFrame()
    else:
        selected_outlier_columns = st.multiselect("Variables numéricas", numeric_columns, default=numeric_columns)
        factor = st.slider("Factor IQR", 1.0, 3.0, 1.5, 0.1)
        outlier_results = detect_outliers(filtered_df, selected_outlier_columns, factor)
        st.metric("Detecciones", len(outlier_results))
        if outlier_results.empty:
            st.success("No se detectaron valores atípicos con la configuración seleccionada.")
        else:
            outlier_counts = outlier_results["Variable atípica"].value_counts().rename_axis("Variable").reset_index(name="Atípicos")
            st.plotly_chart(
                px.bar(outlier_counts, x="Variable", y="Atípicos", text_auto=True, title="Atípicos por variable"),
                use_container_width=True,
            )
            st.dataframe(outlier_results, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar valores atípicos", data=dataframe_to_csv_bytes(outlier_results),
            file_name="valores_atipicos.csv", mime="text/csv", disabled=outlier_results.empty,
        )
    st.caption("Un valor atípico no necesariamente representa un error. Debe evaluarse con conocimiento del contexto.")

with tab_table:
    st.subheader("Tabla interactiva y ordenable")
    visible_columns = st.multiselect("Columnas visibles", filtered_df.columns, default=list(filtered_df.columns))
    if not visible_columns:
        st.info("Selecciona al menos una columna para visualizar la tabla.")
    else:
        st.dataframe(filtered_df[visible_columns], use_container_width=True, hide_index=True, height=520)
    st.download_button(
        "Descargar datos filtrados", data=dataframe_to_csv_bytes(filtered_df),
        file_name="datos_filtrados.csv", mime="text/csv",
    )

st.divider()
st.warning(
    "Tratamiento responsable: los datos se procesan durante la sesión de la aplicación. "
    "Evita cargar información personal, confidencial o sensible. Este análisis exploratorio no reemplaza "
    "la interpretación experta. Una correlación no implica causalidad y un valor atípico no necesariamente es un error."
)
