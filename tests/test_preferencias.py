"""T25 · preferencias del hogar como pesos (ADR-0007 §4). Recetas y hogar SINTÉTICOS."""
import json

import pytest

from nutriuax import base_fdc, composicion as c, hogar as h, recetas as rc

BASES = [("pechuga de pollo", "ave"), ("lomos de merluza", "pescado"), ("lentejas", "legumbre"),
         ("huevos", "huevo"), ("carne de ternera", "carne_roja"), ("garbanzos cocidos", "legumbre")]


def receta(i, principal, grupo, veg="calabacin", nevera=3, congelable=False, minutos=30, comidas=("comida", "cena")):
    q, u = (2, "ud") if principal == "huevos" else (150, "g")
    return {"id": f"r{i:02d}", "nombre": f"Plato {i}", "categoria": {"ave": "ave", "pescado": "pescado", "legumbre":
            "legumbre", "huevo": "huevo", "carne_roja": "carne"}[grupo], "comidas": list(comidas), "grupos": [grupo],
            "alergenos": [], "batch": True, "congelable": congelable, "nevera": nevera, "facil": True,
            "minutos": minutos, "ingredientes": [{"n": principal, "q": q, "u": u, "s": "x"},
                                                 {"n": veg, "q": 100, "u": "g", "s": "x"},
                                                 {"n": "patatas", "q": 150, "u": "g", "s": "x"},
                                                 {"n": "aceite de oliva", "q": 10, "u": "ml", "s": "x"}]}


@pytest.fixture(scope="module")
def entorno(tmp_path_factory):
    if base_fdc.cargar_completa() is None:
        pytest.skip("sin data/fdc_completa.csv.gz")
    lib = [receta(i, *BASES[i % len(BASES)], nevera=1 + i % 5, congelable=(i % 4 == 0), minutos=20 + 10 * (i % 5))
           for i in range(24)]
    ruta = tmp_path_factory.mktemp("lib") / "lib.json"
    ruta.write_text(json.dumps(lib), encoding="utf-8")
    recs = rc.cargar_recetas(ruta)
    hog = h.Hogar([h.Miembro("SA", "H", 40, 78.0, 178.0, 1.55, "mantenimiento"),
                   h.Miembro("SB", "M", 38, 60.0, 165.0, 1.45, "mantenimiento")])
    return recs, hog, c.cargar()


def platos(entorno, **op):
    recs, hog, comp = entorno
    base = dict(dias=7, primero_en_comida=False, tiempo_etapa1=20, tiempo_etapa2=10)
    return h.generar_hogar(hog, recs, comp, h.Opciones(**{**base, **op})).platos


def test_baja_valoracion_no_aparece(entorno):
    p = platos(entorno, valoraciones={"r00": 1, "r06": 2, "r01": 5})
    assert not {"r00", "r06"} & set(p.receta)


def test_sin_repetir_receta(entorno):
    p = platos(entorno)
    assert not p.receta.duplicated().any()


def test_batch_lunes_a_viernes_aguanta_en_nevera(entorno):
    recs = {r.id: r for r in entorno[0]}
    p = platos(entorno, batch=True)
    for f in p[p.n_dia <= 5].itertuples():
        r = recs[f.receta]
        assert r.congelable or r.nevera >= f.n_dia, (f.receta, f.n_dia, r.nevera)


def test_tiempo_de_cocina_en_laborables(entorno):
    recs = {r.id: r for r in entorno[0]}
    p = platos(entorno, minutos_max_laborable=30, pesos={"tiempo": 5.0})
    assert all(recs[f.receta].minutos <= 30 for f in p[p.n_dia <= 5].itertuples())


def test_temporada(entorno):
    recs, hog, comp = entorno
    dos = [rc.calcular_receta(receta(90, "pechuga de pollo", "ave", veg="tomate", comidas=("cena",))),
           rc.calcular_receta(receta(91, "pechuga de pollo", "ave", veg="coliflor", comidas=("cena",)))]
    op = dict(dias=1, primero_en_comida=False, tiempo_etapa1=10, tiempo_etapa2=10, pesos={"temporada": 5.0})
    solo_cena = h.Hogar(hog.miembros, asistencia={(0, "C"): set(), (0, "D"): set(), (0, "M"): set()})
    enero = h.generar_hogar(solo_cena, dos, comp, h.Opciones(mes=1, **op)).platos
    julio = h.generar_hogar(solo_cena, dos, comp, h.Opciones(mes=7, **op)).platos
    assert list(enero.receta) == ["r91"] and list(julio.receta) == ["r90"]   # coliflor en enero, tomate en julio
