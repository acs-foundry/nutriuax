"""T20 · perfiles como datos (ADR-0004): carga, herencia y validación."""
from pathlib import Path

import pytest

from nutriuax import objetivos as o
from nutriuax.perfiles import PerfilInvalido, cargar_perfiles

BASE = 'nombre = "Base"\ndescripcion = "d"\nfuentes = ["f"]\nproteina_gkg = [1.0, 1.2]\n'


def escribir(d: Path, **ficheros: str) -> Path:
    for nombre, texto in ficheros.items():
        (d / f"{nombre}.toml").write_text(texto, encoding="utf-8")
    return d


def test_los_cinco_clinicos_salen_de_toml_en_su_orden():
    assert list(o.PERFILES)[:5] == ["uax_mediterranea", "uax_hiperproteica", "erc_nd", "erc_hd", "bcaa_intervencion"]
    for p in o.PERFILES.values():
        assert p.fuentes, p.clave
    # mínimos OMS heredados por defecto y sobrescritos en BCAA
    assert o.PERFILES["uax_mediterranea"].aa_min_mgkg["lys"] == 30.0
    assert o.PERFILES["bcaa_intervencion"].aa_min_mgkg["leu"] == 70.0
    assert o.PERFILES["bcaa_intervencion"].aa_min_mgkg["his"] == 10.0


def test_herencia_sobrescribe_y_fusiona(tmp_path):
    escribir(tmp_path,
             padre=BASE + 'grasa_pct = [20, 30]\n[semanal_min]\npescado = 3\nlegumbre = 4\n',
             hijo='parte_de = "padre"\nnombre = "Hijo"\nproteina_gkg = [1.6, 2.2]\n[semanal_min]\npescado = 2\n')
    p = cargar_perfiles(tmp_path)
    h = p["hijo"]
    assert h.nombre == "Hijo" and h.descripcion == "d" and h.fuentes == ("f",)
    assert h.proteina_gkg == (1.6, 2.2) and h.grasa_pct == (20, 30)
    assert h.semanal_min == {"pescado": 2, "legumbre": 4}
    assert p["padre"].semanal_min == {"pescado": 3, "legumbre": 4}   # el padre no se modifica


@pytest.mark.parametrize("texto, mensaje", [
    (BASE + "proteina_kg = [1, 2]\n", "desconocido"),
    (BASE.replace("[1.0, 1.2]", "[1.4, 1.2]"), "invertido"),
    (BASE.replace('fuentes = ["f"]\n', ""), "fuentes"),
    (BASE + 'ambito = "gimnasio"\n', "ambito"),
    (BASE + 'comidas = ["D", "Z"]\n', "comidas"),
    (BASE + 'parte_de = "no_existe"\n', "no existe"),
    (BASE + "proteina_gkg = [1, \n", "mal formado"),
])
def test_validacion_dice_fichero_y_motivo(tmp_path, texto, mensaje):
    escribir(tmp_path, malo=texto)
    with pytest.raises(PerfilInvalido) as e:
        cargar_perfiles(tmp_path)
    assert str(e.value).startswith("malo.toml") and mensaje in str(e.value)


def test_ciclo_en_parte_de(tmp_path):
    escribir(tmp_path, a=BASE + 'parte_de = "b"\n', b=BASE + 'parte_de = "a"\n')
    with pytest.raises(PerfilInvalido, match="ciclo"):
        cargar_perfiles(tmp_path)
