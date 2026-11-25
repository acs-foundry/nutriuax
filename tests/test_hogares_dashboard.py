"""T31-T32 · hogares guardados en local e intercambio con el dashboard Menú Familiar. Datos SINTÉTICOS."""
import datetime as dt
import json
import os
import stat

import pandas as pd
import pytest

from nutriuax import dashboard, hogares


@pytest.fixture(autouse=True)
def dir_hogares(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRIUAX_HOGARES", str(tmp_path / "hogares"))
    return tmp_path / "hogares"


HOGAR = pd.DataFrame([
    dict(id="papa", nombre="Papá", sexo="H", edad=50, peso=80.0, talla=178.0, actividad=1.5, perfil="mantenimiento",
         alergias=""),
    dict(id="hijo", nombre="Hijo", sexo="H", edad=15, peso=58.0, talla=172.0, actividad=1.7,
         perfil="crecimiento_adolescente", alergias="crustaceos"),
])


def test_guardar_cargar_y_por_defecto(dir_hogares):
    ruta = hogares.guardar("Familia Sintética", HOGAR)
    assert ruta.parent == dir_hogares and ruta.name == "familia-sintetica.json"
    assert stat.S_IMODE(os.stat(ruta).st_mode) == 0o600                 # solo el usuario
    assert hogares.listar() == ["Familia Sintética"] and hogares.por_defecto() == "Familia Sintética"
    df = hogares.cargar("Familia Sintética")
    assert list(df.id) == ["papa", "hijo"] and df.loc[1, "peso"] == 58.0


def test_importar_del_dashboard_conserva_peso_y_talla():
    doc = {"formato": "menu-familiar→nutriuax", "version": 1,
           "miembros": [{"id": "papa", "nombre": "Papá", "edad": "50 años", "objetivo": "control", "factor": 1.2,
                         "alergias": ["lacteos"]},
                        {"id": "nuevo", "nombre": "Abuela", "edad": "76", "objetivo": "mantenimiento", "alergias": []}],
           "valoraciones": {"imp-lentejas-estofadas": 4.5, "r-x": 1.5}}
    df, vals = dashboard.importar(doc, HOGAR)
    p = df.set_index("id")
    assert p.at["papa", "peso"] == 80.0 and p.at["papa", "perfil"] == "control" and p.at["papa", "alergias"] == "leche"
    assert p.at["nuevo", "edad"] == 76 and pd.isna(p.at["nuevo", "peso"])  # el dashboard no trae peso: se completa aquí
    assert vals == {"imp-lentejas-estofadas": 4.5, "r-x": 1.5}
    with pytest.raises(dashboard.FormatoInvalido):
        dashboard.importar({"formato": "otro", "version": 1})


def test_exportar_al_dashboard():
    class M:  # MenuHogar mínimo
        platos = pd.DataFrame([dict(n_dia=1, comida="C", rol="principal", receta="r-lentejas", nombre="Lentejas"),
                               dict(n_dia=1, comida="C", rol="primero", receta="r-ensalada", nombre="Ensalada"),
                               dict(n_dia=2, comida="X", rol="principal", receta="r-merluza", nombre="Merluza")])
        raciones = pd.DataFrame([dict(miembro="papa", n_dia=1, comida="C", rol="principal", k=1.2),
                                 dict(miembro="hijo", n_dia=1, comida="C", rol="principal", k=1.5),
                                 dict(miembro="papa", n_dia=2, comida="X", rol="principal", k=1.0)])
    out = dashboard.exportar(M, dt.date(2026, 11, 2))
    assert out["formato"] == "nutriuax→menu-familiar" and out["semana"] == "2026-11-02"
    c = out["menu"]["2026-11-02"]["comida"]
    assert c["receta"] == "r-lentejas" and c["quien"] == ["hijo", "papa"]
    assert "papa ×1,20" in c["nota"] and "Ensalada" in c["nota"]
    assert out["menu"]["2026-11-03"]["cena"]["quien"] == ["papa"]
    json.dumps(out)                                                      # serializable
