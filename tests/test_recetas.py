"""T23 · recetas externas como unidad de cálculo (ADR-0006). Mini-biblioteca SINTÉTICA del mismo formato.
Los valores esperados se calculan aquí, directamente con las filas de la base FDC (independiente de recetas.py)."""
from pathlib import Path

import pandas as pd
import pytest

from nutriuax import base_fdc, recetas as rc
from nutriuax import composicion as c

MINI = Path(__file__).resolve().parent / "fixtures" / "biblioteca_mini.json"


@pytest.fixture(scope="module")
def recs():
    if base_fdc.cargar_completa() is None:
        pytest.skip("sin data/fdc_completa.csv.gz")
    return {r.id: r for r in rc.cargar_recetas(MINI)}


def fdc(ndb: str, n: str) -> float:
    b = base_fdc.cargar_completa().set_index("ndb")
    return float(b.at[ndb, n])


def test_tortilla_nutrientes_a_mano(recs):
    r = recs["mini-tortilla-patata"]
    # 2 huevos × 50 g (01123) + 200 g patata (11352) + 20 ml × 0,92 aceite (04053); la sal no aporta
    prot = 100 * fdc("01123", "proteina") / 100 + 200 * fdc("11352", "proteina") / 100
    kcal = 100 * fdc("01123", "kcal") / 100 + 200 * fdc("11352", "kcal") / 100 + 18.4 * fdc("04053", "kcal") / 100
    leu = 100 * fdc("01123", "leu") / 100 + 200 * fdc("11352", "leu") / 100
    assert r.nutrientes["proteina"] == pytest.approx(prot)
    assert r.nutrientes["kcal"] == pytest.approx(kcal)
    assert r.nutrientes["leu"] == pytest.approx(leu)
    assert r.nutrientes["proteina_animal"] == pytest.approx(100 * fdc("01123", "proteina") / 100)
    assert r.cobertura == pytest.approx(1.0) and r.gramos_crudo == pytest.approx(319.4)
    assert r.rol == "principal" and r.comidas == {"X"} and r.alergenos == {"huevo"}


def test_alergenos_declarados_mas_deducidos(recs):
    r = recs["mini-merluza-gambas"]
    # declarado: pescado; deducidos: gambas → crustáceos; harina → gluten; vino → sulfitos
    assert r.alergenos == {"pescado", "crustaceos", "gluten", "sulfitos"}
    assert r.comidas == {"C", "X"}


def test_unidades_y_metadatos(recs):
    r = recs["mini-lentejas"]
    gr = {i["n"]: i["gramos"] for i in r.ingredientes}
    assert gr["zanahoria"] == 70 and gr["dientes de ajo"] == 4 and gr["aceite de oliva"] == pytest.approx(9.2)
    assert r.batch and r.congelable and r.nevera == 4 and r.minutos == 40


def test_roles_y_cobertura_parcial(recs):
    assert recs["mini-vinagreta"].rol == "no_plato"
    r = recs["mini-rara"]
    assert r.cobertura == pytest.approx(150 / 200) and any("hierba" in a for a in r.avisos)


def test_tabla_de_recetas(recs):
    t = rc.como_tabla(list(recs.values()))
    assert len(t) == 5 and {"kcal", "proteina", "leu", "cobertura", "rol"} <= set(t.columns)


def test_alergenos_del_catalogo():
    t = c.cargar().tabla
    assert t.at["leche_entera", "alergenos_set"] == {"leche"}
    assert t.at["gambas", "alergenos_set"] == {"crustaceos"}
    assert t.at["pan_blanco", "alergenos_set"] == {"gluten"}
    assert t.at["almendras", "alergenos_set"] == {"frutos_cascara"}
    assert t.at["arroz_blanco", "alergenos_set"] == set()


def test_ruta_inexistente_da_error_claro(tmp_path):
    with pytest.raises(FileNotFoundError, match="biblioteca"):
        rc.cargar_recetas(tmp_path / "no_existe.json")
