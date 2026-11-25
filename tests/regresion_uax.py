"""Casos de la referencia del estudio UAX (T19). Persona SINTÉTICA; instancias que el solver resuelve al óptimo
(gap 2 %) muy por debajo del límite de tiempo, para que el resultado no dependa de la velocidad del equipo."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pandas as pd

from nutriuax import composicion as c, generador as g, objetivos as o

DIR = Path(__file__).resolve().parent / "regresion"
PERSONA = dict(codigo="SINT01", sexo="H", edad=23, peso=75.0, talla=178.0, factor_actividad=1.6)
CASOS = [
    dict(nombre="uax_mediterranea_1d", perfil="uax_mediterranea", dias=1, semilla=0, tiempo_max=60),
    dict(nombre="uax_hiperproteica_2d", perfil="uax_hiperproteica", dias=2, semilla=0, tiempo_max=60),
]
COLS = ["n_dia", "cod_comida", "id", "gramos"]


def generar_caso(caso: dict) -> pd.DataFrame:
    obj = o.calcular_objetivos(o.Persona(**PERSONA), o.PERFILES[caso["perfil"]])
    menu = g.generar(c.cargar(), obj, dias=caso["dias"], semilla=caso["semilla"], tiempo_max=caso["tiempo_max"])
    return menu.items[COLS].reset_index(drop=True)


def perfiles_como_dict() -> dict:
    def limpio(v):
        if isinstance(v, (set, frozenset)):
            return sorted(v)
        if isinstance(v, tuple):
            return list(v)
        if isinstance(v, dict):
            return {k: limpio(x) for k, x in sorted(v.items())}
        if isinstance(v, list):
            return [limpio(x) for x in v]
        return v
    claves = ["uax_mediterranea", "uax_hiperproteica", "erc_nd", "erc_hd", "bcaa_intervencion"]
    return {k: {campo: limpio(v) for campo, v in asdict(o.PERFILES[k]).items()} for k in claves}
