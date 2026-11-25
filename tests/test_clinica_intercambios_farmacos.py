"""Tests de intercambios EasyDiet, vademécum fármaco-nutriente, índices clínicos y recetas MIT."""
import pytest

from nutriuax import clinica, composicion, farmacos, generador, intercambios, objetivos, recetas


def test_recetas_base_mit_cobertura_total():
    rs = recetas.cargar_recetas()
    assert len(rs) >= 30
    assert all(r.cobertura >= 0.90 for r in rs)


def test_intercambios_menu_y_guia():
    comp = composicion.cargar()
    p = objetivos.Persona(kcal_manual=2000)
    obj = objetivos.calcular_objetivos(p, objetivos.PERFILES["uax_mediterranea"])
    menu = generador.generar(comp, obj, dias=2, semilla=0, tiempo_max=15)
    res = intercambios.intercambios_de_menu(menu, comp)
    assert len(res["por_dia"]) == 2
    assert sum(res["media_diaria"].values()) > 5.0
    guia = intercambios.guia_intercambios(comp)
    assert len(guia) == len(comp.tabla)
    assert (guia["gramos_1_intercambio"] >= 5.0).all()


def test_vademecum_24_farmacos_y_alertas():
    todos = farmacos.listar_farmacos()
    assert len(todos) >= 24
    res = farmacos.evaluar_interacciones(
        ["ieca_ara2", "levodopa", "sglt2", "litio", "inexistente"],
        resumen_diario={"potasio": 3600.0, "sodio": 1200.0, "proteina_gkg": 1.4, "hc": 70.0},
    )
    assert res["total_alertas"] == 4
    assert res["altas"] >= 3
    assert res["desconocidos"] == ["inexistente"]
    # Cada fármaco disparó su alerta cuantitativa
    assert all(len(a["disparadores"]) >= 1 for a in res["alertas"])


def test_antropometria_5_ecuaciones_cribados_pral_y_aas():
    p = objetivos.Persona(codigo="P10", sexo="H", edad=45, peso=95.0, talla=175.0, factor_actividad=1.55)
    ant = clinica.evaluar_antropometria(p, cintura_cm=102.0, cadera_cm=104.0)
    assert ant["imc"] == pytest.approx(31.02, abs=0.05)
    assert ant["clasificacion_oms"] == "Obesidad grado I"
    assert ant["peso_ajustado_kg"] < p.peso
    assert len(ant["ecuaciones_energeticas"]) == 4
    assert ant["riesgo_cintura_talla"] == "moderado_central"

    # Adolescente añade EER IOM 2005 (5ª ecuación)
    ado = objetivos.Persona(codigo="P11", sexo="M", edad=15, peso=52.0, talla=162.0, factor_actividad=1.6)
    ant_ado = clinica.evaluar_antropometria(ado)
    assert "eer_iom_2005_pediatrico" in ant_ado["ecuaciones_energeticas"]

    assert clinica.cribado_must(imc=17.5, perdida_peso_pct_3_6m=12.0, efecto_enfermedad_aguda=True)["puntuacion"] == 6
    assert clinica.cribado_mna_sf(2, 3, 2, 2, 2, 3)["estado"] == "estado_nutricional_normal"
    assert clinica.cribado_mna_sf(0, 1, 1, 0, 1, 1)["estado"] == "malnutricion"
    with pytest.raises(ValueError):
        clinica.cribado_mna_sf(5, 0, 0, 0, 0, 0)

    pral_alk = clinica.calcular_pral(proteina_g=45, fosforo_mg=700, potasio_mg=4200, calcio_mg=900)
    pral_acid = clinica.calcular_pral(proteina_g=160, fosforo_mg=1800, potasio_mg=2000, calcio_mg=600)
    assert pral_alk["pral_meq_dia"] < 0 and pral_alk["clasificacion"] == "alcalinizante"
    assert pral_acid["pral_meq_dia"] > 20 and pral_acid["clasificacion"] == "acidificante_alto"

    comp = composicion.cargar()
    obj = objetivos.calcular_objetivos(objetivos.Persona(kcal_manual=2200), objetivos.PERFILES["uax_mediterranea"])
    menu = generador.generar(comp, obj, dias=1, semilla=0, tiempo_max=15)
    cal = clinica.calidad_proteica_menu(menu)
    assert 0 < cal["aas_global_pct"] <= 100.0
    assert cal["aminoacido_limitante"] in clinica.WHO_PATRON_AAS_MG_G
