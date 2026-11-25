"""Interfaz para otros programas (ADR-0007, T27): `generar_menu(entrada: dict) -> dict`.

Entrada y salida siguen `schema/entrada_v1.json` y `schema/salida_v1.json` (versión «1»). Los datos de los
miembros (edad, peso, talla) solo viven en memoria durante la llamada; la salida solo lleva seudónimos.
La CLI (`python -m nutriuax menu …`) llama a esta misma función.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

from . import composicion, equivalencias as eq, hogar as h, recetas as rc
from .objetivos import PERFILES

RAIZ = Path(__file__).resolve().parents[2]
VERSION = "1"
AMBITOS_POR_MODO = {"hogar": {"hogar"}, "consulta": {"hogar", "clinico", "estudio"}, "estudio": {"estudio", "clinico"}}


class EntradaInvalida(ValueError):
    """La entrada no cumple el esquema v1 o pide algo no permitido en su modo."""


def _esquema(nombre: str) -> dict:
    return json.loads((RAIZ / "schema" / nombre).read_text(encoding="utf-8"))


def validar(doc: dict, esquema: str) -> None:
    """Valida contra `schema/<esquema>` (JSON Schema draft-07). Lanza EntradaInvalida con la ruta del error."""
    try:
        import jsonschema
    except ModuleNotFoundError as e:  # pragma: no cover
        raise RuntimeError("Falta la dependencia jsonschema (pip install -r requirements.txt)") from e
    v = jsonschema.Draft7Validator(_esquema(esquema))
    errores = sorted(v.iter_errors(doc), key=lambda e: list(e.path))
    if errores:
        e = errores[0]
        ruta = "/".join(str(p) for p in e.path) or "(raíz)"
        raise EntradaInvalida(f"{esquema}: {ruta}: {e.message}")


def _hogar(entrada: dict, modo: str) -> h.Hogar:
    ambitos = AMBITOS_POR_MODO[modo]
    miembros = []
    for m in entrada["hogar"]["miembros"]:
        if m["perfil"] not in PERFILES:
            raise EntradaInvalida(f"perfil «{m['perfil']}» no existe (disponibles: {', '.join(PERFILES)})")
        if PERFILES[m["perfil"]].ambito not in ambitos:
            raise EntradaInvalida(f"el perfil «{m['perfil']}» no está permitido en modo {modo}")
        miembros.append(h.Miembro(m["id"], m["sexo"], int(m["edad"]), float(m["peso"]), float(m["talla"]),
                                  float(m.get("actividad", 1.55)), m["perfil"], set(m.get("alergias", [])),
                                  set(m.get("vetados", [])), m.get("masa_magra")))
    ids = [m.id for m in miembros]
    if len(set(ids)) != len(ids):
        raise EntradaInvalida("hay ids de miembro repetidos")
    asistencia = {}
    for a in entrada["hogar"].get("asistencia", []):
        desconocidos = set(a["presentes"]) - set(ids)
        if desconocidos:
            raise EntradaInvalida(f"asistencia día {a['dia']} {a['comida']}: miembros desconocidos {sorted(desconocidos)}")
        asistencia[(a["dia"] - 1, a["comida"])] = set(a["presentes"])
    return h.Hogar(miembros, asistencia)


def _compra(menu: h.MenuHogar, recetas: dict[str, rc.Receta]) -> list[dict]:
    acum: dict[tuple[str, str, str], float] = defaultdict(float)
    for r in menu.raciones.itertuples() if len(menu.raciones) else []:
        for i in recetas[r.receta].ingredientes:
            if i.get("alimento") == "nulo":
                continue
            acum[(i.get("s") or "otros", eq.normalizar(i["n"]), i["u"])] += float(i["q"]) * r.k
    for c in menu.complementos.itertuples() if len(menu.complementos) else []:
        acum[("catalogo", c.nombre, "g")] += float(c.gramos)
    return [dict(seccion=s, ingrediente=n, cantidad=round(q, 1), unidad=u) for (s, n, u), q in sorted(acum.items())]


def generar_menu(entrada: dict, recetas_ruta: str | Path | None = None) -> dict:
    """Entrada v1 → salida v1. Valida ambos contra el esquema."""
    validar(entrada, "entrada_v1.json")
    modo = entrada.get("modo", "hogar")
    hogar = _hogar(entrada, modo)
    semana = entrada.get("semana", {})
    inicio = dt.date.fromisoformat(semana["inicio"]) if semana.get("inicio") else None
    pref, opc = entrada.get("preferencias", {}), entrada.get("opciones", {})
    op = h.Opciones(dias=int(semana.get("dias", 7)), k_min=float(opc.get("k_min", 0.5)),
                    k_max=float(opc.get("k_max", 2.0)), primero_en_comida=bool(opc.get("primero_en_comida", True)),
                    semilla=int(opc.get("semilla", 0)), valoraciones=dict(pref.get("valoraciones", {})),
                    batch=bool(pref.get("batch", False)), mes=inicio.month if inicio else None,
                    minutos_max_laborable=int(pref.get("minutos_max_laborable", 45)), pesos=dict(pref.get("pesos", {})))
    recetas = rc.cargar_recetas(recetas_ruta or entrada.get("recetas_ruta"))
    por_id = {r.id: r for r in recetas}
    menu = h.generar_hogar(hogar, recetas, composicion.cargar(), op, rc.cobertura_minima())

    comidas = []
    for d in range(op.dias):
        fecha = (inicio + dt.timedelta(days=d)).isoformat() if inicio else None
        for m in h.COMIDAS_HOGAR:
            pres = [x.id for x in hogar.presentes(d, m)]
            if not pres:
                continue
            pl = []
            for p in menu.platos[(menu.platos.n_dia == d + 1) & (menu.platos.comida == m)].itertuples():
                rr = menu.raciones[(menu.raciones.n_dia == d + 1) & (menu.raciones.comida == m)
                                   & (menu.raciones.rol == p.rol)]
                pl.append(dict(rol=p.rol, receta=p.receta, nombre=p.nombre,
                               raciones={r.miembro: dict(k=float(r.k), gramos_crudo=float(r.gramos_crudo))
                                         for r in rr.itertuples()}))
            cc = menu.complementos[(menu.complementos.n_dia == d + 1) & (menu.complementos.comida == m)] \
                if len(menu.complementos) else menu.complementos
            comp_m = {mid: [dict(alimento=c.id, nombre=c.nombre, gramos=float(c.gramos))
                            for c in cc[cc.miembro == mid].itertuples()] for mid in pres}
            comidas.append(dict(dia=d + 1, fecha=fecha, comida=m, platos=pl, complementos=comp_m))
    nutr = [dict(miembro=r.miembro, dia=int(r.n_dia), kcal=float(r.kcal), kcal_objetivo=float(r.kcal_obj),
                 desviacion_kcal=float(r.kcal_desv), proteina=float(r.proteina), leu=float(r.leu), ile=float(r.ile),
                 val=float(r.val), fibra=float(r.fibra), sodio=float(r.sodio))
            for r in menu.resumen.itertuples()]
    objetivos = {mid: dict(perfil=o.perfil.clave, kcal=round(float(o.kcal), 1),
                           proteina=[round(float(o.proteina[0]), 1), round(float(o.proteina[1]), 1)])
                 for mid, o in menu.objetivos.items()}
    salida = dict(version=VERSION, modo=modo, semana=dict(inicio=semana.get("inicio"), dias=op.dias), menu=comidas,
                  nutrientes=nutr, objetivos=objetivos, compra=_compra(menu, por_id), avisos=list(menu.avisos))
    validar(salida, "salida_v1.json")
    return salida
