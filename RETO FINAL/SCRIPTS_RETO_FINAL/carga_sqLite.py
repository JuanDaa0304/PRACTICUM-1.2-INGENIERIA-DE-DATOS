"""
load_to_sqlite.py
Semana 2 - Carga de las 5 tablas BCE limpias a SQLite
"""

import sqlite3
import pandas as pd
from Limpieza.limpieza_bce import (
    limpiar_pib_real,
    limpiar_pib_nominal,
    limpiar_vab,
    limpiar_petroleo_riesgo,
    limpiar_iee,
)
from Limpieza.limpieza_supercias import (
    limpiar_supercias,
)

from Limpieza.limpieza_mineduc import (
    limpiar_mineduc,
)

CARPETA_DATOS = "dataSets"
RUTA_BRONZE = f"{CARPETA_DATOS}/bronze"
RUTA_SILVER = f"{CARPETA_DATOS}/silver"
RUTA_BD = "macroentorno.db"


def main():
    print("Limpiando fuentes BCE...\n")

    # ===============================
    # LECTURA DESDE BRONZE
    # ===============================

    pib_real = limpiar_pib_real(f"{RUTA_BRONZE}/retropolacion_1965_2023_PIB real.xlsx")
    pib_nominal = limpiar_pib_nominal(f"{RUTA_BRONZE}/PIB.xlsx")
    vab = limpiar_vab(f"{RUTA_BRONZE}/VAB 2018-2023.xlsx")
    supercias = limpiar_supercias(f"{RUTA_BRONZE}/supercias.sql")

    petroleo_riesgo = limpiar_petroleo_riesgo(
        f"{RUTA_BRONZE}/PETRÓLEO.xlsx",
        f"{RUTA_BRONZE}/RIESGO PAÍS.xlsx"
    )

    iee = limpiar_iee(f"{RUTA_BRONZE}/IEE.xlsx")
    mineduc = limpiar_mineduc(f"{RUTA_BRONZE}/2_MINEDUC_RegistrosAdministrativos_2023-2024Inicio (1).csv")


    # ===============================
    # VALIDACIONES (solo algunas)
    # ===============================

    print("\n--- PIB REAL HEAD ---")
    print(pib_real.head())

    print("\n--- VAB HEAD ---")
    print(vab.head())

    print("\n--- PETROLEO HEAD ---")
    print(petroleo_riesgo.head())

    # ===============================
    # MODELO RELACIONAL
    # ===============================

    # 🔹 DIMENSIÓN TIEMPO
    # OJO: antes esto se armaba solo con los años de pib_real (1965-2023),
    # pero vab e iee ya traen años que pib_real no tiene (ej. 2024). Eso
    # dejaba filas de fact_vab/fact_iee con id_tiempo = NULL después del
    # merge (se verificó: 1,000 filas en fact_vab y 24 en fact_iee).
    # Se arma la dimensión con la UNIÓN de años de todas las fuentes
    # anuales para que ningún año se quede sin id_tiempo.
    anios_pib_real = set(pib_real["anio"].dropna().astype(int))
    anios_vab = set(vab["anio"].dropna().astype(int))
    anios_iee = set(iee["fecha"].dropna().dt.year.astype(int))
    todos_los_anios = sorted(anios_pib_real | anios_vab | anios_iee)

    dim_tiempo = pd.DataFrame({"anio": todos_los_anios})
    dim_tiempo["fecha"] = pd.to_datetime(dim_tiempo["anio"].astype(str) + "-01-01")
    dim_tiempo["mes"] = 1
    dim_tiempo["trimestre"] = 1

    dim_tiempo = dim_tiempo.reset_index(drop=True)
    dim_tiempo["id_tiempo"] = dim_tiempo.index + 1

    anios_faltantes_antes = (anios_vab | anios_iee) - anios_pib_real
    if anios_faltantes_antes:
        print(f"[dim_tiempo] Años agregados que no estaban en pib_real: {sorted(anios_faltantes_antes)}")

    # 🔹 FACT MACRO
    fact_macro = pib_real.merge(
        dim_tiempo[["id_tiempo", "anio"]],
        on="anio",
        how="left"
    ).drop(columns=["anio"])

    # 🔹 DIMENSIÓN GEOGRAFÍA
    dim_geografia = vab[
        ["provincia", "cod_provincia", "canton", "cod_canton"]
    ].copy()

    # eliminar registros repetidos
    dim_geografia = dim_geografia.drop_duplicates()

    # crear ID
    dim_geografia = dim_geografia.reset_index(drop=True)
    dim_geografia["id_geo"] = dim_geografia.index + 1

    # ordenar columnas
    dim_geografia = dim_geografia[
        [
            "id_geo",
            "provincia",
            "cod_provincia",
            "canton",
            "cod_canton"
        ]
    ]

    print("\n--- DIM GEOGRAFIA ---")
    print(dim_geografia.head())

    # 🔹 FACT INDICADORES DIARIOS
    fact_indicadores_diarios = petroleo_riesgo.copy()

    # crear ID
    fact_indicadores_diarios = fact_indicadores_diarios.reset_index(drop=True)
    fact_indicadores_diarios["id"] = fact_indicadores_diarios.index + 1

    # ordenar columnas
    fact_indicadores_diarios = fact_indicadores_diarios[
        [
            "id",
            "fecha",
            "precio_petroleo_wti",
            "riesgo_pais_pb"
        ]
    ]

    print("\n--- FACT INDICADORES DIARIOS ---")
    print(fact_indicadores_diarios.head())

    # 🔹 FACT VAB

    fact_vab = vab.merge(
        dim_geografia[
            ["id_geo", "cod_provincia", "cod_canton"]
        ],
        on=["cod_provincia", "cod_canton"],
        how="left"
    )

    fact_vab = fact_vab.merge(
        dim_tiempo[
            ["id_tiempo", "anio"]
        ],
        on="anio",
        how="left"
    )

    # eliminar columnas que ya están representadas por las dimensiones
    fact_vab = fact_vab.drop(
        columns=[
            "anio",
            "provincia",
            "cod_provincia",
            "canton",
            "cod_canton"
        ]
    )

    # crear ID
    fact_vab = fact_vab.reset_index(drop=True)
    fact_vab["id"] = fact_vab.index + 1

    # ordenar columnas
    # es_total viene de limpiar_vab(): True en la fila "ECONOMÍA TOTAL"
    # (subtotal de los otros 14 sectores). Se conserva la columna para que
    # el dashboard pueda:
    #   - WHERE es_total = 0  -> sumar vab_usd por sector sin duplicar
    #   - WHERE es_total = 1  -> usar directo el total anual ya calculado
    fact_vab = fact_vab[
        [
            "id",
            "id_tiempo",
            "id_geo",
            "sector",
            "vab_usd",
            "es_total"
        ]
    ]

    n_null_tiempo = fact_vab["id_tiempo"].isna().sum()
    if n_null_tiempo:
        print(f"[fact_vab] Aviso: {n_null_tiempo} filas sin id_tiempo (año no encontrado en dim_tiempo).")

    print("\n--- FACT VAB ---")
    print(fact_vab.head())
    print(f"[fact_vab] {fact_vab['es_total'].sum()} filas son subtotal 'ECONOMÍA TOTAL' "
          f"(es_total=True) -- excluir con WHERE es_total = 0 al sumar por sector.")

    # ===============================
    # 🔹 FACT IEE
    # ===============================

    fact_iee = iee.copy()

    # obtener año desde la fecha
    fact_iee["anio"] = fact_iee["fecha"].dt.year

    # relacionar con la dimensión tiempo
    fact_iee = fact_iee.merge(
        dim_tiempo[["id_tiempo", "anio"]],
        on="anio",
        how="left"
    )

    # eliminar año auxiliar
    fact_iee = fact_iee.drop(columns=["anio"])

    # crear ID
    fact_iee = fact_iee.reset_index(drop=True)
    fact_iee["id"] = fact_iee.index + 1

    # ordenar columnas
    fact_iee = fact_iee[
        [
            "id",
            "id_tiempo",
            "fecha",
            "iee_global",
            "comercio",
            "construccion",
            "manufactura",
            "servicios"
        ]
    ]

    print("\n--- FACT IEE ---")
    print(fact_iee.head())

    # ===============================
    # 🔹 FACT MINEDUC
    # ===============================

    fact_mineduc = mineduc.merge(
        dim_geografia[
            ["id_geo", "provincia", "canton"]
        ],
        on=["provincia", "canton"],
        how="left"
    )

    # eliminar columnas reemplazadas por la dimensión
    fact_mineduc = fact_mineduc.drop(
        columns=[
            "provincia",
            "canton"
        ]
    )

    # crear ID
    fact_mineduc = fact_mineduc.reset_index(drop=True)
    fact_mineduc["id"] = fact_mineduc.index + 1

    # ordenar columnas
    fact_mineduc = fact_mineduc[
        [
            "id",
            "id_geo",
            "ano_lectivo",
            "parroquia",
            "tipo_educacion",
            "nivel_educacion",
            "sostenimiento",
            "area",
            "regimen_escolar",
            "total_docentes",
            "total_estudiantes"
        ]
    ]

    print("\n--- FACT MINEDUC ---")
    print(fact_mineduc.head())

    
    # ===============================
    #  GUARDAR CSVs (SILVER)
    # ===============================

    pib_real.to_csv(f"{RUTA_SILVER}/silver_pib_real.csv", index=False)
    pib_nominal.to_csv(f"{RUTA_SILVER}/silver_pib_nominal.csv", index=False)
    vab.to_csv(f"{RUTA_SILVER}/silver_vab.csv", index=False)
    petroleo_riesgo.to_csv(f"{RUTA_SILVER}/silver_petroleo_riesgo.csv", index=False)
    iee.to_csv(f"{RUTA_SILVER}/silver_iee.csv", index=False)
    mineduc.to_csv(f"{RUTA_SILVER}/silver_mineduc.csv", index=False)
    supercias.to_csv(f"{RUTA_SILVER}/silver_supercias.csv", index=False)

    print("\n📁 CSVs silver guardados correctamente")

    # ===============================
    #  CARGA SQLITE
    # ===============================

    conn = sqlite3.connect(RUTA_BD)

    pib_real.to_sql("bce_pib_real", conn, if_exists="replace", index=False)
    pib_nominal.to_sql("bce_pib_nominal", conn, if_exists="replace", index=False)
    vab.to_sql("bce_vab", conn, if_exists="replace", index=False)
    petroleo_riesgo.to_sql("bce_petroleo_riesgo", conn, if_exists="replace", index=False)
    iee.to_sql("bce_iee", conn, if_exists="replace", index=False)
    mineduc.to_sql("mineduc", conn, if_exists="replace", index=False)

    # Modelo relacional 
    dim_tiempo.to_sql("dim_tiempo", conn, if_exists="replace", index=False)
    fact_macro.to_sql("fact_macro_anual", conn, if_exists="replace", index=False)
    fact_indicadores_diarios.to_sql("fact_indicadores_diarios", conn,  if_exists="replace", index=False)
    fact_vab.to_sql("fact_vab", conn, if_exists="replace", index=False)
    dim_geografia.to_sql("dim_geografia", conn, if_exists="replace", index=False)
    fact_iee.to_sql("fact_iee", conn, if_exists="replace", index=False)
    fact_mineduc.to_sql("fact_mineduc", conn, if_exists="replace", index=False)
    supercias.to_sql("fact_supercias", conn, if_exists="replace", index=False)

    conn.close()

    print("\nFilas limpias por tabla:")
    print(f"  pib_real:         {len(pib_real)}")
    print(f"  pib_nominal:      {len(pib_nominal)}")
    print(f"  vab:              {len(vab)}")
    print(f"  petroleo_riesgo:  {len(petroleo_riesgo)}")
    print(f"  iee:              {len(iee)}")
    print(f"  mineduc:          {len(mineduc)}")
    print(f"  supercias:        {len(supercias)}")


    print(f"\n Todo cargado correctamente en {RUTA_BD}")


if __name__ == "__main__":
    main()