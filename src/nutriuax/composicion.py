"""Tabla de composición de alimentos (por 100 g de porción comestible).

Fuente de verdad (ADR-0001): USDA FoodData Central SR Legacy (CC0), importada con
`python -m nutriuax.importar_fdc`. Mientras no exista `data/composicion_fdc.csv`, se usa la
tabla semilla de `data/alimentos.csv`, cuyos aminoácidos se ESTIMAN como proteína × patrón
aminoacídico del grupo (PATRONES_AA). La semilla sirve para desarrollar y probar, nunca para
resultados de un estudio: `Composicion.fuente` lo deja dicho y la app lo muestra.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

MACROS = ["kcal", "proteina", "grasa", "agsat", "hc", "fibra"]
MINERALES = ["sodio", "potasio", "fosforo", "calcio"]  # mg/100 g
AMINOACIDOS = ["leu", "ile", "val", "lys", "met", "phe", "thr", "trp", "his"]  # mg/100 g
NUTRIENTES = MACROS + MINERALES + AMINOACIDOS

UNIDADES = {
    "kcal": "kcal", "proteina": "g", "grasa": "g", "agsat": "g", "hc": "g", "fibra": "g",
    **{m: "mg" for m in MINERALES}, **{a: "mg" for a in AMINOACIDOS},
}

# g de aminoácido por 100 g de proteína. Valores redondeados de orden de magnitud típico por
# grupo; SOLO para la semilla (se sustituyen por los analíticos de FDC al importar).
PATRONES_AA: dict[str, dict[str, float]] = {
    "lacteo":       dict(leu=9.8, ile=5.4, val=6.6, lys=8.0, met=2.6, phe=4.9, thr=4.5, trp=1.4, his=2.8),
    "suero":        dict(leu=11.0, ile=6.2, val=5.8, lys=9.5, met=2.1, phe=3.2, thr=6.8, trp=1.7, his=1.8),
    "huevo":        dict(leu=8.6, ile=5.3, val=6.8, lys=7.3, met=3.0, phe=5.4, thr=4.4, trp=1.3, his=2.5),
    "carne":        dict(leu=8.0, ile=4.6, val=5.0, lys=8.6, met=2.6, phe=4.0, thr=4.2, trp=1.2, his=3.5),
    "pescado":      dict(leu=8.1, ile=4.6, val=5.2, lys=9.2, met=3.0, phe=3.9, thr=4.4, trp=1.1, his=2.9),
    "legumbre":     dict(leu=7.8, ile=4.4, val=5.1, lys=6.6, met=1.2, phe=5.3, thr=3.8, trp=1.1, his=2.7),
    "soja":         dict(leu=7.8, ile=4.6, val=4.8, lys=6.3, met=1.3, phe=5.0, thr=4.0, trp=1.3, his=2.6),
    "trigo":        dict(leu=6.8, ile=3.6, val=4.3, lys=2.6, met=1.7, phe=4.8, thr=2.8, trp=1.2, his=2.3),
    "arroz":        dict(leu=8.2, ile=4.3, val=6.0, lys=3.6, met=2.4, phe=5.3, thr=3.6, trp=1.2, his=2.4),
    "avena":        dict(leu=7.5, ile=4.0, val=5.4, lys=4.2, met=1.9, phe=5.3, thr=3.4, trp=1.4, his=2.4),
    "patata":       dict(leu=5.6, ile=3.9, val=5.2, lys=5.5, met=1.6, phe=4.3, thr=3.6, trp=1.2, his=2.1),
    "frutos_secos": dict(leu=6.9, ile=3.6, val=4.5, lys=3.0, met=1.0, phe=5.2, thr=3.0, trp=1.0, his=2.6),
    "verdura":      dict(leu=5.5, ile=3.8, val=4.8, lys=5.0, met=1.4, phe=3.8, thr=3.6, trp=1.1, his=2.0),
    "fruta":        dict(leu=4.5, ile=3.0, val=3.8, lys=4.2, met=1.0, phe=2.8, thr=2.8, trp=1.0, his=1.8),
    "ninguno":      {a: 0.0 for a in AMINOACIDOS},
}

ROLES = ["lacteo", "cereal", "proteina", "legumbre", "verdura", "fruta", "grasa",
         "frutos_secos", "suplemento", "dulce"]


@dataclass
class Composicion:
    tabla: pd.DataFrame  # índice = id; columnas de metadatos + NUTRIENTES por 100 g
    fuente: str          # "semilla" | "fdc"

    def nutr(self, id_: str, n: str) -> float:
        return float(self.tabla.at[id_, n])

    def etiquetas(self, id_: str) -> set[str]:
        return self.tabla.at[id_, "etiquetas_set"]

    def anadir(self, filas: list[pd.Series]) -> "Composicion":
        """Nueva Composicion con filas extra (p. ej. alimentos de la base FDC completa, id `fdc_<ndb>`).
        Las filas ya presentes se ignoran; el catálogo del generador no cambia de contenido."""
        nuevas = [f for f in filas if f.name not in self.tabla.index]
        if not nuevas:
            return self
        return Composicion(pd.concat([self.tabla, pd.DataFrame(nuevas)]), self.fuente)

    def calcular(self, items: pd.DataFrame) -> pd.DataFrame:
        """items: columnas `id` y `gramos` (+ las que sean). Devuelve items con nutrientes aportados."""
        out = items.copy()
        fac = out["gramos"].astype(float).to_numpy() / 100.0
        sub = self.tabla.loc[out["id"], NUTRIENTES].to_numpy()
        for j, n in enumerate(NUTRIENTES):
            out[n] = sub[:, j] * fac
        out["proteina_animal"] = out["proteina"].where(
            self.tabla.loc[out["id"], "origen"].to_numpy() == "animal", 0.0)
        out["proteina_vegetal"] = out["proteina"] - out["proteina_animal"]
        return out


def _estimar_aa(df: pd.DataFrame) -> pd.DataFrame:
    for a in AMINOACIDOS:
        if a not in df.columns:
            df[a] = float("nan")
        est = df.apply(lambda r: r["proteina"] * PATRONES_AA[r["patron_aa"]][a] * 10.0, axis=1)  # mg/100 g
        df[a + "_estimado"] = df[a].isna()
        df[a] = df[a].fillna(est)
    return df


def alergenos_derivados(id_: str, r) -> set[str]:
    """Alérgenos UE-14 de un alimento del catálogo deducidos de su grupo, patrón y etiquetas (T23). Si el CSV trae
    la columna `alergenos`, manda esa. Conservador: ante la duda, se marca."""
    a: set[str] = set()
    grupo, patron = str(r.get("grupo", "")), str(r.get("patron_aa", ""))
    et = set(str(r.get("etiquetas", "") or "").split(";"))
    if (grupo == "lacteos" or patron == "lacteo" or "lacteo" in et) and patron != "soja":
        a.add("leche")
    if grupo == "huevos" or patron == "huevo":
        a.add("huevo")
    if grupo == "pescados":
        if any(k in id_ for k in ("gamba", "langostino", "cangrejo", "surimi")):
            a.add("crustaceos")
        if any(k in id_ for k in ("mejillon", "almeja", "calamar", "pulpo", "sepia")):
            a.add("moluscos")
        if not a or "surimi" in id_:
            a.add("pescado")
    if patron in ("trigo", "avena") and grupo in ("cereales", "azucares", "tuberculos"):
        a.add("gluten")
    if grupo == "frutos_secos":
        if "cacahuete" in id_:
            a.add("cacahuete")
        elif "sesamo" in id_:
            a.add("sesamo")
        elif not any(k in id_ for k in ("pipas", "chia", "lino")):
            a.add("frutos_cascara")
    if "soja" in et or patron == "soja":
        a.add("soja")
    return a


def cargar(data_dir: Path | None = None) -> Composicion:
    d = Path(data_dir) if data_dir else DATA_DIR
    base = pd.read_csv(d / "alimentos.csv", dtype={"ndb": str}).set_index("id")
    fuente = "semilla"
    fdc_path = d / "composicion_fdc.csv"
    if fdc_path.exists():
        fdc = pd.read_csv(fdc_path).set_index("id")
        cols = [c for c in NUTRIENTES if c in fdc.columns]
        comunes = base.index.intersection(fdc.index)
        for c in cols:
            if c not in base.columns:
                base[c] = float("nan")
            base.loc[comunes, c] = fdc.loc[comunes, c].combine_first(base.loc[comunes, c])
        fuente = "fdc" if len(comunes) == len(base) else "mixta"
    base = _estimar_aa(base)
    base["comidas_set"] = base["comidas"].fillna("").map(lambda s: set(s.split(";")) - {""})
    base["etiquetas_set"] = base["etiquetas"].fillna("").map(lambda s: set(s.split(";")) - {""})
    # etiqueta derivada «carne» = roja ∪ blanca (AESAN 2022 cuenta la carne total; ADR-0004)
    base["etiquetas_set"] = base["etiquetas_set"].map(lambda e: e | {"carne"} if e & {"carne_roja", "carne_blanca"} else e)
    if "alergenos" in base.columns:
        base["alergenos_set"] = base["alergenos"].fillna("").map(lambda s: set(s.split(";")) - {""})
    else:
        base["alergenos_set"] = [alergenos_derivados(i, r) for i, r in base.iterrows()]
    unknown = set(base["patron_aa"]) - set(PATRONES_AA)
    if unknown:
        raise ValueError(f"patron_aa desconocido: {unknown}")
    bad_roles = set(base["rol"]) - set(ROLES)
    if bad_roles:
        raise ValueError(f"rol desconocido: {bad_roles}")
    return Composicion(base, fuente)
