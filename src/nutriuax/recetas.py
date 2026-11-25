"""Recetas de una biblioteca externa como unidad de cálculo (ADR-0006, T23).

Lee la biblioteca (formato Menú Familiar) de la ruta de `config/fuentes.toml` o de la que se pase; nunca la copia.
Por cada receta calcula, por ración de adulto y en crudo: nutrientes (suma de ingredientes vía la tabla de
equivalencias y la base FDC completa), alérgenos UE-14 (los declarados ∪ los de sus ingredientes), rol de plato
y cobertura (fracción de sus gramos que se han podido mapear).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

try:  # Python ≥ 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

import pandas as pd

from . import base_fdc
from . import equivalencias as eq
from .composicion import AMINOACIDOS, MACROS, MINERALES, NUTRIENTES

RAIZ = Path(__file__).resolve().parents[2]

# alérgenos declarados en la biblioteca → nombres UE-14 de NutriUAX
ALERGENOS_BIBLIOTECA = {"lacteos": "leche", "leche": "leche", "huevo": "huevo", "gluten": "gluten",
                        "pescado": "pescado", "sulfitos": "sulfitos", "crustaceos": "crustaceos",
                        "frutos_cascara": "frutos_cascara", "moluscos": "moluscos", "apio": "apio",
                        "mostaza": "mostaza", "soja": "soja", "sesamo": "sesamo", "cacahuete": "cacahuete",
                        "altramuces": "altramuces"}
COMIDAS_BIBLIOTECA = {"desayuno": "D", "comida": "C", "merienda": "M", "cena": "X"}
ROL_POR_CATEGORIA = {
    "pescado": "principal", "carne": "principal", "ave": "principal", "legumbre": "principal",
    "arroz_pasta": "principal", "huevo": "principal", "infantil": "principal",
    "verdura": "primero", "sopa_crema": "primero", "entrante": "primero", "guarnicion": "guarnicion",
    "postre": "postre", "desayuno": "desayuno", "masa_pan": "otro",
    "salsa_base": "no_plato", "bebida": "no_plato", "aperitivo": "no_plato",
}


@dataclass
class Receta:
    id: str
    nombre: str
    categoria: str
    rol: str
    comidas: set[str]
    grupos: set[str]
    alergenos: set[str]
    nutrientes: dict[str, float]          # por ración de adulto
    cobertura: float                      # fracción de gramos mapeados y convertidos
    gramos_crudo: float
    ingredientes: list[dict]              # {n, q, u, s, alimento, gramos}
    batch: bool = False
    congelable: bool = False
    nevera: int = 0
    facil: bool = False
    minutos: int | None = None
    avisos: list[str] = field(default_factory=list)


def ruta_biblioteca(ruta: str | Path | None = None) -> Path:
    if ruta:
        return Path(ruta)
    with (RAIZ / "config" / "fuentes.toml").open("rb") as fh:
        cfg = tomllib.load(fh)
    return (RAIZ / cfg["recetas"]["biblioteca"]).resolve()


def cobertura_minima() -> float:
    with (RAIZ / "config" / "fuentes.toml").open("rb") as fh:
        return float(tomllib.load(fh)["recetas"].get("cobertura_minima", 0.9))


@lru_cache(maxsize=4096)
def _fila(ndb: str) -> dict:
    s = base_fdc.fila_composicion(ndb)
    return {k: s[k] for k in NUTRIENTES} | {"origen": s["origen"]} | {a + "_estimado": s[a + "_estimado"]
                                                                       for a in AMINOACIDOS}


def calcular_receta(r: dict, tablas: eq.Tablas | None = None) -> Receta:
    t = tablas or eq.cargar()
    tot = {n: 0.0 for n in NUTRIENTES} | {"proteina_animal": 0.0, "proteina_vegetal": 0.0}
    g_tot = g_ok = 0.0
    alg = {ALERGENOS_BIBLIOTECA[a] for a in r.get("alergenos", []) if a in ALERGENOS_BIBLIOTECA}
    ingredientes, avisos, estimado = [], [], False
    for i in r.get("ingredientes", []):
        e = eq.resolver(i["n"], float(i["q"]), i["u"], t)
        gramos = e.gramos
        peso = gramos if gramos is not None else float(i["q"]) * (50.0 if i["u"] == "ud" else 1.0)
        g_tot += peso
        ingredientes.append(dict(n=i["n"], q=i["q"], u=i["u"], s=i.get("s", ""), alimento=e.alimento, gramos=gramos))
        if e.alimento is None or gramos is None:
            avisos.append(f"sin equivalencia: «{i['n']}»" if e.alimento is None else f"sin gramos por unidad: «{i['n']}»")
            continue
        g_ok += gramos
        alg |= set(e.alergenos)
        ndb = t.canonicos.at[e.alimento, "ndb"]
        if not ndb:
            continue
        f = _fila(ndb)
        for n in NUTRIENTES:
            tot[n] += f[n] * gramos / 100.0
        tot["proteina_animal" if f["origen"] == "animal" else "proteina_vegetal"] += f["proteina"] * gramos / 100.0
        estimado |= any(f[a + "_estimado"] for a in ("leu", "ile", "val")) and f["proteina"] * gramos > 100
    if estimado:
        avisos.append("Leu/Ile/Val de algún ingrediente estimados por patrón (sin dato FDC)")
    cat = r.get("categoria", "")
    return Receta(
        id=r["id"], nombre=r.get("nombre", r["id"]), categoria=cat, rol=ROL_POR_CATEGORIA.get(cat, "otro"),
        comidas={COMIDAS_BIBLIOTECA[c] for c in r.get("comidas", []) if c in COMIDAS_BIBLIOTECA},
        grupos=set(r.get("grupos", [])), alergenos=alg, nutrientes=tot,
        cobertura=(g_ok / g_tot) if g_tot else 0.0, gramos_crudo=g_ok, ingredientes=ingredientes,
        batch=bool(r.get("batch")), congelable=bool(r.get("congelable")), nevera=int(r.get("nevera") or 0),
        facil=bool(r.get("facil")), minutos=r.get("minutos"), avisos=avisos)


def cargar_recetas(ruta: str | Path | None = None) -> list[Receta]:
    """Todas las recetas de la biblioteca, calculadas. Lanza FileNotFoundError con la ruta si no existe."""
    p = ruta_biblioteca(ruta)
    if not p.exists():
        raise FileNotFoundError(f"No encuentro la biblioteca de recetas en {p} (config/fuentes.toml o --recetas)")
    datos = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(datos, dict):
        datos = datos.get("recetas", [])
    t = eq.cargar()
    return [calcular_receta(r, t) for r in datos]


def como_tabla(recetas: list[Receta]) -> pd.DataFrame:
    """Una fila por receta con metadatos y nutrientes por ración (para el generador y los informes)."""
    filas = []
    for r in recetas:
        filas.append(dict(id=r.id, nombre=r.nombre, categoria=r.categoria, rol=r.rol,
                          comidas=";".join(sorted(r.comidas)), grupos=";".join(sorted(r.grupos)),
                          alergenos=";".join(sorted(r.alergenos)), cobertura=round(r.cobertura, 3),
                          gramos_crudo=round(r.gramos_crudo, 1), batch=r.batch, congelable=r.congelable,
                          nevera=r.nevera, minutos=r.minutos, n_avisos=len(r.avisos),
                          **{k: round(v, 2) for k, v in r.nutrientes.items()}))
    return pd.DataFrame(filas)


__all__ = ["Receta", "calcular_receta", "cargar_recetas", "como_tabla", "ruta_biblioteca", "cobertura_minima",
           "MACROS", "MINERALES"]
