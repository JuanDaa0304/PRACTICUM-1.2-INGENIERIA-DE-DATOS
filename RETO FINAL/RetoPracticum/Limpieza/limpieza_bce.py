"""
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

    