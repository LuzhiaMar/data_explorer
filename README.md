# Explorador automático de datos

Aplicación web en Streamlit para cargar archivos tabulares y ejecutar automáticamente un análisis exploratorio de datos, sin depender de rutas fijas ni datasets predeterminados.

## Funcionalidades

- Carga de archivos desde la interfaz.
- Limpieza de espacios en nombres de columnas y reconocimiento prudente de fechas.
- Filtros por fecha, categoría y rango numérico.
- Métricas de filas, columnas, duplicados y valores faltantes.
- Resumen de tipos analíticos.
- Inspección de duplicados y faltantes.
- Estadísticas descriptivas numéricas y categóricas.
- Histogramas, diagramas de caja y gráficos de frecuencias con Plotly.
- Correlaciones de Pearson, Spearman y Kendall.
- Detección de valores atípicos por IQR.
- Tabla interactiva con selección de columnas.
- Descarga de datos filtrados y valores atípicos en CSV UTF-8 con BOM.

## Formatos admitidos

- CSV
- XLSX mediante `openpyxl`
- XLS mediante `xlrd`

La aplicación procesa el primer libro u hoja disponible en un archivo de Excel.

## Estructura del repositorio

```text
explorador-automatico-datos/
├── app.py
├── requirements.txt
└── README.md
```

No se incluye ningún dataset.

## Instalación

Se recomienda Python 3.11 o 3.12.

```bash
git clone URL_DE_TU_REPOSITORIO
cd explorador-automatico-datos
python -m venv .venv
```

Activa el entorno virtual:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS o Linux
source .venv/bin/activate
```

Instala las dependencias:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Ejecución local

```bash
streamlit run app.py
```

Streamlit abrirá la aplicación en el navegador. Si no lo hace, visita la dirección local indicada en la terminal, normalmente `http://localhost:8501`.

## Despliegue en Streamlit Community Cloud

1. Crea un repositorio en GitHub.
2. Sube `app.py`, `requirements.txt` y `README.md` a la raíz.
3. Inicia sesión en Streamlit Community Cloud con GitHub.
4. Selecciona **Create app**.
5. Elige el repositorio, la rama y `app.py` como archivo principal.
6. Selecciona una versión compatible de Python, preferiblemente 3.11 o 3.12.
7. Pulsa **Deploy**.

La aplicación no necesita secretos, claves ni archivos adicionales.

## Privacidad y uso responsable

Los archivos cargados se procesan durante la sesión. Evita cargar datos personales, confidenciales o sensibles. El análisis es exploratorio, no reemplaza la interpretación experta, una correlación no implica causalidad y un valor atípico no necesariamente representa un error.

## Limitaciones conocidas

- Los archivos muy grandes pueden superar la memoria o el límite de carga del entorno de despliegue.
- En Excel se analiza la primera hoja leída por Pandas.
- La detección automática de fechas se basa en el nombre de la columna y una tasa mínima de conversión válida.
- Las variables de texto con alta cardinalidad no se ofrecen como filtros categóricos para evitar una interfaz excesivamente pesada.
- El método IQR es un criterio estadístico general y puede no ser apropiado para todas las áreas del conocimiento.
- Las correlaciones y algunos gráficos pueden ser lentos con muchas variables o registros.
