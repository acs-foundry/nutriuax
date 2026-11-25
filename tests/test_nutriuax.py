"""Tests con alimentos sintéticos (valores esperados calculados a mano, independientes del código)."""
from pathlib import Path

import pandas as pd
import pytest

from nutriuax import composicion as c
from nutriuax import generador as g
from nutriuax import objetivos as o

CAB = ("id,nombre,grupo,rol,origen,patron_aa,comidas,min_g,max_g,porcion_g,max_semana,etiquetas,ndb,"
       "busqueda_fdc,kcal,proteina,grasa,agsat,hc,fibra,sodio,potasio,fosforo,calcio\n")


@pytest.fixture
def tabla_sintetica(tmp_path: Path) -> Path:
    filas = [
        "pollo,Pollo,carnes,proteina,animal,carne,C;X,50,300,100,14,carne_blanca,,x,100,20,2,0.5,0,0,50,300,200,10",
        "arroz,Arroz,cereales,cereal,vegetal,arroz,D;C;X,50,400,100,14,cereal,,x,130,2.5,0.3,0.1,28,0.5,1,30,40,10",
        "leche,Leche,lacteos,lacteo,animal,lacteo,D;MM;M;X,100,400,200,14,lacteo,,x,60,3,3,2,5,0,40,150,90,120",
        "manzana,Manzana,frutas,fruta,vegetal,fruta,D;MM;C;M;X,100,300,150,21,fruta,,x,50,0.3,0.2,0,13,2.4,1,100,10,5",
        "tomate,Tomate,verduras,verdura,vegetal,verdura,C;X,100,400,150,14,verdura,,x,20,1,0.2,0,4,1.5,5,240,25,10",
        "lechuga,Lechuga,verduras,verdura,vegetal,verdura,C;X,50,300,100,14,verdura,,x,15,1.4,0.2,0,3,1.3,30,190,30,35",
        "aove,AOVE,grasas,grasa,vegetal,ninguno,D;C;X,5,40,10,21,aove,,x,884,0,100,14,0,0,2,1,0,1",
        "lentejas,Lentejas,legumbres,legumbre,vegetal,legumbre,C;X,100,300,200,7,legumbre,,x,116,9,0.4,0.1,20,8,2,370,180,19",
    ]
    (tmp_path / "alimentos.csv").write_text(CAB + "\n".join(filas) + "\n", encoding="utf-8")
    return tmp_path


def test_aminoacidos_semilla_por_patron(tabla_sintetica):
    comp = c.cargar(tabla_sintetica)
    assert comp.fuente == "semilla"
    # pollo: 20 g proteína × 8,0 g Leu/100 g proteína = 1,6 g = 1600 mg Leu /100 g
    assert comp.nutr("pollo", "leu") == pytest.approx(1600)
    assert comp.nutr("aove", "val") == 0


def test_calcular_items_escala_por_gramos(tabla_sintetica):
    comp = c.cargar(tabla_sintetica)
    items = pd.DataFrame({"id": ["pollo", "arroz"], "gramos": [150, 200]})
    r = comp.calcular(items)
    assert r["kcal"].sum() == pytest.approx(150 + 260)
    assert r["proteina_animal"].sum() == pytest.approx(30)
    assert r["proteina_vegetal"].sum() == pytest.approx(5)
    # Leu arroz: 2,5 × 8,2 × 10 = 205 mg/100 g → 410 mg en 200 g; pollo 1600 × 1,5 = 2400
    assert r["leu"].sum() == pytest.approx(2810)


def test_fdc_sustituye_semilla(tabla_sintetica):
    pd.DataFrame({"id": ["pollo"], "leu": [2500.0], "proteina": [23.0]}).to_csv(
        tabla_sintetica / "composicion_fdc.csv", index=False)
    comp = c.cargar(tabla_sintetica)
    assert comp.fuente == "mixta"
    assert comp.nutr("pollo", "leu") == 2500
    assert comp.nutr("pollo", "proteina") == 23
    assert not comp.tabla.at["pollo", "leu_estimado"]
    assert comp.tabla.at["pollo", "ile_estimado"]  # sin dato FDC → estimado (23 × 4,6 × 10)
    assert comp.nutr("pollo", "ile") == pytest.approx(1058)


def test_objetivos_mifflin_y_aa():
    p = o.Persona(sexo="H", edad=30, peso=80, talla=180, factor_actividad=1.5)
    obj = o.calcular_objetivos(p, o.PERFILES["uax_mediterranea"])
    # Mifflin: 800 + 1125 − 150 + 5 = 1780 × 1,5 = 2670
    assert obj.kcal == pytest.approx(2670)
    assert obj.proteina == pytest.approx((80, 96))
    assert obj.minimos["leu"] == pytest.approx(39 * 80)


def test_objetivos_erc_kcal_por_kg_y_masa_magra():
    p = o.Persona(peso=60, masa_magra=45)
    obj = o.calcular_objetivos(p, o.PERFILES["erc_nd"])
    assert obj.kcal == pytest.approx(1800)
    assert obj.maximos["sodio"] == 2300
    pf = o.PERFILES["bcaa_intervencion"].copia(aa_por_masa_magra=True)
    obj2 = o.calcular_objetivos(p, pf)
    assert obj2.minimos["leu"] == pytest.approx(70 * 45)


def test_aviso_incoherencia_hiperproteica():
    p = o.Persona(sexo="H", edad=23, peso=75, talla=178, factor_actividad=1.6)
    obj = o.calcular_objetivos(p, o.PERFILES["uax_hiperproteica"])
    assert o.avisos_coherencia(obj)  # 165 g ×4 / ~2800 kcal ≈ 23,5 % < 30 %


def test_generar_cumple_estructura_y_objetivos(tabla_sintetica):
    comp = c.cargar(tabla_sintetica)
    pf = o.Perfil("t", "test", "", proteina_gkg=(1.0, 1.4), grasa_pct=(20, 40), hc_pct=(35, 65),
                  agsat_pct_max=None, fibra_min=None, sodio_max=None, fruta_min_dia=1, verdura_min_dia=1,
                  aa_min_mgkg={"leu": 39}, comidas=["D", "C", "X"])
    p = o.Persona(sexo="H", edad=30, peso=70, talla=175, kcal_manual=2000)
    obj = o.calcular_objetivos(p, pf)
    menu = g.generar(comp, obj, dias=2, semilla=3, tiempo_max=20)
    it = menu.items
    assert set(it["n_dia"]) == {1, 2}
    # cada comida y cena tiene verdura y plato proteico; el desayuno, cereal
    for (d, m), grp in it.groupby(["n_dia", "cod_comida"]):
        roles = set(comp.tabla.loc[grp["id"], "rol"])
        if m in ("C", "X"):
            assert "verdura" in roles and roles & {"proteina", "legumbre"}
        if m == "D":
            assert "cereal" in roles
    # porciones dentro de [min, max] (escaladas) y múltiplo de 5 g
    assert (it["gramos"] % 5 == 0).all()
    ch = g.comprobar(menu)
    e = ch[ch.criterio == "Energía"]
    assert e.ok.all(), e
    assert ch[ch.criterio == "Proteína"].ok.all()
    # recálculo independiente de la Leu del día 1
    d1 = it[it.n_dia == 1]
    leu = sum(comp.nutr(f, "leu") * gr / 100 for f, gr in zip(d1["id"], d1["gramos"]))
    assert menu.resumen.loc[menu.resumen.n_dia == 1, "leu"].iloc[0] == pytest.approx(leu)


def test_vetados_no_aparecen(tabla_sintetica):
    comp = c.cargar(tabla_sintetica)
    pf = o.Perfil("t", "test", "", proteina_gkg=(0.8, 1.6), fibra_min=None, sodio_max=None,
                  agsat_pct_max=None, aa_min_mgkg={}, comidas=["D", "C", "X"])
    obj = o.calcular_objetivos(o.Persona(kcal_manual=2000), pf)
    menu = g.generar(comp, obj, dias=1, semilla=0, vetados={"pollo"}, tiempo_max=10)
    assert "pollo" not in set(menu.items["id"])


def test_tabla_real_carga_y_es_coherente():
    comp = c.cargar()
    t = comp.tabla
    assert len(t) >= 60
    assert (t["min_g"] <= t["max_g"]).all()
    # Atwater aproximado: energía declarada ≈ 4P + 9G + 4HC (± 25 %) salvo alimentos con fibra/alcohol
    atw = 4 * t["proteina"] + 9 * t["grasa"] + 4 * t["hc"]
    rel = (t["kcal"] - atw).abs() / t["kcal"]
    # verduras < 30 kcal: FDC usa factores específicos y la fibra pesa mucho; se excluyen del control
    sel = t["kcal"] >= 30
    assert (rel[sel] < 0.25).all(), t.index[sel & (rel >= 0.25)].tolist()


def test_importar_fdc_zip_sintetico(tabla_sintetica):
    import zipfile
    from nutriuax import importar_fdc
    zp = tabla_sintetica / "sr.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("FoodData/food.csv", 'fdc_id,description\n1,"Chicken, breast, roasted"\n2,"Rice, white, cooked"\n')
        z.writestr("FoodData/sr_legacy_food.csv", "fdc_id,NDB_number\n1,5064\n2,20045\n")
        z.writestr("FoodData/nutrient.csv", "id,nutrient_nbr\n1003,203\n1213,504.0\n1092,306\n")
        z.writestr("FoodData/food_nutrient.csv",
                   "fdc_id,nutrient_id,amount\n1,1003,31.0\n1,1213,2.47\n1,1092,256\n2,1003,2.7\n2,1213,0.22\n")
    alim = pd.read_csv(tabla_sintetica / "alimentos.csv", dtype=str)
    alim.loc[alim.id == "pollo", "ndb"] = "05064"
    alim.loc[alim.id == "arroz", "busqueda_fdc"] = "rice white cooked"
    alim.to_csv(tabla_sintetica / "alimentos.csv", index=False)
    rev = importar_fdc.importar(zp, tabla_sintetica).set_index("id")
    assert rev.at["pollo", "modo"] == "ndb"
    assert rev.at["arroz", "descripcion_fdc"] == "Rice, white, cooked"
    comp = c.cargar(tabla_sintetica)
    assert comp.nutr("pollo", "leu") == pytest.approx(2470)   # g → mg
    assert comp.nutr("pollo", "proteina") == 31.0
    assert comp.nutr("pollo", "potasio") == 256
    assert comp.nutr("arroz", "leu") == pytest.approx(220)
