"""T21 · perfiles domésticos y suelos de seguridad (ADR-0004 §3-5). Personas SINTÉTICAS; valores a mano."""
import pytest

from nutriuax import objetivos as o
from nutriuax.perfiles import PerfilInvalido, cargar_perfiles
from nutriuax.seguridad import PerfilNoPermitido, objetivos_seguros

P = o.PERFILES
HOMBRE40 = o.Persona("S1", "H", 40, 80.0, 180.0, 1.55)   # basal 1730; gasto total 2681,5
MUJER30 = o.Persona("S2", "M", 30, 55.0, 160.0, 1.2)     # basal 1239; gasto total 1486,8
HOMBRE25 = o.Persona("S3", "H", 25, 75.0, 178.0, 1.725)  # basal 1742,5; gasto total 3005,8125
CHICO15 = o.Persona("S4", "H", 15, 60.0, 170.0, 1.6)     # EER IOM 2005 (activo, PA 1,26) = 3137,746


def test_perfiles_domesticos_existen_con_fuentes_y_ambito():
    for k in ("mantenimiento", "control", "volumen", "crecimiento_adolescente"):
        assert P[k].ambito == "hogar" and P[k].fuentes
    assert P["mantenimiento"].semanal_min == {"legumbre": 4, "pescado": 3}
    assert P["mantenimiento"].semanal_max["carne"] == 3 and P["mantenimiento"].semanal_max["huevo"] == 4
    assert P["control"].semanal_min == P["mantenimiento"].semanal_min        # heredado


def test_mantenimiento_es_el_gasto_total():
    obj = objetivos_seguros(HOMBRE40, P["mantenimiento"])
    assert obj.kcal == pytest.approx(2681.5) and not obj.avisos
    assert obj.proteina == pytest.approx((64, 96))


def test_control_deficit_moderado_sin_avisos():
    obj = objetivos_seguros(HOMBRE40, P["control"])
    assert obj.kcal == pytest.approx(2681.5 * 0.85)           # punto medio de −20/−10 %
    assert obj.proteina == pytest.approx((96, 128)) and not obj.avisos


def test_control_no_baja_del_20_por_ciento_aunque_se_pida():
    obj = objetivos_seguros(HOMBRE40, P["control"], ajuste_pct=-30)
    assert obj.kcal == pytest.approx(2681.5 * 0.8) and "déficit máximo" in obj.avisos[0]
    manual = o.Persona(**{**HOMBRE40.__dict__, "kcal_manual": 1500})
    assert objetivos_seguros(manual, P["control"]).kcal == pytest.approx(2145.2)


def test_control_nunca_por_debajo_del_basal():
    obj = objetivos_seguros(MUJER30, P["control"], ajuste_pct=-20)   # 0,8 × 1486,8 = 1189,4 < basal 1239
    assert obj.kcal == pytest.approx(1239) and "basal" in obj.avisos[0]


def test_con_deficit_la_proteina_minima_es_1_2():
    pf = P["control"].copia(proteina_gkg=(1.0, 1.4))
    obj = objetivos_seguros(HOMBRE40, pf)
    assert obj.proteina[0] == pytest.approx(96) and any("1.2 g/kg" in a for a in obj.avisos)


def test_volumen_superavit_y_proteina():
    obj = objetivos_seguros(HOMBRE25, P["volumen"])
    assert obj.kcal == pytest.approx(3005.8125 * 1.10)
    assert obj.proteina == pytest.approx((120, 165))


def test_adolescente_eer_sin_deficit():
    obj = objetivos_seguros(CHICO15, P["crecimiento_adolescente"])
    assert obj.kcal == pytest.approx(3137.746, abs=0.01) and not obj.avisos
    manual = o.Persona(**{**CHICO15.__dict__, "kcal_manual": 2000})
    obj = objetivos_seguros(manual, P["crecimiento_adolescente"])
    assert obj.kcal == pytest.approx(3137.746, abs=0.01) and "menor" in obj.avisos[0]


def test_adolescente_nunca_perfil_de_control():
    with pytest.raises(PerfilNoPermitido):
        objetivos_seguros(CHICO15, P["control"])
    sin_edad = P["control"].copia(edad=None)                    # aunque alguien quite el rango de edad
    with pytest.raises(PerfilNoPermitido, match="déficit"):
        objetivos_seguros(CHICO15, sin_edad)


def test_los_clinicos_no_cambian_con_los_campos_nuevos():
    # kcal_objetivo de v0.1: Mifflin × actividad, sin ajuste
    obj = o.calcular_objetivos(HOMBRE40, P["uax_mediterranea"])
    assert obj.kcal == pytest.approx(2681.5)


@pytest.mark.parametrize("linea, msg", [("ajuste_pct = [-30, -10]", "ajuste_pct"),
                                        ('energia_modo = "harris"', "energia_modo")])
def test_validacion_de_campos_de_energia(tmp_path, linea, msg):
    (tmp_path / "x.toml").write_text(f'nombre="x"\ndescripcion="d"\nfuentes=["f"]\nproteina_gkg=[1,2]\n{linea}\n',
                                     encoding="utf-8")
    with pytest.raises(PerfilInvalido, match=msg):
        cargar_perfiles(tmp_path)
