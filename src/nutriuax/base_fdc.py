"""Base completa USDA FDC SR Legacy (≈ 7.800 alimentos) y búsqueda en español (T13).

Nivel 2 de la base: no la usa el generador (que trabaja con el catálogo curado de `alimentos.csv`),
sino la edición manual y el calculador de encuestas. Se genera una vez desde el zip oficial:

    python -m nutriuax.importar_fdc RUTA/AL/zip      # escribe también data/fdc_completa.csv.gz

La búsqueda traduce las palabras españolas con `data/glosario_es_en.csv` (editable) y puntúa las
descripciones inglesas de FDC; las palabras sin traducción se buscan tal cual (sirve buscar en inglés).
"""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import zipfile
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .composicion import AMINOACIDOS, DATA_DIR, MACROS, MINERALES, PATRONES_AA

FICHERO = "fdc_completa.csv.gz"
GLOSARIO = "glosario_es_en.csv"

# número de nutriente SR → (columna, factor a la unidad interna: g→mg en minerales ya vienen en mg; AA g→mg)
NUM = {
    "208": ("kcal", 1), "203": ("proteina", 1), "204": ("grasa", 1), "606": ("agsat", 1),
    "205": ("hc", 1), "291": ("fibra", 1), "307": ("sodio", 1), "306": ("potasio", 1),
    "305": ("fosforo", 1), "301": ("calcio", 1),
    "501": ("trp", 1000), "502": ("thr", 1000), "503": ("ile", 1000), "504": ("leu", 1000),
    "505": ("lys", 1000), "506": ("met", 1000), "507": ("cys", 1000), "508": ("phe", 1000),
    "509": ("tyr", 1000), "510": ("val", 1000), "511": ("arg", 1000), "512": ("his", 1000),
    "513": ("ala", 1000), "514": ("asp", 1000), "515": ("glu", 1000), "516": ("gly", 1000),
    "517": ("pro", 1000), "518": ("ser", 1000),
}
AA_18 = ["leu", "ile", "val", "lys", "met", "cys", "phe", "tyr", "thr", "trp", "his", "arg", "ala",
         "asp", "glu", "gly", "pro", "ser"]
COLUMNAS = ["ndb", "fdc_id", "descripcion", "categoria", "origen", "patron_aa"] + MACROS + MINERALES + AA_18

# categoría SR → (origen de la proteína, patrón para estimar AA si faltan)
CATEGORIAS = {
    "Dairy and Egg Products": ("animal", "lacteo"), "Poultry Products": ("animal", "carne"),
    "Sausages and Luncheon Meats": ("animal", "carne"), "Pork Products": ("animal", "carne"),
    "Beef Products": ("animal", "carne"), "Lamb, Veal, and Game Products": ("animal", "carne"),
    "Finfish and Shellfish Products": ("animal", "pescado"), "Legumes and Legume Products": ("vegetal", "legumbre"),
    "Cereal Grains and Pasta": ("vegetal", "trigo"), "Baked Products": ("vegetal", "trigo"),
    "Breakfast Cereals": ("vegetal", "trigo"), "Nut and Seed Products": ("vegetal", "frutos_secos"),
    "Vegetables and Vegetable Products": ("vegetal", "verdura"), "Fruits and Fruit Juices": ("vegetal", "fruta"),
    "Fats and Oils": ("vegetal", "ninguno"), "Spices and Herbs": ("vegetal", "verdura"),
}


def _sin_tildes(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def _palabras(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _sin_tildes(s))


def _leer(z: zipfile.ZipFile, nombre: str, **kw) -> pd.DataFrame:
    cand = [n for n in z.namelist() if n.endswith("/" + nombre) or n == nombre]
    if not cand:
        raise FileNotFoundError(f"{nombre} no está en el zip")
    with z.open(cand[0]) as fh:
        return pd.read_csv(io.TextIOWrapper(fh, encoding="utf-8"), dtype=str, **kw)


def generar_completa(zip_path: Path, data_dir: Path = DATA_DIR) -> Path:
    """Escribe data/fdc_completa.csv.gz (por 100 g; minerales y AA en mg) y su .sha256. Devuelve la ruta."""
    z = zipfile.ZipFile(zip_path)
    food = _leer(z, "food.csv")
    food = food[[c for c in ("fdc_id", "description", "food_category_id") if c in food.columns]]
    sr = _leer(z, "sr_legacy_food.csv")[["fdc_id", "NDB_number"]]
    food = food.merge(sr, on="fdc_id")
    try:
        cat = _leer(z, "food_category.csv")[["id", "description"]].rename(
            columns={"id": "food_category_id", "description": "categoria"})
        food = food.merge(cat, on="food_category_id", how="left")
    except (FileNotFoundError, KeyError):
        food["categoria"] = ""
    nutrient = _leer(z, "nutrient.csv")[["id", "nutrient_nbr"]]
    nutrient["nbr"] = nutrient["nutrient_nbr"].str.replace(r"\.0$", "", regex=True)
    nutrient = nutrient[nutrient["nbr"].isin(NUM)]
    fn = _leer(z, "food_nutrient.csv", usecols=["fdc_id", "nutrient_id", "amount"])
    fn = fn[fn["nutrient_id"].isin(nutrient["id"])].merge(nutrient, left_on="nutrient_id", right_on="id")
    fn["col"] = fn["nbr"].map(lambda k: NUM[k][0])
    fn["valor"] = fn["amount"].astype(float) * fn["nbr"].map(lambda k: NUM[k][1])
    ancho = fn.pivot_table(index="fdc_id", columns="col", values="valor", aggfunc="first").reset_index()

    out = food.merge(ancho, on="fdc_id", how="left")
    out = out.rename(columns={"description": "descripcion", "NDB_number": "ndb"})
    out["ndb"] = out["ndb"].str.zfill(5)
    out["categoria"] = out["categoria"].fillna("")
    org = out["categoria"].map(lambda c_: CATEGORIAS.get(c_, ("vegetal", "verdura")))
    out["origen"] = org.map(lambda t: t[0])
    out["patron_aa"] = org.map(lambda t: t[1])
    for col in COLUMNAS:
        if col not in out.columns:
            out[col] = float("nan")
    out = out[COLUMNAS].sort_values("ndb").reset_index(drop=True)

    ruta = Path(data_dir) / FICHERO
    out.to_csv(ruta, index=False, compression={"method": "gzip", "mtime": 0})
    sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
    (Path(data_dir) / (FICHERO + ".sha256")).write_text(f"{sha}  {FICHERO}\n", encoding="utf-8")
    cargar_completa.cache_clear()
    return ruta


@lru_cache(maxsize=4)
def cargar_completa(data_dir: Path | None = None) -> pd.DataFrame | None:
    """La base completa, o None si aún no se ha generado."""
    ruta = Path(data_dir or DATA_DIR) / FICHERO
    if not ruta.exists():
        return None
    df = pd.read_csv(ruta, dtype={"ndb": str, "fdc_id": str})
    df["_palabras"] = df["descripcion"].map(lambda d: set(_palabras(d)))
    df["tiene_aa"] = df[["leu", "ile", "val"]].notna().all(axis=1)
    return df


@lru_cache(maxsize=4)
def cargar_glosario(data_dir: Path | None = None) -> dict[str, list[str]]:
    """español (sin tildes, en minúsculas; puede ser de varias palabras) → alternativas en inglés."""
    ruta = Path(data_dir or DATA_DIR) / GLOSARIO
    if not ruta.exists():
        return {}
    g = pd.read_csv(ruta, dtype=str).dropna()
    out: dict[str, list[str]] = {}
    for es, en in zip(g["es"], g["en"]):
        out.setdefault(" ".join(_sin_vacias(es)), []).extend(_palabras_en(en))
    return out


VACIAS = {"de", "del", "la", "el", "los", "las", "con", "y", "en", "al", "a"}


def _sin_vacias(s: str) -> list[str]:
    return [p for p in _palabras(s) if p not in VACIAS]


def _palabras_en(en: str) -> list[str]:
    # «chickpeas|garbanzo» → alternativas; cada alternativa puede tener varias palabras (se exigen todas)
    return [" ".join(_palabras(a)) for a in str(en).split("|") if a.strip()]


def traducir(texto: str, glosario: dict[str, list[str]]) -> list[list[str]]:
    """Divide la consulta en términos; cada término es una lista de alternativas inglesas.
    Prueba primero expresiones de 3 y 2 palabras del glosario («pechuga de pollo», «aceite de oliva»)."""
    pal = _sin_vacias(texto)
    terminos, i = [], 0
    while i < len(pal):
        for n in (3, 2, 1):
            clave = " ".join(pal[i:i + n])
            if n <= len(pal) - i and clave in glosario:
                terminos.append(glosario[clave])
                i += n
                break
        else:
            p = pal[i]
            singulares = [p[:-2], p[:-1]] if p.endswith("es") else [p[:-1]] if p.endswith("s") else []
            hallado = next((glosario[s] for s in singulares if len(s) > 2 and s in glosario), None)
            if hallado:
                terminos.append(hallado)
            else:
                terminos.append([p, p.rstrip("s")] if len(p) > 3 else [p])
            i += 1
    return terminos


# categorías de productos procesados, platos o marcas: se bajan en la búsqueda (siguen apareciendo)
CATEGORIAS_ABAJO = {"Sausages and Luncheon Meats", "Fast Foods", "Restaurant Foods", "Baby Foods",
                    "Meals, Entrees, and Side Dishes", "Branded Food Products Database", "Snacks",
                    "American Indian/Alaska Native Foods", "Quality Control Materials"}
ESTADO = {"raw", "cooked", "boiled", "roasted", "baked", "grilled", "broiled", "fried", "steamed", "stewed",
          "braised", "canned", "frozen"}
PROCESADO = {"breaded", "roll", "sliced", "patties", "nuggets", "frozen", "prepared", "mix", "fortified", "sprouted"}


def _encaja(alternativa: str, palabras: set[str]) -> bool:
    return all(any(w == t or w.startswith(t) for w in palabras) for t in alternativa.split())


def buscar(texto: str, n: int = 20, data_dir: Path | None = None, base: pd.DataFrame | None = None) -> pd.DataFrame:
    """Alimentos FDC que mejor encajan con `texto` (español o inglés), ordenados por puntuación.
    Puntúa la fracción de términos encontrados, premia que el primero aparezca al principio de la
    descripción, que tenga aminoácidos y que sea crudo o cocinado sin más; penaliza descripciones largas."""
    df = base if base is not None else cargar_completa(data_dir)
    if df is None or not str(texto).strip():
        return pd.DataFrame(columns=["ndb", "descripcion", "categoria", "tiene_aa", "puntuacion"])
    terminos = traducir(texto, cargar_glosario(data_dir))
    if not terminos:
        return pd.DataFrame(columns=["ndb", "descripcion", "categoria", "tiene_aa", "puntuacion"])
    if "_palabras" not in df.columns:
        df = df.assign(_palabras=df["descripcion"].map(lambda d: set(_palabras(d))))
    if "tiene_aa" not in df.columns:
        df = df.assign(tiene_aa=df[["leu", "ile", "val"]].notna().all(axis=1))

    pedidas = {w for alts in terminos for a in alts for w in a.split()}
    # los términos de estado («cocido», «crudo»…) no cuentan para el premio de cabecera
    terminos_alimento = [alts for alts in terminos if not all(set(a.split()) <= ESTADO for a in alts)]

    def puntuar(row) -> float:
        pw = row["_palabras"]
        hits = sum(any(_encaja(a, pw) for a in alts) for alts in terminos)
        if hits == 0:
            return 0.0
        s = hits / len(terminos)
        desc = re.sub(r"\(Includes foods for USDA.*?\)", "", row["descripcion"])
        cabeza = set(_palabras(",".join(desc.split(",")[:2])))  # «Fish, salmon…», «Chicken, broilers…»
        s += 0.3 * any(_encaja(a, cabeza) for alts in terminos_alimento for a in alts)
        s += 0.1 * bool(row["tiene_aa"])
        s += 0.05 * bool(pw & {"raw", "cooked", "boiled", "roasted"})
        s -= 0.004 * len(set(_palabras(desc)))
        s -= 0.15 * (row["categoria"] in CATEGORIAS_ABAJO)
        s -= 0.1 * bool((pw & PROCESADO) - pedidas)
        s -= 0.15 * bool(re.search(r"\b(?!USDA\b)[A-Z]{4,}\b", desc))  # marcas en mayúsculas
        return s

    sc = df.apply(puntuar, axis=1)
    res = df.assign(puntuacion=sc)[sc > 0].sort_values("puntuacion", ascending=False).head(n)
    return res[["ndb", "descripcion", "categoria", "tiene_aa", "puntuacion"]].reset_index(drop=True)


def fila_composicion(ndb: str, data_dir: Path | None = None, base: pd.DataFrame | None = None) -> pd.Series:
    """Fila lista para añadir a la tabla del motor (id `fdc_<ndb>`), con AA estimados por patrón si faltan."""
    df = base if base is not None else cargar_completa(data_dir)
    if df is None:
        raise FileNotFoundError("Falta data/fdc_completa.csv.gz: ejecuta python -m nutriuax.importar_fdc ZIP")
    r = df.loc[df["ndb"] == str(ndb).zfill(5)]
    if r.empty:
        raise KeyError(f"NDB {ndb} no está en la base FDC")
    r = r.iloc[0]
    f = {"nombre": f"{r['descripcion']} [FDC {r['ndb']}]", "grupo": "fdc", "rol": "fdc", "origen": r["origen"],
         "patron_aa": r["patron_aa"], "ndb": r["ndb"], "comidas_set": set(), "etiquetas_set": set()}
    for n in MACROS + MINERALES:
        f[n] = float(r[n]) if pd.notna(r[n]) else 0.0
    for a in AMINOACIDOS:
        est = pd.isna(r[a])
        f[a] = f["proteina"] * PATRONES_AA[r["patron_aa"]][a] * 10.0 if est else float(r[a])
        f[a + "_estimado"] = bool(est)
    return pd.Series(f, name=f"fdc_{r['ndb']}")
