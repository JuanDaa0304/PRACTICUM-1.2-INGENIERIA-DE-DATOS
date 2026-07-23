import json
import re
import pandas as pd


def limpiar_supercias(ruta_sql: str):

    registros = []

    with open(ruta_sql, "r", encoding="utf-8", errors="ignore") as archivo:

        for linea in archivo:

            if "INSERT INTO `tabla_supercias`" not in linea:
                continue

            try:
                # 🔹 Buscar el JSON exacto (entre { ... } bien cerrado)
                match = re.search(r"\{.*?\}(?=',')", linea)

                if not match:
                    continue

                texto_json = match.group(0)

                # 🔹 Limpiar escapes
                texto_json = texto_json.replace('\\"', '"')

                # 🔹 Convertir a dict
                datos = json.loads(texto_json)

                registros.append(datos)

            except Exception as e:
                print("Error en JSON:", e)
                continue

    df = pd.DataFrame(registros)

    # ==========================
    # Conversión de tipos
    # ==========================

    columnas_numericas = [
        "ANIO",
        "ACTIVOS",
        "PATRIMONIO",
        "INGRESOS_VENTAS",
        "INGRESOS_TOTALES",
        "N_EMPLEADOS",
        "UTILIDAD_NETA",
        "UTILIDAD_EJERCICIO",
        "UTILIDAD_AN_IMP",
        "POSICION_GENERAL",
        "EXPEDIENTE"
    ]

    for columna in columnas_numericas:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")

    # ==========================
    # Limpieza básica
    # ==========================

    if "ANIO" in df.columns:
        df["ANIO"] = df["ANIO"].astype("Int64")

    if "CIIU_N1" in df.columns:
        df["CIIU_N1"] = df["CIIU_N1"].astype(str).str.strip()

    if "CIIU_N6" in df.columns:
        df["CIIU_N6"] = df["CIIU_N6"].astype(str).str.strip()

    df = df.drop_duplicates()

    return df


if __name__ == "__main__":

    supercias = limpiar_supercias(
        "dataSets/bronze/supercias.sql"
    )

    print("\n--- HEAD ---")
    print(supercias.head())

    print("\n--- INFO ---")
    print(supercias.info())

    print("\n--- NULOS ---")
    print(supercias.isna().sum())

    print("\nTotal registros:", len(supercias))