"""T13 · base FDC completa y búsqueda en español (zip sintético; valores esperados a mano)."""
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from nutriuax import base_fdc as b
from nutriuax import composicion as c


@pytest.fixture
def zip_fdc(tmp_path: Path) -> Path:
    zp = tmp_path / "sr.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("FD/food.csv", "fdc_id,description,food_category_id\n"
                   '1,"Chickpeas (garbanzo beans, bengal gram), mature seeds, raw",16\n'
                   '2,"Chickpeas (garbanzo beans, bengal gram), mature seeds, cooked, boiled, without salt",16\n'
                   '3,"Chicken, broilers or fryers, breast, meat only, cooked, roasted",5\n'
                   '4,"Chicken breast tenders, breaded, cooked, microwaved",5\n'
                   '5,"Bread, french or vienna (includes sourdough)",18\n')
        z.writestr("FD/sr_legacy_food.csv", "fdc_id,NDB_number\n1,16056\n2,16057\n3,5064\n4,5326\n5,18029\n")
        z.writestr("FD/food_category.csv", 'id,code,description\n5,0500,Poultry Products\n'
                   '16,1600,Legumes and Legume Products\n18,1800,Baked Products\n')
        z.writestr("FD/nutrient.csv", "id,nutrient_nbr\n1003,203\n1008,208\n1213,504.0\n1212,503\n1219,510\n")
        z.writestr("FD/food_nutrient.csv", "fdc_id,nutrient_id,amount\n"
                   "1,1003,20.47\n1,1008,378\n1,1213,1.465\n1,1212,0.882\n1,1219,0.865\n"
                   "2,1003,8.86\n2,1008,164\n2,1213,0.631\n2,1212,0.380\n2,1219,0.372\n"
                   "3,1003,31.02\n3,1008,165\n3,1213,2.475\n3,1212,1.641\n3,1219,1.544\n"
                   "4,1003,15\n4,1008,270\n4,1213,1.1\n4,1212,0.7\n4,1219,0.7\n"
                   "5,1003,10.75\n5,1008,272\n")
    return zp


@pytest.fixture
def base(zip_fdc, tmp_path) -> pd.DataFrame:
    (tmp_path / "glosario_es_en.csv").write_text(
        "es,en\ngarbanzo,chickpeas\npechuga,breast\npollo,chicken\ncocido,cooked|boiled\npan,bread\n",
        encoding="utf-8")
    b.generar_completa(zip_fdc, tmp_path)
    b.cargar_glosario.cache_clear()
    return b.cargar_completa(tmp_path)


def test_genera_base_completa_con_hash_y_unidades(base, tmp_path):
    assert len(base) == 5
    assert (tmp_path / "fdc_completa.csv.gz.sha256").read_text().endswith("fdc_completa.csv.gz\n")
    g = base.set_index("ndb")
    assert g.at["16057", "leu"] == pytest.approx(631)        # 0,631 g → mg
    assert g.at["05064", "origen"] == "animal"
    assert g.at["16056", "origen"] == "vegetal"
    assert pd.isna(g.at["18029", "leu"]) and not g.at["18029", "tiene_aa"]


def test_buscar_en_espanol(base, tmp_path):
    r = b.buscar("garbanzo", data_dir=tmp_path)
    assert set(r["ndb"][:2]) == {"16056", "16057"}
    assert b.buscar("garbanzos cocidos", data_dir=tmp_path)["ndb"].iloc[0] == "16057"   # plural + estado
    r = b.buscar("pechuga de pollo", data_dir=tmp_path)
    assert r["ndb"].iloc[0] == "05064"                       # el empanado («breaded») queda detrás
    assert b.buscar("chickpeas raw", data_dir=tmp_path)["ndb"].iloc[0] == "16056"   # también en inglés
    assert b.buscar("xyzzy", data_dir=tmp_path).empty


def test_fila_composicion_y_calculo(base, tmp_path):
    f = b.fila_composicion("16057", tmp_path)
    assert f.name == "fdc_16057" and f["leu"] == pytest.approx(631) and not f["leu_estimado"]
    pan = b.fila_composicion("18029", tmp_path)              # sin AA en FDC → estimado por patrón trigo
    assert pan["leu_estimado"] and pan["leu"] == pytest.approx(10.75 * 6.8 * 10)
    comp = c.Composicion(pd.DataFrame(), "fdc").anadir([f, pan])
    r = comp.calcular(pd.DataFrame({"id": ["fdc_16057"], "gramos": [200]}))
    assert r["leu"].sum() == pytest.approx(1262)
    assert r["proteina_vegetal"].sum() == pytest.approx(17.72)
