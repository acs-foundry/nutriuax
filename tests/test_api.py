"""T27 · contrato JSON v1, función pública y CLI (ADR-0007). Datos SINTÉTICOS."""
import copy
import json
from pathlib import Path

import pytest

from nutriuax import api, base_fdc
from nutriuax.__main__ import main as cli

RAIZ = Path(__file__).resolve().parents[1]
MINI = RAIZ / "tests" / "fixtures" / "biblioteca_mini.json"
EJEMPLO = json.loads((RAIZ / "docs" / "ejemplos" / "entrada_hogar_sintetico.json").read_text(encoding="utf-8"))


def entrada_pequena():
    e = copy.deepcopy(EJEMPLO)
    e["semana"]["dias"] = 2
    e["hogar"]["miembros"] = [m for m in e["hogar"]["miembros"] if m["id"] in ("adulto1", "adulto3", "adolescente1")]
    e["hogar"]["asistencia"] = [{"dia": 1, "comida": "X", "presentes": ["adulto1", "adulto3"]}]
    e["preferencias"]["batch"] = False
    return e


@pytest.fixture(scope="module")
def salida():
    if base_fdc.cargar_completa() is None:
        pytest.skip("sin data/fdc_completa.csv.gz")
    return api.generar_menu(entrada_pequena(), MINI)


def test_ejemplo_de_entrada_valida():
    api.validar(EJEMPLO, "entrada_v1.json")


def test_salida_valida_contra_esquema(salida):
    api.validar(salida, "salida_v1.json")
    assert salida["version"] == "1" and salida["semana"] == {"inicio": "2026-11-02", "dias": 2}
    assert {n["miembro"] for n in salida["nutrientes"]} == {"adulto1", "adulto3", "adolescente1"}
    assert all(abs(n["desviacion_kcal"]) <= 0.10 for n in salida["nutrientes"])
    assert salida["compra"] and all(c["cantidad"] > 0 for c in salida["compra"])


def test_salida_sin_datos_de_salud(salida):
    texto = json.dumps(salida)
    for clave in ('"peso"', '"talla"', '"edad"', '"sexo"', '"alergias"'):
        assert clave not in texto


def test_alergia_respetada_en_salida(salida):
    # adulto3 es alérgico a crustáceos: la merluza con gambas no puede servírsele
    for c in salida["menu"]:
        for p in c["platos"]:
            if "adulto3" in p["raciones"]:
                assert p["receta"] != "mini-merluza-gambas"


@pytest.mark.parametrize("cambio, mensaje", [
    (lambda e: e.update(version="2"), "version"),
    (lambda e: e["hogar"]["miembros"][0].update(perfil="erc_nd"), "no está permitido en modo hogar"),
    (lambda e: e["hogar"]["miembros"][0].update(perfil="no_existe"), "no existe"),
    (lambda e: e["hogar"]["asistencia"].append({"dia": 2, "comida": "C", "presentes": ["fantasma"]}), "desconocidos"),
    (lambda e: e["hogar"]["miembros"][0].update(alergias=["marisco"]), "alergias"),
    (lambda e: e.update(extra=1), "Additional properties"),
])
def test_entradas_invalidas(cambio, mensaje):
    e = entrada_pequena()
    cambio(e)
    with pytest.raises(api.EntradaInvalida, match=mensaje):
        api.generar_menu(e, MINI)


def test_cli_igual_que_funcion(salida, tmp_path):
    ent = tmp_path / "entrada.json"
    sal = tmp_path / "salida.json"
    ent.write_text(json.dumps(entrada_pequena()), encoding="utf-8")
    assert cli(["menu", "--entrada", str(ent), "--salida", str(sal), "--recetas", str(MINI)]) == 0
    assert json.loads(sal.read_text(encoding="utf-8")) == salida


def test_cli_error_claro(tmp_path, capsys):
    ent = tmp_path / "mal.json"
    ent.write_text(json.dumps({"version": "9"}), encoding="utf-8")
    assert cli(["menu", "--entrada", str(ent), "--recetas", str(MINI)]) == 2
    assert "Error" in capsys.readouterr().err
