# ---------------------------------------------------------------------------
# 6. MINEDUC - REGISTROS ADMINISTRATIVOS
# ---------------------------------------------------------------------------

import pandas as pd

def limpiar_mineduc(ruta_csv: str):

    df = pd.read_csv(ruta_csv, sep=";", encoding="latin1")

    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("á", "a")
        .str.replace("é", "e")
        .str.replace("í", "i")
        .str.replace("ó", "o")
        .str.replace("ú", "u")
        .str.replace("ñ", "n")
    )

    columnas = [
        "ano_lectivo",
        "provincia",
        "canton",
        "parroquia",
        "tipo_educacion",
        "nivel_educacion",
        "sostenimiento",
        "area",
        "regimen_escolar",
        "total_docentes",
        "total_estudiantes"
    ]

    df = df[columnas].copy()

    df["total_docentes"] = pd.to_numeric(df["total_docentes"], errors="coerce")
    df["total_estudiantes"] = pd.to_numeric(df["total_estudiantes"], errors="coerce")

    df = df.dropna(subset=["provincia", "canton"])
    df["provincia"] = df["provincia"].str.strip().str.upper()
    df["canton"] = df["canton"].str.strip().str.upper()

    return df

if __name__ == "__main__":
    CARPETA = "dataSets/bronze"

    print("=== MINEDUC ===")
    mineduc = limpiar_mineduc(f"{CARPETA}/2_MINEDUC_RegistrosAdministrativos_2023-2024Inicio (1).csv")
    print(mineduc.head())
    print(mineduc.tail())
    print(mineduc.dtypes, "\n")