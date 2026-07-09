"""
transform/bce.py
Semana 2 - Limpieza de fuentes BCE
Reto Pipeline Macroentorno Ecuador - UTPL - 4to ciclo

Cinco funciones, una por fuente. Cada una recibe la ruta al archivo y
devuelve un DataFrame de pandas ya limpio, listo para cargar a SQLite.

Estructura real de los archivos (confirmada por exploración, no supuesta):

1. PIB.xlsx                              -> limpiar_pib_nominal()
2. retropolacion_1965_2023_PIB real.xlsx -> limpiar_pib_real()
3. VAB 2018-2023.xlsx                    -> limpiar_vab()
4. PETRÓLEO.xlsx + RIESGO PAÍS.xlsx      -> limpiar_petroleo_riesgo()
5. IEE.xlsx                              -> limpiar_iee()
"""

import re
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# 1. PIB REAL ANUAL
# ---------------------------------------------------------------------------
def limpiar_pib_real(ruta_retropolacion: str) -> pd.DataFrame:
    """
    Fuente: retropolacion_1965_2023_PIB real.xlsx, hoja 'PIB pc real'.

    Por qué esta hoja y no otra: el reto pide una tabla con columnas
    Años, PIB_musd, Población, PIB_percapita, Variacion_pct, serie desde 1965.
    La hoja 'PIB pc real' es la única que trae las cinco cifras juntas
    (PIB real total, población, PIB per cápita real y variación anual).
    Las demás hojas del archivo (Serie VAB real, Serie Gasto real, etc.)
    solo tienen el desglose sectorial, no la serie agregada con población.

    Estructura cruda observada:
    - Columnas sin nombre (Unnamed: 0 a Unnamed: 5).
    - Unnamed: 0 está vacía en todas las filas (columna basura, se descarta).
    - Las primeras ~4-5 filas son NaN (espacio del encabezado visual del Excel).
    - Los datos reales viven en Unnamed: 1 (año), Unnamed: 2 (PIB real total),
      Unnamed: 3 (población), Unnamed: 4 (PIB per cápita real),
      Unnamed: 5 (variación % anual).
    - Al final hay 3-4 filas de texto (notas al pie, "Elaboración: BCE") que
      hay que descartar.
    - El año viene como string y el último año incluye la marca "(p)"
      de "provisional" (ej. "2023 (p)") que hay que limpiar.
    """
    df = pd.read_excel(ruta_retropolacion, sheet_name="PIB pc real", header=None)

    # Filtrar solo filas donde la columna 1 (año) hace match con un año de 4
    # dígitos, con o sin sufijo "(p)". Esto descarta de una sola vez las filas
    # vacías del inicio y las notas de texto del final, sin depender de un
    # número fijo de filas a saltar (que podría cambiar si el BCE actualiza
    # el archivo con más años).
    patron_anio = re.compile(r'^\d{4}\s*(\(p\))?$')

    def es_fila_de_datos(valor):
        if pd.isna(valor):
            return False
        return bool(patron_anio.match(str(valor).strip()))

    mask = df[1].apply(es_fila_de_datos)
    datos = df[mask].copy()

    if datos.empty:
        raise ValueError(
            "No se encontraron filas de datos en 'PIB pc real'. "
            "Revisa si el BCE cambió la estructura del archivo."
        )

    datos = datos[[1, 2, 3, 4, 5]]
    datos.columns = ["anio_raw", "pib_real_musd", "poblacion", "pib_percapita_real", "variacion_pct"]

    # Limpiar el año: quitar "(p)" y convertir a entero
    datos["anio"] = (
        datos["anio_raw"]
        .astype(str)
        .str.replace(r"\s*\(p\)", "", regex=True)
        .astype(int)
    )
    datos = datos.drop(columns=["anio_raw"])

    # Tipos numéricos
    for col in ["pib_real_musd", "poblacion", "pib_percapita_real", "variacion_pct"]:
        datos[col] = pd.to_numeric(datos[col], errors="coerce")

    datos = datos.sort_values("anio").reset_index(drop=True)

    # Nota de limpieza (igual que con el PIB nominal): el primer año de la
    # serie tendrá variación % nula porque no hay año anterior con qué
    # compararlo. Es correcto, NO se elimina esa fila.
    datos = datos[["anio", "pib_real_musd", "poblacion", "pib_percapita_real", "variacion_pct"]]

    # Duplicados exactos (por si el Excel repite alguna fila)
    antes = len(datos)
    datos = datos.drop_duplicates(subset=["anio"], keep="last")
    if len(datos) < antes:
        print(f"[pib_real] Se eliminaron {antes - len(datos)} filas duplicadas por año.")

    return datos


# ---------------------------------------------------------------------------
# 2. PIB PER CÁPITA NOMINAL
# ---------------------------------------------------------------------------
def limpiar_pib_nominal(ruta_pib: str) -> pd.DataFrame:
    """
    Fuente: PIB.xlsx, hoja 'Hoja1'.

    Estructura cruda observada:
    - Columnas: AÑO, PIB 2018 = 100, VAR ANUAL PIB, PIB PER CÁPITA NOMINAL,
      Unnamed: 4-7 (completamente vacías, basura), PIB 2018 = 100.1
      (columna duplicada/repetida, basura).
    - Solo nos interesan AÑO y PIB PER CÁPITA NOMINAL para esta función
      (el reto pide únicamente Período + PIB_percapita_nominal_usd aquí;
      el PIB real ya se obtiene de la función anterior).
    - Al final del archivo hay 4 filas de texto con notas al pie
      ("*(p) provisional...", "*PIB en millones de dólares", etc.)
      que hay que descartar.
    - El AÑO viene limpio como número en las filas de datos reales
      (no trae "(p)" en esta hoja, a diferencia de la otra).
    """
    df = pd.read_excel(ruta_pib, sheet_name="Hoja1")

    # Quedarnos solo con filas donde AÑO es un año válido de 4 dígitos.
    # Esto descarta automáticamente las notas al pie del final.
    def es_anio_valido(valor):
        if pd.isna(valor):
            return False
        texto = str(valor).strip()
        return bool(re.match(r'^\d{4}$', texto))

    mask = df["AÑO"].apply(es_anio_valido)
    datos = df[mask].copy()

    datos["periodo"] = pd.to_datetime(datos["AÑO"].astype(int).astype(str) + "-01-01")
    datos["pib_percapita_nominal_usd"] = pd.to_numeric(
        datos["PIB PER CÁPITA NOMINAL"], errors="coerce"
    )

    datos = datos[["periodo", "pib_percapita_nominal_usd"]].sort_values("periodo").reset_index(drop=True)

    antes = len(datos)
    datos = datos.drop_duplicates(subset=["periodo"], keep="last")
    if len(datos) < antes:
        print(f"[pib_nominal] Se eliminaron {antes - len(datos)} filas duplicadas por período.")

    return datos


# ---------------------------------------------------------------------------
# 3. VAB POR PROVINCIA E INDUSTRIA
# ---------------------------------------------------------------------------
def limpiar_vab(ruta_vab: str) -> pd.DataFrame:
    """
    Fuente: VAB 2018-2023.xlsx, hoja 'DATA'.

    Estructura cruda observada:
    - Columnas: AÑO, CÓDIGO PROVINCIA, PROVINCIA, CÓDIGO CANTÓN, CANTÓN,
      SECTOR, VALOR. Ya viene en formato largo (una fila por
      provincia-cantón-sector-año), no hace falta pivotar ni hacer melt().
    - 20,893 filas, de las cuales las últimas 3 son basura:
      2 filas completamente vacías + 1 fila de nota de texto
      ("*Yo convertí a unidades de USD").
    - Aunque el archivo se llama "2018-2023", en realidad contiene también
      el año 2024 (se ve en las últimas filas de datos). Se conserva tal
      cual viene; si tu tutor pide limitarlo estrictamente a 2018-2023,
      hay que filtrar `anio <= 2023` explícitamente.
    - CÓDIGO PROVINCIA y CÓDIGO CANTÓN vienen como float (101.0 en vez de
      101) porque pandas los infiere así al haber NaNs en la columna;
      se convierten a entero una vez descartadas las filas basura.
    - IMPORTANTE - unidades: la nota al pie dice "convertí a unidades de
      USD", es decir los valores de VALOR ya están en USD corrientes,
      NO en miles de USD como sugiere el nombre de columna VAB_miles_usd
      del script base del reto. Esta función expone la columna tal cual
      viene (vab_usd). Si necesitas exactamente "miles de USD" para que
      calce con el nombre de columna del DDL sugerido, divide entre 1000
      al cargar (ver load_to_sqlite.py, está comentado ahí).
    """
    df = pd.read_excel(ruta_vab, sheet_name="DATA")

    # Descartar filas donde AÑO es nulo (las 2 filas vacías) o es texto
    # (la nota al pie "*Yo convertí..."), quedándonos solo con años válidos.
    def es_anio_valido(valor):
        if pd.isna(valor):
            return False
        return bool(re.match(r'^\d{4}$', str(valor).strip()))

    mask = df["AÑO"].apply(es_anio_valido)
    datos = df[mask].copy()

    datos["anio"] = datos["AÑO"].astype(int)
    datos["cod_provincia"] = datos["CÓDIGO PROVINCIA"].astype(int)
    datos["provincia"] = datos["PROVINCIA"].str.strip().str.upper()
    datos["cod_canton"] = datos["CÓDIGO CANTÓN"].astype(int)
    datos["canton"] = datos["CANTÓN"].str.strip().str.upper()
    datos["sector"] = datos["SECTOR"].str.strip()
    datos["vab_usd"] = pd.to_numeric(datos["VALOR"], errors="coerce")

    datos = datos[[
        "anio", "cod_provincia", "provincia", "cod_canton", "canton", "sector", "vab_usd"
    ]].reset_index(drop=True)

    antes = len(datos)
    datos = datos.drop_duplicates()
    if len(datos) < antes:
        print(f"[vab] Se eliminaron {antes - len(datos)} filas duplicadas exactas.")

    nulos_vab = datos["vab_usd"].isna().sum()
    if nulos_vab:
        print(f"[vab] Aviso: {nulos_vab} filas con VALOR no numérico quedaron como NaN.")

    return datos


# ---------------------------------------------------------------------------
# 4. PRECIO PETRÓLEO Y RIESGO PAÍS
# ---------------------------------------------------------------------------
def limpiar_petroleo_riesgo(ruta_petroleo: str, ruta_riesgo: str) -> pd.DataFrame:
    """
    Fuentes: PETRÓLEO.xlsx y RIESGO PAÍS.xlsx (archivos separados, hoja 'Ark1'
    en ambos). El reto anticipaba que podían venir juntos o separados;
    en este caso vienen separados, así que se limpian por separado y
    se combinan con un merge por fecha.

    Estructura cruda observada (idéntica en ambos archivos):
    - La fila 0 de datos (según pandas, que ya usó la fila real 0 del Excel
      como encabezado) contiene en realidad los verdaderos nombres de
      columna como si fueran datos: ['Período', 'Precio Petróleo (WTI)...'].
      Esto pasa porque el Excel probablemente tiene celdas combinadas o un
      título genérico arriba que pandas toma como encabezado por error.
    - Por eso se lee con header=None y skiprows=2, saltando tanto la fila
      que pandas hubiera tomado como header como la fila-encabezado real
      que viene mezclada como dato, y se asignan los nombres de columna
      manualmente.
    - Frecuencia diaria, sin nulos, sin duplicados en la muestra revisada.
    - PETRÓLEO cubre 2025-01-01 a 2026-02-02 (399 filas).
    - RIESGO PAÍS cubre 2025-01-02 a 2026-02-02 (308 filas) — tiene menos
      filas que petróleo porque el riesgo país no se publica en fines de
      semana/feriados, mientras que el archivo de petróleo sí trae esas
      fechas. El merge por fecha dejará NaN en riesgo_pais_pb para esas
      fechas sin publicación; es correcto, no se debe rellenar
      artificialmente.
    """
    petroleo = pd.read_excel(
        ruta_petroleo, sheet_name="Ark1", header=None, skiprows=2,
        names=["fecha", "precio_petroleo_wti"]
    )
    riesgo = pd.read_excel(
        ruta_riesgo, sheet_name="Ark1", header=None, skiprows=2,
        names=["fecha", "riesgo_pais_pb"]
    )

    petroleo["fecha"] = pd.to_datetime(petroleo["fecha"])
    riesgo["fecha"] = pd.to_datetime(riesgo["fecha"])

    petroleo["precio_petroleo_wti"] = pd.to_numeric(petroleo["precio_petroleo_wti"], errors="coerce")
    riesgo["riesgo_pais_pb"] = pd.to_numeric(riesgo["riesgo_pais_pb"], errors="coerce")

    # Outer join: conservamos todas las fechas de ambas fuentes. Si usaras
    # inner join perderías las fechas donde solo una de las dos series
    # publicó dato.
    datos = pd.merge(petroleo, riesgo, on="fecha", how="outer").sort_values("fecha").reset_index(drop=True)

    antes = len(datos)
    datos = datos.drop_duplicates(subset=["fecha"])
    if len(datos) < antes:
        print(f"[petroleo_riesgo] Se eliminaron {antes - len(datos)} fechas duplicadas.")

    return datos


# ---------------------------------------------------------------------------
# 5. IEE - EXPECTATIVAS EMPRESARIALES
# ---------------------------------------------------------------------------
def limpiar_iee(ruta_iee: str) -> pd.DataFrame:
    """
    Fuente: IEE.xlsx, hoja 'IEE'.

    Estructura cruda observada:
    - 6 columnas sin nombre. Las primeras ~5 filas son NaN en todas las
      columnas (espacio visual del Excel antes de la tabla real).
    - La última fila es una nota de texto larga con la metodología del
      índice ("(1) Representa un punto de equilibrio...") que hay que
      descartar.
    - Las fechas vienen como texto 'AAAA-MM-DD' (confirmado: el reto ya
      anticipaba este formato).
    - NO se pudo confirmar visualmente en qué fila exacta está el
      encabezado de texto (Fecha/IEE Global/Comercio/Construcción/
      Manufactura/Servicios) porque no apareció en el head(5)/tail(5) de
      la exploración inicial. Para no adivinar el nombre de columna,
      esta función:
        1. Busca automáticamente la primera fila donde la columna 0 hace
           match con el patrón de fecha AAAA-MM-DD (esa es la primera
           fila de datos real, sin importar cuántas filas vacías haya
           antes).
        2. Asigna los nombres de columna de forma FIJA según el orden que
           describe el propio reto y la nota metodológica del archivo
           (Fecha, IEE_global, Comercio, Construccion, Manufactura,
           Servicios) — el reto solo pide las primeras 4 columnas de
           indicador (IEE_global, Comercio, Construccion, Manufactura),
           así que Servicios se conserva pero es opcional para tus vistas
           Gold.

    ⚠️ Verificación pendiente: antes de dar esto por bueno, abre
    IEE.xlsx en Excel y confirma visualmente que la fila justo antes del
    primer dato (columna 0 = una fecha) efectivamente dice
    Fecha/IEE Global/Comercio/Construcción/Manufactura/Servicios en ese
    orden. Si el orden real de las columnas es distinto, ajusta la lista
    `nombres_columnas` de esta función.
    """
    df = pd.read_excel(ruta_iee, sheet_name="IEE", header=None)

    patron_fecha = re.compile(r'^\d{4}-\d{2}-\d{2}$')

    def es_fecha(valor):
        if pd.isna(valor):
            return False
        return bool(patron_fecha.match(str(valor).strip()))

    mask = df[0].apply(es_fecha)
    datos = df[mask].copy()

    if datos.empty:
        raise ValueError(
            "No se encontraron filas con fecha 'AAAA-MM-DD' en la columna 0 de IEE. "
            "Revisa manualmente la estructura del archivo, puede haber cambiado."
        )

    nombres_columnas = ["fecha", "iee_global", "comercio", "construccion", "manufactura", "servicios"]
    datos.columns = nombres_columnas[:datos.shape[1]]

    datos["fecha"] = pd.to_datetime(datos["fecha"], format="%Y-%m-%d")
    for col in nombres_columnas[1:]:
        if col in datos.columns:
            datos[col] = pd.to_numeric(datos[col], errors="coerce")

    datos = datos.sort_values("fecha").reset_index(drop=True)

    antes = len(datos)
    datos = datos.drop_duplicates(subset=["fecha"])
    if len(datos) < antes:
        print(f"[iee] Se eliminaron {antes - len(datos)} fechas duplicadas.")

    return datos


# ---------------------------------------------------------------------------
# Prueba rápida manual (opcional, bórrala o coméntala si no la necesitas)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    CARPETA = "dataSets/bronze"

    print("=== PIB REAL ===")
    pib_real = limpiar_pib_real(f"{CARPETA}/retropolacion_1965_2023_PIB real.xlsx")
    print(pib_real.head())
    print(pib_real.tail())
    print(pib_real.dtypes, "\n")

    print("=== PIB NOMINAL ===")
    pib_nominal = limpiar_pib_nominal(f"{CARPETA}/PIB.xlsx")
    print(pib_nominal.head())
    print(pib_nominal.tail())
    print(pib_nominal.dtypes, "\n")

    print("=== VAB ===")
    vab = limpiar_vab(f"{CARPETA}/VAB 2018-2023.xlsx")
    print(vab.head())
    print(vab["anio"].unique())
    print(vab.dtypes, "\n")

    print("=== PETROLEO + RIESGO PAIS ===")
    pr = limpiar_petroleo_riesgo(f"{CARPETA}/PETRÓLEO.xlsx", f"{CARPETA}/RIESGO PAÍS.xlsx")
    print(pr.head())
    print(pr.tail())
    print(pr.dtypes, "\n")

    print("=== IEE ===")
    iee = limpiar_iee(f"{CARPETA}/IEE.xlsx")
    print(iee.head())
    print(iee.tail())
    print(iee.dtypes, "\n")

    