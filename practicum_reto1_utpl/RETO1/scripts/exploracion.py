import pandas as pd
import unicodedata

ruta = r"data\2_MINEDUC_RegistrosAdministrativos_2023-2024-Fin-1.csv"

# === FUNCION PARA LIMPIAR NOMBRES ===
def limpiar(texto):
    texto = str(texto).strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace(" ", "_").lower()
    return texto

# === LEER CSV ===
df = pd.read_csv(
    ruta,
    sep=";",
    encoding="utf-8-sig",
    header=10,
    low_memory=False
)

# === LIMPIAR COLUMNAS ===
df.columns = [limpiar(col) for col in df.columns]

print("\nCOLUMNAS LIMPIAS:")
print(df.columns.tolist())

print("\nDIMENSIONES:")
print(df.shape)

# === BUSCAR COLUMNAS IMPORTANTES ===
col_sostenimiento = None
col_nivel = None
col_total = None

for col in df.columns:
    if "sostenimiento" in col:
        col_sostenimiento = col
    if "nivel_educacion" in col:
        col_nivel = col
    if "total_estudiantes" in col:
        col_total = col

print("\nCOLUMNAS ENCONTRADAS:")
print("Sostenimiento:", col_sostenimiento)
print("Nivel:", col_nivel)
print("Total estudiantes:", col_total)

# === RESULTADOS ===
if col_sostenimiento:
    print("\nSOSTENIMIENTO:")
    print(df[col_sostenimiento].value_counts())

if col_nivel:
    print("\nNIVEL EDUCACION:")
    print(df[col_nivel].value_counts())

if col_total:
    print("\nTOTAL ESTUDIANTES:")
    print(df[col_total].describe())