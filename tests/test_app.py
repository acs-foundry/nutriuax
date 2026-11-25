"""Prueba de humo de la app Streamlit (sin navegador) y de la exportación a Excel."""
import io
from pathlib import Path

import pandas as pd
import pytest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_genera_y_exporta():
    st_testing = pytest.importorskip("streamlit.testing.v1")
    at = st_testing.AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception
    at.sidebar.slider[-1].set_value(2)  # 2 días (último slider = Días)
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert "menu" in at.session_state
    menu = at.session_state["menu"]
    assert set(menu.items["n_dia"]) == {1, 2}


def test_app_anade_alimento_de_base_completa():
    st_testing = pytest.importorskip("streamlit.testing.v1")
    from nutriuax import base_fdc
    if base_fdc.cargar_completa() is None:
        pytest.skip("sin data/fdc_completa.csv.gz")
    at = st_testing.AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.sidebar.slider[-1].set_value(1)
    at.button[0].click().run()
    n0 = len(at.session_state["menu"].items)
    at.text_input(key="q_fdc").set_value("garbanzos cocidos").run()
    assert not at.exception, at.exception
    [b for b in at.button if b.label == "Añadir al menú"][0].click().run()
    assert not at.exception, at.exception
    items = at.session_state["menu"].items
    assert len(items) == n0 + 1
    assert items["id"].iloc[-1].startswith("fdc_")


def test_excel_tiene_hojas():
    from nutriuax import composicion as c, exportar, generador as g, objetivos as o
    comp = c.cargar()
    p = o.Persona(kcal_manual=2000)
    obj = o.calcular_objetivos(p, o.PERFILES["uax_mediterranea"])
    menu = g.generar(comp, obj, dias=1, tiempo_max=15)
    xls = pd.ExcelFile(io.BytesIO(exportar.a_excel(menu, p)))
    assert xls.sheet_names == ["Menú", "Resumen diario", "Comprobación", "Lista de la compra", "Parámetros"]


def _textos(at) -> str:
    partes = []
    for tipo in ("markdown", "title", "caption", "header", "subheader", "info", "warning", "error", "text"):
        for el in getattr(at, tipo, []):
            partes.append(str(getattr(el, "value", "")))
    for sb in at.selectbox:
        partes += [str(o) for o in sb.options]
    return " ".join(partes)


def test_modo_estudio_lleva_marca_uax(monkeypatch):
    st_testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.setenv("NUTRIUAX_MODO", "estudio")
    at = st_testing.AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception
    assert "nuax-hero" in _textos(at)


def test_modo_hogar_neutro_y_sin_textos_clinicos(monkeypatch, tmp_path):
    st_testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.setenv("NUTRIUAX_MODO", "hogar")
    monkeypatch.setenv("NUTRIUAX_RECETAS", str(Path(__file__).resolve().parent / "fixtures" / "biblioteca_mini.json"))
    monkeypatch.setenv("NUTRIUAX_HOGARES", str(tmp_path / "hogares"))
    at = st_testing.AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    t = _textos(at)
    assert "nuax-hero" not in t and "UAX" not in t
    for palabra in ("ERC", "BCAA", "estudio", "hemodiálisis", "diálisis"):
        assert palabra not in t, palabra
    # genera con la mini-biblioteca y los dos miembros de ejemplo
    at.slider(key="h_dias").set_value(1)
    at.button(key="h_generar").click().run()
    assert not at.exception, at.exception
    assert "menu_hogar" in at.session_state


def test_modo_consulta_ofrece_todos_los_perfiles(monkeypatch):
    st_testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.setenv("NUTRIUAX_MODO", "consulta")
    at = st_testing.AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception
    opciones = set(at.sidebar.selectbox[1].options)
    assert {"UAX · Mediterránea normoproteica", "Mantenimiento (adulto)"} <= opciones
    assert "nuax-hero" not in _textos(at)


def test_modo_hogar_carga_el_hogar_por_defecto(monkeypatch, tmp_path):
    st_testing = pytest.importorskip("streamlit.testing.v1")
    from nutriuax import hogares
    monkeypatch.setenv("NUTRIUAX_HOGARES", str(tmp_path / "hogares"))
    hogares.guardar("Familia Sintética", pd.DataFrame([dict(id="sint1", nombre="", sexo="M", edad=33, peso=60.0,
                                                            talla=164.0, actividad=1.5, perfil="mantenimiento",
                                                            alergias="")]))
    monkeypatch.setenv("NUTRIUAX_MODO", "hogar")
    at = st_testing.AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["h_nombre"] == "Familia Sintética"
    assert list(at.session_state["h_tabla"]["id"]) == ["sint1"]

