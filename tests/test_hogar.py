"""T24 · modo hogar en dos etapas (ADR-0005). Hogar y biblioteca SINTÉTICOS."""
from pathlib import Path

import pytest

from nutriuax import base_fdc, composicion as c, hogar as h, recetas as rc

MINI = Path(__file__).resolve().parent / "fixtures" / "biblioteca_mini.json"


@pytest.fixture(scope="module")
def menu_y_datos():
    if base_fdc.cargar_completa() is None:
        pytest.skip("sin data/fdc_completa.csv.gz")
    recs = rc.cargar_recetas(MINI)
    hog = h.Hogar(
        [h.Miembro("SA", "H", 45, 80.0, 178.0, 1.55, "mantenimiento"),
         h.Miembro("SB", "M", 40, 62.0, 165.0, 1.4, "control", alergias={"pescado"}),
         h.Miembro("ST", "H", 15, 58.0, 172.0, 1.6, "crecimiento_adolescente")],
        asistencia={(0, "X"): {"SA", "SB"}})                     # el adolescente no cena en casa el día 1
    menu = h.generar_hogar(hog, recs, c.cargar(), h.Opciones(dias=2, tiempo_etapa1=10, tiempo_etapa2=10))
    return menu, hog, {r.id: r for r in recs}


def test_un_plato_compartido_por_comida(menu_y_datos):
    menu, hog, _ = menu_y_datos
    pr = menu.platos[menu.platos.rol == "principal"]
    assert len(pr) == 4 and not pr.duplicated(["n_dia", "comida"]).any()
    # todas las raciones de una comida apuntan al plato de esa comida
    m = menu.raciones.merge(menu.platos, on=["n_dia", "comida", "rol", "receta"], how="left", indicator=True)
    assert (m["_merge"] == "both").all()


def test_alergias_duras(menu_y_datos):
    menu, hog, recs = menu_y_datos
    tab = c.cargar().tabla
    for p in menu.platos.itertuples():
        presentes = hog.presentes(p.n_dia - 1, p.comida)
        for mb in presentes:
            assert not (recs[p.receta].alergenos & mb.alergias), (p.receta, mb.id)
    sb = menu.complementos[menu.complementos.miembro == "SB"]
    assert not any(tab.at[f, "alergenos_set"] & {"pescado"} for f in sb["id"])
    # la merluza (pescado) no puede aparecer en ninguna comida con SB presente
    assert "mini-merluza-gambas" not in set(menu.platos["receta"])


def test_raciones_en_rango_y_energia(menu_y_datos):
    menu, _, _ = menu_y_datos
    assert menu.raciones["k"].between(0.5, 2.0).all()
    assert (menu.resumen["kcal_desv"].abs() <= 0.10).all(), menu.resumen
    # los suelos están aplicados: control con déficit ≤ 20 % y proteína ≥ 1,2 g/kg
    o_sb = menu.objetivos["SB"]
    assert o_sb.proteina[0] >= 1.2 * 62.0 - 1e-6


def test_ausente_no_recibe_racion(menu_y_datos):
    menu, _, _ = menu_y_datos
    st = menu.raciones[(menu.raciones.miembro == "ST") & (menu.raciones.n_dia == 1) & (menu.raciones.comida == "X")]
    assert st.empty
    stc = menu.complementos[(menu.complementos.miembro == "ST") & (menu.complementos.n_dia == 1)
                            & (menu.complementos.comida == "X")]
    assert stc.empty
    # y su objetivo de ese día se reduce en la fracción de la cena (30 %)
    r = menu.resumen.set_index(["miembro", "n_dia"])
    assert r.at[("ST", 1), "kcal_obj"] == pytest.approx(r.at[("ST", 2), "kcal_obj"] * 0.70, rel=0.01)

