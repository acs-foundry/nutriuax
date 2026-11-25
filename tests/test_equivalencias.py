"""T22 · tabla de equivalencias ingrediente → alimento canónico (ADR-0006). Casos reales de la prueba del 30-10."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from nutriuax import base_fdc
from nutriuax import equivalencias as eq

RAIZ = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("entrada, esperado", [
    ("Cebolla picada", "cebolla"),
    ("tomate, pelado y troceado", "tomate"),
    ("Lechugas variadas (escarola, achicoria roja y canónigos)", "lechugas variadas"),
    ("2 dientes de ajo grandes", "2 dientes de ajo"),
    ("piñones", "pinones"),
])
def test_normalizar(entrada, esperado):
    assert eq.normalizar(entrada) == esperado


@pytest.mark.parametrize("nombre, q, u, alimento, gramos", [
    ("huevo", 1, "ud", "huevo", 50),                 # antes «huevo» → berenjena con buscar()
    ("huevos", 2, "ud", "huevo", 100),
    ("vino blanco", 100, "ml", "vino_blanco", 99),   # antes → vinagre
    ("arroz", 80, "g", "arroz", 80),                 # antes → fideos de arroz
    ("arroz integral", 80, "g", "arroz_integral", 80),
    ("fideos de arroz", 50, "g", "fideo_arroz", 50),
    ("panceta", 30, "g", "bacon", 30),               # «pan» no encaja dentro de «panceta»
    ("pan", 1, "ud", "pan", 40),
    ("dientes de ajo", 2, "ud", "ajo", 8),
    ("aceite de oliva virgen extra", 10, "ml", "aceite_oliva", 9.2),
    ("lomos de mero", 150, "g", "mero", 150),        # quitando «lomos de»
    ("nuez moscada", 1, "g", "nulo", 1),
    ("nueces", 3, "ud", "nuez", 15),
    ("sal", 2, "g", "nulo", 2),
    ("yogur natural desnatado", 1, "ud", "yogur_desnatado", 125),
    ("pechuga de pavo abierta", 120, "g", "pavo", 120),
])
def test_resolver_casos_reales(nombre, q, u, alimento, gramos):
    e = eq.resolver(nombre, q, u)
    assert e.alimento == alimento
    assert e.gramos == pytest.approx(gramos)


def test_alergenos_y_desconocidos():
    assert eq.resolver("gambas", 100, "g").alergenos == {"crustaceos"}
    assert eq.resolver("queso parmesano", 20, "g").alergenos == {"leche"}
    e = eq.resolver("ingrediente inventado xyz", 10, "g")
    assert e.alimento is None and e.revisar


def test_tablas_coherentes_con_fdc():
    t = eq.cargar()
    base = base_fdc.cargar_completa()
    if base is None:
        pytest.skip("sin data/fdc_completa.csv.gz")
    ndb_validos = set(base["ndb"])
    con_ndb = t.canonicos[t.canonicos["ndb"] != ""]
    assert set(con_ndb["ndb"]) <= ndb_validos
    for a in con_ndb.index:
        for alg in str(t.canonicos.at[a, "alergenos"]).split(";"):
            assert alg == "" or alg in eq.ALERGENOS_UE, (a, alg)
    usados = {r[1] for r in t.reglas}
    assert usados <= set(t.canonicos.index)


def test_cobertura_con_mini_biblioteca(tmp_path):
    sys.path.insert(0, str(RAIZ / "scripts"))
    from cobertura_equivalencias import analizar
    recetas = [{"id": "r1", "ingredientes": [
        {"n": "patatas", "q": 200, "u": "g", "s": "fruteria"},
        {"n": "huevos", "q": 2, "u": "ud", "s": "lacteos"},
        {"n": "aceite de oliva", "q": 20, "u": "ml", "s": "despensa"},
        {"n": "ingrediente raro", "q": 18.4, "u": "g", "s": "despensa"}]}]
    df = analizar(recetas)
    mapeado = df.loc[df["alimento"].notna(), "gramos"].sum()
    assert mapeado == pytest.approx(200 + 100 + 18.4)
    assert mapeado / df["gramos"].sum() == pytest.approx(318.4 / 336.8)
