"""Intercambio con el dashboard «Menú Familiar» (artifact de claude.ai) por JSON copiado y pegado (T32).

- Del dashboard a NutriUAX («Exportar al planificador»): `{"formato": "menu-familiar→nutriuax", "version": 1,
  "miembros": [{id, nombre, edad, objetivo, factor, alergias}], "valoraciones": {receta: media}}`. NutriUAX une los
  miembros con el hogar local (peso, talla y actividad solo viven aquí) y usa las valoraciones como preferencia.
- De NutriUAX al dashboard («Importar del planificador»): `{"formato": "nutriuax→menu-familiar", "version": 1,
  "menu": {fecha: {"comida": {receta, quien, nota}, "cena": {…}}}}`. El dashboard escribe solo comida y cena de esas
  fechas; desayuno y merienda no se tocan. La nota lleva las raciones por persona (k × ración de adulto).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

FORMATO_ENTRADA = "menu-familiar→nutriuax"
FORMATO_SALIDA = "nutriuax→menu-familiar"
# alérgenos del dashboard → UE-14 de NutriUAX (solo cambia «lacteos»)
ALERGENO = {"lacteos": "leche"}
OBJETIVO = {"mantenimiento": "mantenimiento", "control": "control", "volumen": "volumen",
            "crecimiento": "crecimiento_adolescente"}
COMIDA = {"C": "comida", "X": "cena"}


class FormatoInvalido(ValueError):
    pass


def importar(doc: dict, hogar: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict[str, float]]:
    """Une los miembros del dashboard con el hogar local. Devuelve (miembros, valoraciones).
    De cada miembro se toman id, nombre, perfil (objetivo) y alergias; sexo, edad, peso, talla y actividad se
    conservan del hogar local si ya existe ese id (el dashboard no los tiene o los tiene como texto)."""
    if doc.get("formato") != FORMATO_ENTRADA or doc.get("version") != 1:
        raise FormatoInvalido("No es un JSON «Exportar al planificador» del dashboard (formato o versión)")
    local = {} if hogar is None else {str(r["id"]): r for r in hogar.to_dict("records")}
    filas = []
    for m in doc.get("miembros", []):
        mid = str(m.get("id", "")).strip()
        if not mid:
            continue
        previo = local.get(mid, {})
        edad = previo.get("edad")
        if edad in (None, "") or (isinstance(edad, float) and pd.isna(edad)):
            digitos = "".join(ch for ch in str(m.get("edad", "")) if ch.isdigit())
            edad = int(digitos) if digitos else None
        filas.append(dict(
            id=mid, nombre=m.get("nombre", mid), sexo=previo.get("sexo") or "",
            edad=edad, peso=previo.get("peso"), talla=previo.get("talla"),
            actividad=previo.get("actividad") or 1.55,
            perfil=OBJETIVO.get(m.get("objetivo", ""), previo.get("perfil") or "mantenimiento"),
            alergias=";".join(sorted(ALERGENO.get(a, a) for a in m.get("alergias", []) or []))))
    vals = {str(k): float(v) for k, v in (doc.get("valoraciones") or {}).items() if v}
    return pd.DataFrame(filas), vals


def exportar(menu, inicio: dt.date) -> dict:
    """MenuHogar → JSON para «Importar del planificador» del dashboard (solo comida y cena)."""
    dias: dict[str, dict] = {}
    for p in menu.platos[menu.platos.rol == "principal"].itertuples():
        fecha = (inicio + dt.timedelta(days=int(p.n_dia) - 1)).isoformat()
        rac = menu.raciones[(menu.raciones.n_dia == p.n_dia) & (menu.raciones.comida == p.comida)
                            & (menu.raciones.rol == "principal")]
        primero = menu.platos[(menu.platos.n_dia == p.n_dia) & (menu.platos.comida == p.comida)
                              & (menu.platos.rol == "primero")]
        nota = "Planificador · raciones: " + ", ".join(f"{r.miembro} ×{r.k:.2f}".replace(".", ",") for r in rac.itertuples())
        if len(primero):
            nota += f" · de primero: {primero.nombre.iloc[0]}"
        dias.setdefault(fecha, {})[COMIDA[p.comida]] = dict(receta=p.receta, quien=sorted(rac.miembro.tolist()),
                                                             nota=nota)
    return {"formato": FORMATO_SALIDA, "version": 1, "semana": inicio.isoformat(), "menu": dias}
