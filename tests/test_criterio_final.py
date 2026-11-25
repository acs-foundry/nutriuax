"""T29 · criterio de éxito final del generador flexible de hogares.

Hogar SINTÉTICO (2 mantenimiento, 1 control con alergia, 1 volumen, 1 adolescente) + biblioteca real del Menú
Familiar (ruta de config/fuentes.toml) → CLI → semana. Se salta si la biblioteca no está en este equipo.
El menú UAX de referencia lo comprueba tests/test_regresion_uax.py en la misma batería.
"""
import json
import time
from pathlib import Path

import pytest

from nutriuax import base_fdc, recetas as rc
from nutriuax.__main__ import main as cli
from nutriuax.objetivos import PERFILES, Persona, gasto_total, tmb_mifflin

RAIZ = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ / "docs" / "ejemplos" / "entrada_hogar_sintetico.json"


@pytest.fixture(scope="module")
def resultado(tmp_path_factory):
    if base_fdc.cargar_completa() is None or not rc.ruta_biblioteca().exists():
        pytest.skip("sin base FDC completa o sin la biblioteca del Menú Familiar en este equipo")
    sal = tmp_path_factory.mktemp("final") / "menu.json"
    t0 = time.perf_counter()
    assert cli(["menu", "--entrada", str(ENTRADA), "--salida", str(sal)]) == 0
    segundos = time.perf_counter() - t0
    return json.loads(ENTRADA.read_text(encoding="utf-8")), json.loads(sal.read_text(encoding="utf-8")), segundos


def test_semana_completa_con_platos_compartidos(resultado):
    ent, sal, _ = resultado
    assert sal["semana"]["dias"] == 7
    comidas_con_plato = [c for c in sal["menu"] if c["comida"] in ("C", "X")]
    assert len(comidas_con_plato) == 14
    for c in comidas_con_plato:
        principales = [p for p in c["platos"] if p["rol"] == "principal"]
        assert len(principales) == 1                                  # un plato principal compartido
        presentes = set(c["complementos"])
        assert set(principales[0]["raciones"]) == presentes           # todos los presentes, cada uno con su ración


def test_energia_de_cada_miembro_dentro_de_10_por_ciento(resultado):
    _, sal, _ = resultado
    malos = [n for n in sal["nutrientes"] if abs(n["desviacion_kcal"]) > 0.10]
    assert not malos, malos


def test_ninguna_alergia_violada(resultado):
    ent, sal, _ = resultado
    alergias = {m["id"]: set(m.get("alergias", [])) for m in ent["hogar"]["miembros"]}
    recs = {r.id: r for r in rc.cargar_recetas()}
    for c in sal["menu"]:
        for p in c["platos"]:
            for mid in p["raciones"]:
                assert not (recs[p["receta"]].alergenos & alergias[mid]), (p["receta"], mid)


def test_suelos_de_seguridad(resultado):
    ent, sal, _ = resultado
    for m in ent["hogar"]["miembros"]:
        per = Persona(m["id"], m["sexo"], m["edad"], m["peso"], m["talla"], m.get("actividad", 1.55))
        o = sal["objetivos"][m["id"]]
        get = gasto_total(per, PERFILES[m["perfil"]])
        if m["edad"] < 18:
            assert o["kcal"] >= get - 1                                # sin déficit
        else:
            assert o["kcal"] >= max(tmb_mifflin(per), 0.8 * get) - 1  # ≥ basal y déficit ≤ 20 %
        if o["kcal"] < get - 1:
            assert o["proteina"][0] >= 1.2 * m["peso"] - 0.1


def test_menos_de_60_segundos(resultado):
    assert resultado[2] < 60, f"{resultado[2]:.1f} s"
