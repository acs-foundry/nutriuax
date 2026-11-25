"""Equivalencias ingrediente de receta → alimento canónico (ADR-0006, T22).

Dos tablas curadas y revisables:
- `data/alimentos_canonicos.csv`: alimento canónico → NDB de FDC (en CRUDO o tal cual se compra; vacío = sin
  aporte: sal, agua, especias en cantidad despreciable), gramos por unidad, densidad (g/ml) y alérgenos UE-14.
- `data/equivalencias_ingredientes.csv`: patrón (expresión regular sobre el nombre NORMALIZADO, anclada al
  principio) → alimento canónico, en orden: gana la primera fila que encaja. Confianza y marca «revisar».
Nunca se empareja por búsqueda libre: lo que no encaja queda sin mapear y se informa.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .composicion import DATA_DIR

ALERGENOS_UE = ["gluten", "crustaceos", "huevo", "pescado", "cacahuete", "soja", "leche", "frutos_cascara",
                "apio", "mostaza", "sesamo", "sulfitos", "altramuces", "moluscos"]

# palabras de preparación, tamaño o estado que no cambian el alimento
_RUIDO = r"""picad[oa]s?|troceado?s?|trocead[oa]s?|en dados|en trozos|en rodajas|en tiras|en juliana|cortad[oa]s?|
pelad[oa]s?|lavad[oa]s?|rallad[oa]s?|machacad[oa]s?|fresc[oa]s?|grandes?|pequen[oa]s?|median[oa]s?|maduro?s?|madura?s?|
a temperatura ambiente|del tiempo|al gusto|opcional|aprox(imadamente)?|para decorar|para servir|para espolvorear|
escurrid[oa]s?|congelad[oa]s?|descongelad[oa]s?|limpi[oa]s?|sin piel|sin hueso|sin espinas|sin semillas|deshuesad[oa]s?|
en polvo|finamente|muy|bien|unos?|unas?|de calidad|ecologic[oa]s?|extra|tierno?s?|tiernas?"""
_RUIDO_RE = re.compile(r"\b(" + re.sub(r"\s+", "", _RUIDO) + r")\b")


def normalizar(nombre: str) -> str:
    """minúsculas, sin tildes ni paréntesis, sin palabras de preparación/tamaño, sin espacios dobles.
    (No singulariza: los patrones admiten el plural con `s?`.)"""
    s = unicodedata.normalize("NFKD", str(nombre).lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\([^)]*\)", " ", s)                       # «(escarola, achicoria…)»
    s = re.sub(r"[^a-z0-9ñ%/ ,.-]", " ", s.replace("ñ", "n"))
    s = s.split(",")[0]                                     # «tomate, pelado y troceado» → «tomate»
    s = _RUIDO_RE.sub(" ", s)
    s = re.sub(r"\b(y|o)\s*$", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .-")


def _alternativas(patron: str) -> list[str]:
    """Divide por «|» de primer nivel (fuera de paréntesis)."""
    partes, nivel, actual = [], 0, ""
    for ch in patron:
        if ch == "(":
            nivel += 1
        elif ch == ")":
            nivel -= 1
        if ch == "|" and nivel == 0:
            partes.append(actual)
            actual = ""
        else:
            actual += ch
    return partes + [actual]


def _con_limites(patron: str) -> str:
    """«(pan|pera).*» → «(pan|pera)\\b.*»: la palabra debe terminar ahí («pan» no encaja en «panceta»)."""
    out = []
    for alt in _alternativas(patron):
        if len(alt) > 2 and alt.endswith(".*") and not alt[:-2].endswith(r"\b"):
            alt = alt[:-2] + r"\b.*"
        out.append(alt)
    return "|".join(out)


@dataclass(frozen=True)
class Tablas:
    canonicos: pd.DataFrame        # índice = alimento
    reglas: list[tuple[re.Pattern, str, str, bool]]   # (patrón, alimento, confianza, revisar)


@lru_cache(maxsize=4)
def cargar(data_dir: Path | None = None) -> Tablas:
    d = Path(data_dir or DATA_DIR)
    can = pd.read_csv(d / "alimentos_canonicos.csv", dtype={"ndb": str}, keep_default_na=False)
    can = can.set_index("alimento")
    if not can.index.is_unique:
        raise ValueError(f"alimentos_canonicos.csv: duplicados {can.index[can.index.duplicated()].tolist()}")
    eq = pd.read_csv(d / "equivalencias_ingredientes.csv", dtype=str, keep_default_na=False, comment="#")
    reglas = []
    for i, r in enumerate(eq.itertuples(), start=2):
        if r.alimento not in can.index:
            raise ValueError(f"equivalencias_ingredientes.csv línea {i}: alimento «{r.alimento}» no está en los canónicos")
        try:
            pat = re.compile(r"(?:" + _con_limites(r.patron) + r")\b")
        except re.error as e:
            raise ValueError(f"equivalencias_ingredientes.csv línea {i}: patrón inválido ({e})") from None
        reglas.append((pat, r.alimento, r.confianza or "alta", r.revisar.strip().lower() in ("si", "sí", "1", "true")))
    return Tablas(can, reglas)


@dataclass(frozen=True)
class Equivalencia:
    alimento: str | None
    gramos: float | None           # gramos en crudo (None si no se puede convertir la unidad)
    confianza: str
    revisar: bool
    alergenos: frozenset[str]


def resolver(nombre: str, q: float, u: str, tablas: Tablas | None = None) -> Equivalencia:
    """Ingrediente {n, q, u} → alimento canónico y gramos. Sin regla → alimento None."""
    t = tablas or cargar()
    n = normalizar(nombre)
    for variante in dict.fromkeys((n, _sin_corte(n))):     # 1.º tal cual; 2.º sin «lomos de», «filetes de»…
        for pat, alim, conf, rev in t.reglas:
            if pat.match(variante):
                fila = t.canonicos.loc[alim]
                gramos = _a_gramos(float(q), u, fila)
                alg = frozenset(a for a in str(fila["alergenos"]).split(";") if a)
                return Equivalencia(alim, gramos, conf, rev, alg)
    return Equivalencia(None, None, "", True, frozenset())


_CORTE = re.compile(r"^(lomos?|filetes?|filetitos?|supremas?|rodajas?|colas?|medallones?|tubos?|lonchas?|pencas?|"
                    r"ramas?|ramitas?|pulpa|trozos?|dados?|tacos?|tiras?|gajos?|taquitos?|escalopes?|chuletas?|"
                    r"espalda|paletilla|pierna|cuarto|cuartos|tronco|corazones?|ramitos?|centros?|latas?|botes?|sobres?)( (finas?|finos?|gruesas?|gruesos?))?"
                    r" de (la |el |los |las )?")


def _sin_corte(n: str) -> str:
    return _CORTE.sub("", n, count=1)


def _a_gramos(q: float, u: str, fila) -> float | None:
    u = (u or "g").lower()
    if u == "g":
        return q
    if u == "kg":
        return q * 1000
    if u == "ml":
        dens = float(fila["g_por_ml"] or 1.0)
        return q * dens
    if u == "l":
        return q * 1000 * float(fila["g_por_ml"] or 1.0)
    if u in ("ud", "u", "unidad"):
        gu = fila["g_por_ud"]
        return q * float(gu) if gu not in ("", None) else None
    return None
