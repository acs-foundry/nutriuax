"""Generador de menús semanales por programación lineal entera mixta (PuLP + HiGHS).

Modelo (ADR-0002):
- Variables: gramos x[d,m,f] y elección binaria y[d,m,f] de cada alimento f en la comida m del día d.
- Duras: porción mín./máx. por alimento si se elige, estructura de cada comida (plantillas), alimentos
  vetados, máximo de veces por semana y una vez por día (salvo AOVE, pan y lácteos).
- Blandas (con holgura penalizada, para que siempre haya solución): energía, proteína (g y % kcal),
  % grasa y HC, AGS, fibra, aminoácidos (mín./máx.), sodio, potasio, fósforo, AOVE, raciones de fruta y
  verdura, reparto por comidas y frecuencias semanales por etiqueta.
- Objetivo: minimizar desviaciones relativas ponderadas + un pequeño coste aleatorio (semilla) que da
  variedad y permite «regenerar».
"""
from __future__ import annotations

import random
from dataclasses import dataclass

import pandas as pd
import pulp

from .composicion import AMINOACIDOS, NUTRIENTES, Composicion
from .objetivos import DIAS, GRUPOS, NOMBRE_COMIDA, PLANTILLAS, REPARTO, Objetivos

PESOS = dict(kcal=10.0, proteina=10.0, macro_pct=4.0, aa=6.0, mineral=5.0, fibra=3.0, aove=3.0,
             raciones=2.0, reparto=1.0, semanal=3.0, variedad=0.4, plantilla=500.0, racion=0.6)
REPETIBLES = {"aove", "pan", "lacteo"}
# tope de gramos por rol y comida (p. ej. AOVE en el desayuno, fruta en un tentempié)
TOPE_COMIDA = {"grasa": {"D": 15, "MM": 20, "M": 20}, "fruta": {"MM": 220, "M": 220}}


@dataclass
class Menu:
    items: pd.DataFrame       # dia, comida, id, nombre, gramos + nutrientes
    resumen: pd.DataFrame     # por día: nutrientes y objetivos
    estado: str               # estado del solver
    objetivos: Objetivos
    fuente: str


def _redondear(g: float, paso: float = 5.0) -> float:
    return max(paso, round(g / paso) * paso)


def generar(comp: Composicion, obj: Objetivos, dias: int = 7, semilla: int = 0,
            vetados: set[str] | None = None, tiempo_max: int = 25, escala_porciones: float | None = None,
            ) -> Menu:
    perfil = obj.perfil
    tab = comp.tabla
    vetados = set(vetados or ())
    rng = random.Random(semilla)
    comidas = [m for m in perfil.comidas if m in PLANTILLAS]
    dias_idx = list(range(dias))
    # porciones escaladas a la energía (una persona de 3000 kcal no come raciones de 1800)
    esc = escala_porciones or min(1.7, max(0.75, obj.kcal / 2000.0))

    elegibles = {
        m: [f for f in tab.index
            if m in tab.at[f, "comidas_set"] and f not in vetados
            and not (tab.at[f, "etiquetas_set"] & perfil.excluir_etiquetas)
            and not (tab.at[f, "rol"] == "suplemento" and "suplemento" in perfil.excluir_etiquetas)]
        for m in comidas
    }
    claves = [(d, m, f) for d in dias_idx for m in comidas for f in elegibles[m]]

    prob = pulp.LpProblem("menu", pulp.LpMinimize)
    x = {k: prob.add_variable(f"x_{k[0]}_{k[1]}_{k[2]}", lowBound=0) for k in claves}
    y = {k: prob.add_variable(f"y_{k[0]}_{k[1]}_{k[2]}", cat="Binary") for k in claves}
    coste = []
    holg_id = [0]

    def holgura(nombre: str) -> pulp.LpVariable:
        holg_id[0] += 1
        return prob.add_variable(f"s{holg_id[0]}_{nombre}", lowBound=0)

    def suma_nutr(d, n, m=None):
        return pulp.lpSum(x[(d, mm, f)] * comp.nutr(f, n) / 100.0
                          for mm in ([m] if m else comidas) for f in elegibles[mm])

    # margen interno: el optimizador apunta un poco dentro del rango para que el redondeo de las
    # porciones a 5 g no saque el menú final del rango
    MG = 0.015

    def blando_min(expr, lim, peso, nombre):
        s = holgura(nombre)
        prob.addConstraint(expr + s >= lim * (1 + MG))
        coste.append(peso * 100.0 / max(lim, 1e-6) * s)

    def blando_max(expr, lim, peso, nombre):
        s = holgura(nombre)
        prob.addConstraint(expr - s <= lim * (1 - MG))
        coste.append(peso * 100.0 / max(lim, 1e-6) * s)

    # --- duras por alimento
    for (d, m, f) in claves:
        es_grasa = tab.at[f, "rol"] == "grasa"
        lo = float(tab.at[f, "min_g"]) * (1.0 if es_grasa else esc)
        hi = float(tab.at[f, "max_g"]) * (1.0 if es_grasa else esc)
        if m in TOPE_COMIDA.get(tab.at[f, "rol"], {}):
            hi = min(hi, TOPE_COMIDA[tab.at[f, "rol"]][m])
        lo = min(lo, hi)
        prob.addConstraint(x[(d, m, f)] >= lo * y[(d, m, f)])
        prob.addConstraint(x[(d, m, f)] <= hi * y[(d, m, f)])
        coste.append(PESOS["variedad"] * rng.random() * y[(d, m, f)])
        # preferencia por la ración habitual: penaliza |x − ración·y| en proporción a la ración
        rac = min(hi, max(lo, float(tab.at[f, "porcion_g"]) * (1.0 if es_grasa else esc)))
        dv = holgura("rac")
        prob.addConstraint(x[(d, m, f)] - rac * y[(d, m, f)] <= dv)
        prob.addConstraint(rac * y[(d, m, f)] - x[(d, m, f)] <= dv)
        coste.append(PESOS["racion"] / rac * dv)

    for f in tab.index:
        ks = [k for k in claves if k[2] == f]
        if not ks:
            continue
        maxs = int(tab.at[f, "max_semana"])
        maxs = max(1, round(maxs * dias / 7))
        prob.addConstraint(pulp.lpSum(y[k] for k in ks) <= maxs)
        if not (tab.at[f, "etiquetas_set"] & REPETIBLES):
            for d in dias_idx:
                kd = [k for k in ks if k[0] == d]
                if len(kd) > 1:
                    prob.addConstraint(pulp.lpSum(y[k] for k in kd) <= 1)

    # --- plantillas de comida
    for d in dias_idx:
        for m in comidas:
            for grupo, (gmin, gmax) in PLANTILLAS[m].items():
                roles = GRUPOS[grupo]
                fs = [f for f in elegibles[m] if roles is None or tab.at[f, "rol"] in roles]
                expr = pulp.lpSum(y[(d, m, f)] for f in fs)
                if gmin > 0:  # mínimo blando muy penalizado: con muchos vetos el modelo sigue teniendo solución
                    s = holgura("plant")
                    prob.addConstraint(expr + s >= gmin)
                    coste.append(PESOS["plantilla"] * s)
                prob.addConstraint(expr <= gmax)

    # --- objetivos diarios
    E = obj.kcal
    for d in dias_idx:
        kc = suma_nutr(d, "kcal")
        sp, sn = holgura("kcal_p"), holgura("kcal_n")
        prob.addConstraint(kc - E == sp - sn)
        coste.append(PESOS["kcal"] * 100.0 / E * (sp + sn))

        prot = suma_nutr(d, "proteina")
        blando_min(prot, obj.proteina[0], PESOS["proteina"], f"pmin{d}")
        blando_max(prot, obj.proteina[1], PESOS["proteina"], f"pmax{d}")
        if obj.proteina_pct_min:
            s = holgura(f"ppct{d}")
            prob.addConstraint(4 * prot + s >= (obj.proteina_pct_min + 0.5) / 100.0 * kc)
            coste.append(PESOS["proteina"] * 100.0 / E * s)

        gr, hc = suma_nutr(d, "grasa"), suma_nutr(d, "hc")
        for expr, (lo, hi), nom in ((9 * gr, obj.grasa_pct, "grasa"), (4 * hc, obj.hc_pct, "hc")):
            s1, s2 = holgura(nom + "lo"), holgura(nom + "hi")
            prob.addConstraint(expr + s1 >= (lo + 0.7) / 100.0 * kc)
            prob.addConstraint(expr - s2 <= (hi - 0.7) / 100.0 * kc)
            coste.append(PESOS["macro_pct"] * 100.0 / E * (s1 + s2))
        if obj.agsat_pct_max:
            s = holgura("ags")
            prob.addConstraint(9 * suma_nutr(d, "agsat") - s <= (obj.agsat_pct_max - 0.5) / 100.0 * kc)
            coste.append(PESOS["macro_pct"] * 100.0 / E * s)

        for n, lim in obj.minimos.items():
            peso = PESOS["aa"] if n in AMINOACIDOS else PESOS["fibra"]
            blando_min(suma_nutr(d, n), lim, peso, f"min_{n}{d}")
        for n, lim in obj.maximos.items():
            peso = PESOS["aa"] if n in AMINOACIDOS else PESOS["mineral"]
            blando_max(suma_nutr(d, n), lim, peso, f"max_{n}{d}")

        if perfil.aove_min_g:
            aove = pulp.lpSum(x[(d, m, f)] for m in comidas for f in elegibles[m]
                              if "aove" in tab.at[f, "etiquetas_set"])
            blando_min(aove, perfil.aove_min_g, PESOS["aove"], f"aove{d}")
        for rol, nmin in (("fruta", perfil.fruta_min_dia), ("verdura", perfil.verdura_min_dia)):
            if nmin:
                cnt = pulp.lpSum(y[(d, m, f)] for m in comidas for f in elegibles[m] if tab.at[f, "rol"] == rol)
                s = holgura(f"rac_{rol}")
                prob.addConstraint(cnt + s >= nmin)
                coste.append(PESOS["raciones"] * 10 * s)

        presentes = sum(REPARTO[m][0] for m in comidas)
        for m in comidas:
            lo, hi = REPARTO[m]
            lo, hi = lo / presentes, min(0.5, hi / presentes)
            km = suma_nutr(d, "kcal", m)
            s1, s2 = holgura("rep"), holgura("rep")
            prob.addConstraint(km + s1 >= lo * E)
            prob.addConstraint(km - s2 <= hi * E)
            coste.append(PESOS["reparto"] * 100.0 / E * (s1 + s2))

    # --- frecuencias semanales por etiqueta (prorrateadas si < 7 días)
    for et, n in perfil.semanal_min.items():
        cnt = pulp.lpSum(y[k] for k in claves if et in tab.at[k[2], "etiquetas_set"])
        s = holgura("sem")
        prob.addConstraint(cnt + s >= round(n * dias / 7))
        coste.append(PESOS["semanal"] * 10 * s)
    for et, n in perfil.semanal_max.items():
        cnt = pulp.lpSum(y[k] for k in claves if et in tab.at[k[2], "etiquetas_set"])
        s = holgura("sem")
        prob.addConstraint(cnt - s <= round(n * dias / 7))
        coste.append(PESOS["semanal"] * 10 * s)

    prob.setObjective(pulp.lpSum(coste))
    solver = pulp.HiGHS(msg=False, timeLimit=tiempo_max, gapRel=0.02)
    prob.solve(solver)
    estado = pulp.LpStatus[prob.status]

    filas = []
    for (d, m, f) in claves:
        if (y[(d, m, f)].value() or 0) > 0.5 and (x[(d, m, f)].value() or 0) > 0.5:
            filas.append(dict(dia=DIAS[d % 7], n_dia=d + 1, comida=NOMBRE_COMIDA[m], cod_comida=m, id=f,
                              nombre=tab.at[f, "nombre"], gramos=_redondear(x[(d, m, f)].value())))
    if not filas:
        raise RuntimeError(f"El optimizador no devolvió menú (estado: {estado}).")
    items = pd.DataFrame(filas)
    orden = {m: i for i, m in enumerate(PLANTILLAS)}
    items = items.sort_values(["n_dia", "cod_comida"], key=lambda s: s.map(orden) if s.name == "cod_comida" else s)
    return evaluar(comp, obj, items.reset_index(drop=True), estado)


def evaluar(comp: Composicion, obj: Objetivos, items: pd.DataFrame, estado: str = "manual") -> Menu:
    """Recalcula nutrientes (p. ej. tras editar el menú a mano) y el resumen diario frente a objetivos."""
    calc = comp.calcular(items[[c for c in items.columns if c not in NUTRIENTES]])
    cols = NUTRIENTES + ["proteina_animal", "proteina_vegetal"]
    res = calc.groupby("n_dia", sort=True)[cols].sum()
    res.insert(0, "dia", calc.groupby("n_dia")["dia"].first())
    res["proteina_gkg"] = res["proteina"] / obj.peso
    res["pct_proteina"] = 400 * res["proteina"] / res["kcal"]
    res["pct_grasa"] = 900 * res["grasa"] / res["kcal"]
    res["pct_hc"] = 400 * res["hc"] / res["kcal"]
    res["bcaa_mg"] = res["leu"] + res["ile"] + res["val"]
    for a in ("leu", "ile", "val"):
        res[f"{a}_mgkg"] = res[a] / obj.kg_referencia
    return Menu(calc, res.reset_index(), estado, obj, comp.fuente)


def comprobar(menu: Menu, tolerancia_kcal: float = 0.10) -> pd.DataFrame:
    """Tabla día × criterio con OK/fuera de rango, para la app y la exportación."""
    o = menu.objetivos
    filas = []
    for r in menu.resumen.itertuples():
        def fila(criterio, valor, lo=None, hi=None, unidad=""):
            ok = (lo is None or valor >= lo * 0.999) and (hi is None or valor <= hi * 1.001)
            filas.append(dict(n_dia=r.n_dia, dia=r.dia, criterio=criterio, valor=round(valor, 1),
                              minimo=None if lo is None else round(lo, 1),
                              maximo=None if hi is None else round(hi, 1), unidad=unidad, ok=ok))
        fila("Energía", r.kcal, o.kcal * (1 - tolerancia_kcal), o.kcal * (1 + tolerancia_kcal), "kcal")
        fila("Proteína", r.proteina, o.proteina[0], o.proteina[1], "g")
        if o.proteina_pct_min:
            fila("Proteína % energía", r.pct_proteina, o.proteina_pct_min, None, "%")
        fila("Grasa % energía", r.pct_grasa, *o.grasa_pct, unidad="%")
        fila("HC % energía", r.pct_hc, *o.hc_pct, unidad="%")
        if o.agsat_pct_max:
            fila("AGS % energía", 900 * r.agsat / r.kcal, None, o.agsat_pct_max, "%")
        for n in sorted(set(o.minimos) | set(o.maximos)):
            fila(n, getattr(r, n), o.minimos.get(n), o.maximos.get(n), "g" if n == "fibra" else "mg")
    return pd.DataFrame(filas)
