"""Tests del calculador de encuestas dietéticas (registro 3 días, FFQ PREDIMED, MEDAS-14 y Maroni; T08-T10)."""
import pytest

from nutriuax import composicion, encuestas


def test_registro_diario_3_dias_con_crudo_cocinado_y_aa():
    comp = composicion.cargar()
    registros = [
        {"participante": "P01", "dia": 1, "comida": "D", "alimento": "avena", "gramos": 60, "estado": "crudo"},
        {"participante": "P01", "dia": 1, "comida": "C", "alimento": "pollo_pechuga", "gramos": 150, "estado": "cocinado"},
        {"participante": "P01", "dia": 1, "comida": "C", "alimento": "arroz_blanco", "gramos": 180, "estado": "cocinado"},
        {"participante": "P01", "dia": 2, "comida": "C", "alimento": "lentejas", "gramos": 220, "estado": "cocinado"},
        {"participante": "P01", "dia": 2, "comida": "X", "alimento": "merluza", "gramos": 180, "estado": "cocinado"},
        {"participante": "P01", "dia": 3, "comida": "C", "alimento": "pechuga de pollo", "gramos": 140, "estado": "crudo"},
    ]
    res = encuestas.calcular_registro_diario(registros, comp, peso_kg=70.0, masa_magra_kg=55.0)
    assert res["media"]["dias"] == 3
    assert res["media"]["kcal"] > 0
    assert res["media"]["leu_mgkg"] > 0
    assert res["media"]["kg_referencia_aa"] == 55.0
    assert len(res["diario"]) == 3


def test_ffq_predimed_ventana_anual_y_8_semanas():
    comp = composicion.cargar()
    respuestas = [
        {"alimento": "aove", "racion_g": 10, "frecuencia": "4-6/dia"},
        {"alimento": "lentejas", "racion_g": 200, "frecuencia": "2-4/sem"},
        {"alimento": "manzana", "racion_g": 150, "frecuencia": "2-3/dia"},
        {"alimento": "merluza", "racion_g": 150, "frecuencia": "2-4/sem"},
        {"alimento": "miel", "racion_g": 15, "frecuencia": "nunca"},
    ]
    r_anual = encuestas.calcular_ffq_predimed(respuestas, comp, peso_kg=70.0, ventana="1_ano")
    assert r_anual["items_activos"] == 4
    assert r_anual["media"]["kcal"] > 500
    assert not any("8 semanas" in a for a in r_anual["avisos"])

    r_8w = encuestas.calcular_ffq_predimed(respuestas, comp, peso_kg=70.0, ventana="8_semanas")
    assert any("8 semanas" in a for a in r_8w["avisos"])


def test_medas14_umbrales_exactos():
    full = {
        "aove_grasa_principal": True, "aove_cucharadas_dia": 4.0, "verdura_raciones_dia": 2.0,
        "fruta_raciones_dia": 3.0, "carne_roja_raciones_dia": 0.5, "mantequilla_raciones_dia": 0.0,
        "bebidas_azucaradas_dia": 0.0, "vino_copas_semana": 7.0, "legumbres_raciones_semana": 3.0,
        "pescado_marisco_semana": 3.0, "bolleria_comercial_semana": 2.0, "frutos_secos_semana": 3.0,
        "prefiere_ave_sobre_roja": True, "sofrito_semana": 2.0,
    }
    r14 = encuestas.calcular_medas14(full)
    assert r14.puntuacion == 14 and r14.categoria == "adherente"

    bajo = dict(full, aove_cucharadas_dia=1, verdura_raciones_dia=1, fruta_raciones_dia=1,
                carne_roja_raciones_dia=2, mantequilla_raciones_dia=2, bebidas_azucaradas_dia=2,
                vino_copas_semana=0, legumbres_raciones_semana=0, pescado_marisco_semana=0, bolleria_comercial_semana=5)
    r_low = encuestas.calcular_medas14(bajo)
    assert r_low.puntuacion == 4 and r_low.categoria == "no_adherente"


def test_maroni_y_adherencia_combinada():
    # Peso 70 kg → Maroni para NUU=10 g/d: 6.25 * (10 + 2.17) = 76.06 g
    assert encuestas.proteina_maroni(10.0, 70.0) == pytest.approx(76.06, abs=0.05)

    # Brazo mediterránea: objetivo 1.1 g/kg = 77 g/día ± 15%
    adh_ok = encuestas.evaluar_adherencia(
        "P01", "mediterranea", [75.0, 78.0, 80.0], [2100.0, 2150.0, 2050.0],
        peso_kg=70.0, nuu_g_dia=10.2, medas14_puntos=10,
    )
    assert adh_ok.clasificacion == "adherente" and adh_ok.proteina_ok and adh_ok.maroni_ok

    # Sin Maroni se clasifica y marca sin_maroni=True
    adh_sin = encuestas.evaluar_adherencia(
        "P02", "hiperproteica", [145.0, 150.0, 148.0], [2500.0, 2500.0, 2500.0],
        peso_kg=70.0, nuu_g_dia=None,
    )
    assert adh_sin.sin_maroni and adh_sin.clasificacion == "adherente"
    assert any("Informativo" in n for n in adh_sin.notas)
