"""
flow_macroentorno.py
Pipeline de datos del Tablero Macroentorno Ecuatoriano, orquestado con Prefect.

Reemplaza la ejecución manual de carga_sqLite.py por un flujo con tareas
independientes, reintentos automáticos y logging. Reutiliza las mismas
funciones de limpieza que ya tenías en Limpieza/.

Coloca este archivo en la raíz de tu proyecto (mismo nivel que carga_sqLite.py),
para que los imports de "Limpieza.*" funcionen igual que antes.
"""

import sqlite3
import pandas as pd
from prefect import flow, task, get_run_logger

from Limpieza.limpieza_bce import (
    limpiar_pib_real,
    limpiar_pib_nominal,
    limpiar_vab,
    limpiar_petroleo_riesgo,
    limpiar_iee,
)
from Limpieza.limpieza_supercias import limpiar_supercias
from Limpieza.limpieza_mineduc import limpiar_mineduc

CARPETA_DATOS = "dataSets"
RUTA_BRONZE = f"{CARPETA_DATOS}/bronze"
RUTA_SILVER = f"{CARPETA_DATOS}/silver"
RUTA_BD = "macroentorno.db"


# ============================================================
# TAREAS DE LIMPIEZA (bronze -> dataframe limpio)
# Cada una es independiente de las demás, por eso se pueden
# correr en paralelo con .submit() en el flujo principal.
# ============================================================

@task(name="limpiar_pib_real", retries=2, retry_delay_seconds=10)
def t_limpiar_pib_real():
    logger = get_run_logger()
    df = limpiar_pib_real(f"{RUTA_BRONZE}/retropolacion_1965_2023_PIB real.xlsx")
    logger.info(f"PIB real limpio: {len(df)} filas")
    return df


@task(name="limpiar_pib_nominal", retries=2, retry_delay_seconds=10)
def t_limpiar_pib_nominal():
    logger = get_run_logger()
    df = limpiar_pib_nominal(f"{RUTA_BRONZE}/PIB.xlsx")
    logger.info(f"PIB nominal limpio: {len(df)} filas")
    return df


@task(name="limpiar_vab", retries=2, retry_delay_seconds=10)
def t_limpiar_vab():
    logger = get_run_logger()
    df = limpiar_vab(f"{RUTA_BRONZE}/VAB 2018-2023.xlsx")
    logger.info(f"VAB limpio: {len(df)} filas")
    return df


@task(name="limpiar_petroleo_riesgo", retries=2, retry_delay_seconds=10)
def t_limpiar_petroleo_riesgo():
    logger = get_run_logger()
    df = limpiar_petroleo_riesgo(
        f"{RUTA_BRONZE}/PETRÓLEO.xlsx",
        f"{RUTA_BRONZE}/RIESGO PAÍS.xlsx",
    )
    logger.info(f"Petróleo/riesgo país limpio: {len(df)} filas")
    return df


@task(name="limpiar_iee", retries=2, retry_delay_seconds=10)
def t_limpiar_iee():
    logger = get_run_logger()
    df = limpiar_iee(f"{RUTA_BRONZE}/IEE.xlsx")
    logger.info(f"IEE limpio: {len(df)} filas")
    return df


@task(name="limpiar_supercias", retries=1, retry_delay_seconds=30, timeout_seconds=1800)
def t_limpiar_supercias():
    # supercias.sql pesa ~2.7 GB, por eso timeout largo y solo 1 reintento
    logger = get_run_logger()
    df = limpiar_supercias(f"{RUTA_BRONZE}/supercias.sql")
    logger.info(f"Supercias limpio: {len(df)} filas")
    return df


@task(name="limpiar_mineduc", retries=2, retry_delay_seconds=10)
def t_limpiar_mineduc():
    logger = get_run_logger()
    df = limpiar_mineduc(
        f"{RUTA_BRONZE}/2_MINEDUC_RegistrosAdministrativos_2023-2024Inicio (1).csv"
    )
    logger.info(f"MINEDUC limpio: {len(df)} filas")
    return df


# ============================================================
# TAREA: MODELO DIMENSIONAL (silver -> esquema estrella)
# Depende de varias limpiezas, por eso se ejecuta después.
# ============================================================

@task(name="construir_modelo_dimensional")
def construir_modelo(pib_real, vab, petroleo_riesgo, iee, mineduc):
    logger = get_run_logger()

    # DIM TIEMPO
    dim_tiempo = pib_real[["anio"]].copy()
    dim_tiempo["fecha"] = pd.to_datetime(dim_tiempo["anio"].astype(str) + "-01-01")
    dim_tiempo["mes"] = 1
    dim_tiempo["trimestre"] = 1
    dim_tiempo = dim_tiempo.reset_index(drop=True)
    dim_tiempo["id_tiempo"] = dim_tiempo.index + 1

    # FACT MACRO
    fact_macro = pib_real.merge(
        dim_tiempo[["id_tiempo", "anio"]], on="anio", how="left"
    ).drop(columns=["anio"])

    # DIM GEOGRAFIA
    dim_geografia = (
        vab[["provincia", "cod_provincia", "canton", "cod_canton"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    dim_geografia["id_geo"] = dim_geografia.index + 1
    dim_geografia = dim_geografia[
        ["id_geo", "provincia", "cod_provincia", "canton", "cod_canton"]
    ]

    # FACT INDICADORES DIARIOS
    fact_indicadores_diarios = petroleo_riesgo.copy().reset_index(drop=True)
    fact_indicadores_diarios["id"] = fact_indicadores_diarios.index + 1
    fact_indicadores_diarios = fact_indicadores_diarios[
        ["id", "fecha", "precio_petroleo_wti", "riesgo_pais_pb"]
    ]

    # FACT VAB
    fact_vab = vab.merge(
        dim_geografia[["id_geo", "cod_provincia", "cod_canton"]],
        on=["cod_provincia", "cod_canton"],
        how="left",
    )
    fact_vab = fact_vab.merge(
        dim_tiempo[["id_tiempo", "anio"]], on="anio", how="left"
    )
    fact_vab = fact_vab.drop(
        columns=["anio", "provincia", "cod_provincia", "canton", "cod_canton"]
    )
    fact_vab = fact_vab.reset_index(drop=True)
    fact_vab["id"] = fact_vab.index + 1
    fact_vab = fact_vab[["id", "id_tiempo", "id_geo", "sector", "vab_usd"]]

    # FACT IEE
    fact_iee = iee.copy()
    fact_iee["anio"] = fact_iee["fecha"].dt.year
    fact_iee = fact_iee.merge(
        dim_tiempo[["id_tiempo", "anio"]], on="anio", how="left"
    ).drop(columns=["anio"])
    fact_iee = fact_iee.reset_index(drop=True)
    fact_iee["id"] = fact_iee.index + 1
    fact_iee = fact_iee[
        ["id", "id_tiempo", "fecha", "iee_global", "comercio", "construccion", "manufactura", "servicios"]
    ]

    # FACT MINEDUC
    fact_mineduc = mineduc.merge(
        dim_geografia[["id_geo", "provincia", "canton"]],
        on=["provincia", "canton"],
        how="left",
    )
    fact_mineduc = fact_mineduc.drop(columns=["provincia", "canton"])
    fact_mineduc = fact_mineduc.reset_index(drop=True)
    fact_mineduc["id"] = fact_mineduc.index + 1
    fact_mineduc = fact_mineduc[
        [
            "id", "id_geo", "ano_lectivo", "parroquia", "tipo_educacion",
            "nivel_educacion", "sostenimiento", "area", "regimen_escolar",
            "total_docentes", "total_estudiantes",
        ]
    ]

    logger.info(
        "Modelo dimensional construido: dim_tiempo, dim_geografia, "
        "fact_macro, fact_vab, fact_iee, fact_mineduc, fact_indicadores_diarios"
    )

    return {
        "dim_tiempo": dim_tiempo,
        "dim_geografia": dim_geografia,
        "fact_macro": fact_macro,
        "fact_indicadores_diarios": fact_indicadores_diarios,
        "fact_vab": fact_vab,
        "fact_iee": fact_iee,
        "fact_mineduc": fact_mineduc,
    }


# ============================================================
# TAREA: GUARDAR SILVER (CSV)
# ============================================================

@task(name="guardar_silver")
def guardar_silver(pib_real, pib_nominal, vab, petroleo_riesgo, iee, mineduc, supercias):
    logger = get_run_logger()
    pib_real.to_csv(f"{RUTA_SILVER}/silver_pib_real.csv", index=False)
    pib_nominal.to_csv(f"{RUTA_SILVER}/silver_pib_nominal.csv", index=False)
    vab.to_csv(f"{RUTA_SILVER}/silver_vab.csv", index=False)
    petroleo_riesgo.to_csv(f"{RUTA_SILVER}/silver_petroleo_riesgo.csv", index=False)
    iee.to_csv(f"{RUTA_SILVER}/silver_iee.csv", index=False)
    mineduc.to_csv(f"{RUTA_SILVER}/silver_mineduc.csv", index=False)
    supercias.to_csv(f"{RUTA_SILVER}/silver_supercias.csv", index=False)
    logger.info(f"7 CSVs silver guardados en {RUTA_SILVER}/")


# ============================================================
# TAREA: CARGAR SQLITE
# ============================================================

@task(name="cargar_sqlite")
def cargar_sqlite(pib_real, pib_nominal, vab, petroleo_riesgo, iee, mineduc, supercias, modelo):
    logger = get_run_logger()
    conn = sqlite3.connect(RUTA_BD)

    pib_real.to_sql("bce_pib_real", conn, if_exists="replace", index=False)
    pib_nominal.to_sql("bce_pib_nominal", conn, if_exists="replace", index=False)
    vab.to_sql("bce_vab", conn, if_exists="replace", index=False)
    petroleo_riesgo.to_sql("bce_petroleo_riesgo", conn, if_exists="replace", index=False)
    iee.to_sql("bce_iee", conn, if_exists="replace", index=False)
    mineduc.to_sql("mineduc", conn, if_exists="replace", index=False)

    modelo["dim_tiempo"].to_sql("dim_tiempo", conn, if_exists="replace", index=False)
    modelo["fact_macro"].to_sql("fact_macro_anual", conn, if_exists="replace", index=False)
    modelo["fact_indicadores_diarios"].to_sql(
        "fact_indicadores_diarios", conn, if_exists="replace", index=False
    )
    modelo["fact_vab"].to_sql("fact_vab", conn, if_exists="replace", index=False)
    modelo["dim_geografia"].to_sql("dim_geografia", conn, if_exists="replace", index=False)
    modelo["fact_iee"].to_sql("fact_iee", conn, if_exists="replace", index=False)
    modelo["fact_mineduc"].to_sql("fact_mineduc", conn, if_exists="replace", index=False)
    supercias.to_sql("fact_supercias", conn, if_exists="replace", index=False)

    conn.close()
    logger.info(f"Todo cargado correctamente en {RUTA_BD}")


# ============================================================
# FLUJO PRINCIPAL
# ============================================================

@flow(name="pipeline-macroentorno-ecuatoriano", log_prints=True)
def pipeline_macroentorno():
    logger = get_run_logger()
    logger.info("Iniciando pipeline de datos del Tablero Macroentorno Ecuatoriano")

    # Las 7 limpiezas son independientes entre sí -> se lanzan en paralelo
    f_pib_real = t_limpiar_pib_real.submit()
    f_pib_nominal = t_limpiar_pib_nominal.submit()
    f_vab = t_limpiar_vab.submit()
    f_petroleo_riesgo = t_limpiar_petroleo_riesgo.submit()
    f_iee = t_limpiar_iee.submit()
    f_supercias = t_limpiar_supercias.submit()
    f_mineduc = t_limpiar_mineduc.submit()

    # .result() espera a que cada tarea termine y trae el dataframe
    pib_real = f_pib_real.result()
    pib_nominal = f_pib_nominal.result()
    vab = f_vab.result()
    petroleo_riesgo = f_petroleo_riesgo.result()
    iee = f_iee.result()
    supercias = f_supercias.result()
    mineduc = f_mineduc.result()

    # El modelo dimensional depende de varias limpiezas anteriores
    modelo = construir_modelo(pib_real, vab, petroleo_riesgo, iee, mineduc)

    # Guardar CSV y cargar SQLite pueden correr en paralelo entre sí
    guardar_silver.submit(pib_real, pib_nominal, vab, petroleo_riesgo, iee, mineduc, supercias)
    cargar_sqlite(pib_real, pib_nominal, vab, petroleo_riesgo, iee, mineduc, supercias, modelo)

    logger.info("Pipeline finalizado correctamente")


if __name__ == "__main__":
    pipeline_macroentorno()
