"""Modo hogar (ADR-0005, T24): un menú para N miembros que comparten plato, con ración y complementos propios.

Etapa 1 · platos: MILP pequeño y común. Elige para cada comida (C, X) con alguien presente un plato principal
compartido (y en la comida un primero/guarnición opcional) entre las recetas candidatas: sin alérgenos de ningún
presente (duro), frecuencias semanales del hogar (blandas), sin repetir receta (blando), y un coste por receta
que favorece platos cuya energía y proteína por ración se acercan a la necesidad media de los presentes.

Etapa 2 · raciones: un MILP por miembro con los platos fijos: multiplicador k ∈ [k_min, k_max] de la ración de
adulto de cada plato en las comidas a las que asiste y complementos del catálogo (desayuno y merienda solo
complementos). Objetivos blandos de su perfil con suelos de seguridad ya aplicados (seguridad.py).

Datos personales (edad, peso, talla) solo en memoria; nunca se escriben.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

import pandas as pd
import pulp

from .composicion import NUTRIENTES, Composicion
from .generador import TOPE_COMIDA
from .objetivos import DIAS, NOMBRE_COMIDA, PERFILES, Objetivos, Persona
from .recetas import Receta
from .seguridad import objetivos_seguros

COMIDAS_HOGAR = ["D", "C", "M", "X"]
COMIDAS_CON_PLATO = ("C", "X")
REPARTO_HOGAR = {"D": 0.20, "C": 0.40, "M": 0.10, "X": 0.30}     # fracción de la energía del día
# roles del catálogo admitidos como complemento en cada comida
COMPLEMENTOS = {"D": {"lacteo", "cereal", "fruta", "frutos_secos", "grasa", "proteina"},
                "M": {"lacteo", "cereal", "fruta", "frutos_secos", "proteina"},
                "C": {"cereal", "fruta", "lacteo", "verdura", "grasa"},
                "X": {"cereal", "fruta", "lacteo", "verdura", "grasa"}}
MAX_COMPLEMENTOS = {"D": 4, "M": 3, "C": 3, "X": 3}
# frecuencias semanales del hogar: clave de perfil → grupos de receta que cuentan
GRUPOS_FRECUENCIA = {"legumbre": {"legumbre"}, "pescado": {"pescado"}, "carne": {"carne_roja", "ave"},
                     "carne_roja": {"carne_roja"}, "huevo": {"huevo"}}
K_PRESELECCION = 40
# pesos de las preferencias (ADR-0007 §4); configurables con Opciones.pesos
PESOS_PREFERENCIAS = dict(valoracion=2.0, valoracion_baja=40.0, repeticion=30.0, categoria=15.0, mismo_dia=6.0,
                          temporada=1.0, tiempo=0.3, batch=60.0)
LABORABLES = range(5)    # lunes a viernes (día 0 = lunes)


def _temporada() -> dict[str, set[int]]:
    from .composicion import DATA_DIR
    ruta = DATA_DIR / "temporada.csv"
    if not ruta.exists():
        return {}
    t = pd.read_csv(ruta, dtype=str, comment="#", keep_default_na=False)
    return {r.alimento: {int(x) for x in r.meses.split(";") if x} for r in t.itertuples()}


_TEMPORADA = None


def fuera_de_temporada(r: Receta, mes: int | None) -> float:
    """Fracción de los gramos de frutas y verduras con temporada definida que están fuera de su temporada."""
    global _TEMPORADA
    if mes is None:
        return 0.0
    if _TEMPORADA is None:
        _TEMPORADA = _temporada()
    con = fuera = 0.0
    for i in r.ingredientes:
        meses = _TEMPORADA.get(i.get("alimento") or "")
        if meses and i.get("gramos"):
            con += i["gramos"]
            fuera += i["gramos"] if mes not in meses else 0.0
    return fuera / con if con else 0.0


def _peso(op: "Opciones", clave: str) -> float:
    return op.pesos.get(clave, PESOS_PREFERENCIAS[clave])


@dataclass
class Miembro:
    id: str                      # seudónimo
    sexo: str
    edad: int
    peso: float
    talla: float
    actividad: float = 1.55
    perfil: str = "mantenimiento"
    alergias: set[str] = field(default_factory=set)      # UE-14
    vetados: set[str] = field(default_factory=set)       # ids de receta o de alimento del catálogo
    masa_magra: float | None = None

    def persona(self) -> Persona:
        return Persona(self.id, self.sexo, self.edad, self.peso, self.talla, self.actividad, self.masa_magra, None)


@dataclass
class Hogar:
    miembros: list[Miembro]
    asistencia: dict[tuple[int, str], set[str]] = field(default_factory=dict)  # (día, comida) → ids; falta = todos

    def presentes(self, d: int, m: str) -> list[Miembro]:
        ids = self.asistencia.get((d, m))
        return [x for x in self.miembros if ids is None or x.id in ids]


@dataclass
class Opciones:
    dias: int = 7
    k_min: float = 0.5
    k_max: float = 2.0
    primero_en_comida: bool = True
    tiempo_etapa1: int = 30
    tiempo_etapa2: int = 15
    semilla: int = 0
    valoraciones: dict[str, float] = field(default_factory=dict)    # receta → 1-5 (T25)
    penalizar: dict[str, float] = field(default_factory=dict)       # receta → coste extra (reintento)
    batch: bool = False              # cocinar el domingo para lunes-viernes (ADR-0007 §4)
    mes: int | None = None           # mes del menú (1-12) para la temporada; None = no cuenta
    minutos_max_laborable: int = 45  # tiempo de cocina razonable de lunes a viernes
    pesos: dict[str, float] = field(default_factory=dict)           # sustituye a PESOS_PREFERENCIAS


@dataclass
class MenuHogar:
    platos: pd.DataFrame          # dia, n_dia, comida, rol, receta, nombre
    raciones: pd.DataFrame        # miembro, n_dia, comida, receta, k, gramos_crudo
    complementos: pd.DataFrame    # miembro, n_dia, comida, id, nombre, gramos
    resumen: pd.DataFrame         # miembro, n_dia, nutrientes del día, kcal_obj, kcal_ok, …
    objetivos: dict[str, Objetivos]
    avisos: list[str]
    estado: str


def _conflicto(receta: Receta, miembros: list[Miembro]) -> bool:
    return any(receta.alergenos & m.alergias or receta.id in m.vetados for m in miembros)


def _coste_preferencia(r: Receta, op: Opciones, dia: int | None = None) -> float:
    """Coste (menor = mejor) por preferencias del hogar. Valoración 1-5 (3 por defecto); ≤ 2 casi nunca."""
    v = op.valoraciones.get(r.id, 3.0)
    coste = (5.0 - v) * _peso(op, "valoracion") + (_peso(op, "valoracion_baja") if v <= 2 else 0.0)
    coste += 10.0 * _peso(op, "temporada") * fuera_de_temporada(r, op.mes)
    if dia is not None and dia in LABORABLES and r.minutos and r.minutos > op.minutos_max_laborable:
        coste += _peso(op, "tiempo") * (r.minutos - op.minutos_max_laborable)
    if dia is not None and op.batch and dia in LABORABLES and not (r.congelable or r.nevera >= dia + 1):
        coste += _peso(op, "batch")       # cocinado el domingo: debe aguantar hasta el día d o congelarse
    return coste + op.penalizar.get(r.id, 0.0)


def _candidatas(recetas: list[Receta], hogar: Hogar, op: Opciones, m: str, roles: set[str],
                cobertura_min: float) -> list[Receta]:
    todos = hogar.miembros
    base = [r for r in recetas if r.rol in roles and m in r.comidas and r.cobertura >= cobertura_min
            and r.nutrientes["kcal"] > 0]
    # preselección top-K: sin conflicto con NADIE del hogar primero; desempate por id (determinista)
    buenas = [r for r in base if op.valoraciones.get(r.id, 3.0) > 2]
    if len(buenas) >= 3:                     # ≤ 2 estrellas: fuera si hay alternativas
        base = buenas
    base.sort(key=lambda r: (_conflicto(r, todos), _coste_preferencia(r, op), r.id))
    return base[:K_PRESELECCION]


def etapa1_platos(recetas: list[Receta], hogar: Hogar, objs: dict[str, Objetivos], op: Opciones,
                  cobertura_min: float = 0.9) -> pd.DataFrame:
    rng = random.Random(op.semilla)
    huecos = []   # (d, m, slot, candidatas)
    for d in range(op.dias):
        for m in COMIDAS_CON_PLATO:
            pres = hogar.presentes(d, m)
            if not pres:
                continue
            cand_p = [r for r in _candidatas(recetas, hogar, op, m, {"principal"}, cobertura_min)
                      if not _conflicto(r, pres)]
            if not cand_p:
                raise RuntimeError(f"No hay platos principales sin alérgenos para el día {d + 1}, {NOMBRE_COMIDA[m]}.")
            huecos.append((d, m, "principal", cand_p))
            if m == "C" and op.primero_en_comida:
                cand_s = [r for r in _candidatas(recetas, hogar, op, m, {"primero", "guarnicion"}, cobertura_min)
                          if not _conflicto(r, pres)]
                if cand_s:
                    huecos.append((d, m, "primero", cand_s))

    prob = pulp.LpProblem("platos", pulp.LpMinimize)
    z, coste = {}, []
    for (d, m, slot, cand) in huecos:
        pres = hogar.presentes(d, m)
        kcal_obj = sum(objs[x.id].kcal for x in pres) / len(pres) * REPARTO_HOGAR[m]
        prot_obj = sum(objs[x.id].proteina[0] + objs[x.id].proteina[1] for x in pres) / (2 * len(pres)) * REPARTO_HOGAR[m]
        fr = 0.75 if (slot == "principal" and m == "C" and op.primero_en_comida) else (0.25 if slot == "primero" else 1.0)
        for r in cand:
            v = prob.add_variable(f"z_{d}_{m}_{slot}_{len(z)}", cat="Binary")
            z[(d, m, slot, r.id)] = (v, r)
            ajuste = abs(r.nutrientes["kcal"] - fr * kcal_obj) / max(fr * kcal_obj, 1) * 10
            ajuste += max(0.0, fr * prot_obj - r.nutrientes["proteina"]) / max(fr * prot_obj, 1) * 10
            coste.append((ajuste + _coste_preferencia(r, op, d) + 0.3 * rng.random()) * v)
        vs = [z[(d, m, slot, r.id)][0] for r in cand]
        if slot == "principal":
            prob.addConstraint(pulp.lpSum(vs) == 1)
        else:
            prob.addConstraint(pulp.lpSum(vs) <= 1)
            coste.append(-2.0 * pulp.lpSum(vs))     # se prefiere poner primero si encaja
    # no repetir receta en la semana (blando)
    por_receta: dict[str, list] = {}
    for (d, m, slot, rid), (v, r) in z.items():
        por_receta.setdefault(rid, []).append(v)
    for rid, vs in por_receta.items():
        if len(vs) > 1:
            s = prob.add_variable(f"rep_{len(coste)}", lowBound=0)
            prob.addConstraint(pulp.lpSum(vs) <= 1 + s)
            coste.append(_peso(op, "repeticion") * s)
    # variedad: cada categoría de plato principal como mucho en 1/3 de las comidas (+1), y no dos veces el mismo día
    principales = [(d, m, v, r) for (d, m, slot, _), (v, r) in z.items() if slot == "principal"]
    n_huecos = len({(d, m) for d, m, _, _ in principales})
    tope = n_huecos // 3 + 1
    for cat in {r.categoria for *_, r in principales}:
        vs = [v for d, m, v, r in principales if r.categoria == cat]
        s = prob.add_variable(f"cat_{cat}_{len(coste)}", lowBound=0)
        prob.addConstraint(pulp.lpSum(vs) <= tope + s)
        coste.append(_peso(op, "categoria") * s)
        for d in range(op.dias):
            vd = [v for dd, m, v, r in principales if dd == d and r.categoria == cat]
            if len(vd) > 1:
                s = prob.add_variable(f"catd_{cat}_{d}_{len(coste)}", lowBound=0)
                prob.addConstraint(pulp.lpSum(vd) <= 1 + s)
                coste.append(_peso(op, "mismo_dia") * s)
    # frecuencias semanales del hogar (las más estrictas de los perfiles), blandas
    mins: dict[str, int] = {}
    maxs: dict[str, int] = {}
    for x in hogar.miembros:
        pf = objs[x.id].perfil
        for k, v in pf.semanal_min.items():
            if k in GRUPOS_FRECUENCIA:
                mins[k] = max(mins.get(k, 0), v)
        for k, v in pf.semanal_max.items():
            if k in GRUPOS_FRECUENCIA:
                maxs[k] = min(maxs.get(k, 99), v)
    escala = op.dias / 7.0
    for k, grupos in GRUPOS_FRECUENCIA.items():
        cnt = pulp.lpSum(v for (_, _, slot, _), (v, r) in z.items() if slot == "principal" and r.grupos & grupos)
        if k in mins:
            s = prob.add_variable(f"fmin_{k}", lowBound=0)
            prob.addConstraint(cnt + s >= round(mins[k] * escala))
            coste.append(15.0 * s)
        if k in maxs:
            s = prob.add_variable(f"fmax_{k}", lowBound=0)
            prob.addConstraint(cnt - s <= max(round(maxs[k] * escala), 0))
            coste.append(15.0 * s)
    prob.setObjective(pulp.lpSum(coste))
    prob.solve(pulp.HiGHS(msg=False, timeLimit=op.tiempo_etapa1, gapRel=0.01))
    filas = []
    for (d, m, slot, rid), (v, r) in z.items():
        if (v.value() or 0) > 0.5:
            filas.append(dict(dia=DIAS[d % 7], n_dia=d + 1, comida=m, rol=slot, receta=rid, nombre=r.nombre))
    if not filas:
        raise RuntimeError(f"La etapa 1 no devolvió platos (estado {pulp.LpStatus[prob.status]}).")
    df = pd.DataFrame(filas)
    df["_c"] = df["comida"].map({m: i for i, m in enumerate(COMIDAS_HOGAR)})
    df["_r"] = df["rol"].map({"principal": 0, "primero": 1})
    return df.sort_values(["n_dia", "_c", "_r"]).drop(columns=["_c", "_r"]).reset_index(drop=True)


def etapa2_miembro(miembro: Miembro, obj: Objetivos, platos: pd.DataFrame, recetas: dict[str, Receta],
                   comp: Composicion, hogar: Hogar, op: Opciones) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    tab = comp.tabla
    pf = obj.perfil
    rng = random.Random(f"{op.semilla}-{miembro.id}")
    prob = pulp.LpProblem(f"raciones_{miembro.id}", pulp.LpMinimize)
    coste = []
    asiste = {(d, m) for d in range(op.dias) for m in COMIDAS_HOGAR
              if miembro.id in {x.id for x in hogar.presentes(d, m)}}
    # platos compartidos → k
    kv = {}
    for p in platos.itertuples():
        d = p.n_dia - 1
        if (d, p.comida) not in asiste:
            continue
        k = prob.add_variable(f"k_{d}_{p.comida}_{p.rol}", lowBound=op.k_min, upBound=op.k_max)
        dk = prob.add_variable(f"dk_{d}_{p.comida}_{p.rol}", lowBound=0)
        prob.addConstraint(k - 1 <= dk)
        prob.addConstraint(1 - k <= dk)
        coste.append(8.0 * dk)
        kv[(d, p.comida, p.rol)] = (k, recetas[p.receta])
    # complementos
    def admitido(f, m):
        rol, cs, et = tab.at[f, "rol"], tab.at[f, "comidas_set"], tab.at[f, "etiquetas_set"]
        if rol not in COMPLEMENTOS[m]:
            return False
        if m == "M":
            if not (cs & {"M", "MM"}):
                return False
        elif m not in cs:
            return False
        if m in ("C", "X") and rol == "cereal" and "pan" not in et:
            return False
        if tab.at[f, "alergenos_set"] & miembro.alergias or f in miembro.vetados or et & pf.excluir_etiquetas:
            return False
        return True
    x, y = {}, {}
    for (d, m) in sorted(asiste):
        for f in tab.index:
            if admitido(f, m):
                x[(d, m, f)] = prob.add_variable(f"x_{d}_{m}_{f}", lowBound=0)
                y[(d, m, f)] = prob.add_variable(f"y_{d}_{m}_{f}", cat="Binary")
                lo, hi = float(tab.at[f, "min_g"]), float(tab.at[f, "max_g"])
                hi = min(hi, TOPE_COMIDA.get(tab.at[f, "rol"], {}).get(m, hi))
                lo = min(lo, hi)
                prob.addConstraint(x[(d, m, f)] >= lo * y[(d, m, f)])
                prob.addConstraint(x[(d, m, f)] <= hi * y[(d, m, f)])
                coste.append((3.0 + 0.5 * rng.random()) * y[(d, m, f)])
        ys = [y[k] for k in y if k[0] == d and k[1] == m]
        if ys:
            prob.addConstraint(pulp.lpSum(ys) <= MAX_COMPLEMENTOS[m])
            for rol in ("grasa", "cereal", "lacteo", "fruta"):
                yr = [y[k] for k in y if k[0] == d and k[1] == m and tab.at[k[2], "rol"] == rol]
                if len(yr) > 1:
                    prob.addConstraint(pulp.lpSum(yr) <= 1)
        if m == "D" and ys:
            prob.addConstraint(pulp.lpSum(ys) >= 2)
            base_d = [y[k] for k in y if k[0] == d and k[1] == m and tab.at[k[2], "rol"] in ("lacteo", "cereal")]
            if base_d:
                prob.addConstraint(pulp.lpSum(base_d) >= 1)      # desayuno con lácteo o cereal
        if m == "M" and ys:
            prob.addConstraint(pulp.lpSum(ys) >= 1)

    def dia_nutr(d, n):
        e = [k * r.nutrientes[n] for (dd, _, _), (k, r) in kv.items() if dd == d]
        e += [x[(dd, m, f)] * float(tab.at[f, n]) / 100.0 for (dd, m, f) in x if dd == d]
        return pulp.lpSum(e)

    def blando(expr, lim, sentido, peso):
        s = prob.add_variable(f"s_{len(coste)}", lowBound=0)
        prob.addConstraint(expr + s >= lim if sentido == "min" else expr - s <= lim)
        coste.append(peso * 100.0 / max(lim, 1e-6) * s)

    dias_con = sorted({d for (d, _) in asiste})
    for d in dias_con:
        frac = sum(REPARTO_HOGAR[m] for m in COMIDAS_HOGAR if (d, m) in asiste)
        kcal = obj.kcal * frac
        e = dia_nutr(d, "kcal")
        blando(e, kcal * 0.97, "min", 40.0)
        blando(e, kcal * 1.03, "max", 40.0)
        blando(dia_nutr(d, "proteina"), obj.proteina[0] * frac, "min", 20.0)
        blando(dia_nutr(d, "proteina"), obj.proteina[1] * frac, "max", 5.0)
        blando(9 * dia_nutr(d, "grasa"), obj.grasa_pct[1] / 100 * kcal, "max", 3.0)
        blando(4 * dia_nutr(d, "hc"), obj.hc_pct[0] / 100 * kcal, "min", 2.0)
        for n, v in obj.minimos.items():
            blando(dia_nutr(d, n), v * frac, "min", 2.0)
        for n, v in obj.maximos.items():
            blando(dia_nutr(d, n), v * frac, "max", 2.0)
    prob.setObjective(pulp.lpSum(coste))
    prob.solve(pulp.HiGHS(msg=False, timeLimit=op.tiempo_etapa2, gapRel=0.02))
    estado = pulp.LpStatus[prob.status]
    rac = [dict(miembro=miembro.id, n_dia=d + 1, comida=m, rol=rol, receta=r.id, nombre=r.nombre,
                k=round(k.value() or 0, 2), gramos_crudo=round((k.value() or 0) * r.gramos_crudo))
           for (d, m, rol), (k, r) in kv.items()]
    com = [dict(miembro=miembro.id, n_dia=d + 1, comida=m, id=f, nombre=tab.at[f, "nombre"],
                gramos=max(5.0, round((x[(d, m, f)].value() or 0) / 5) * 5))
           for (d, m, f) in x if (y[(d, m, f)].value() or 0) > 0.5]
    return pd.DataFrame(rac), pd.DataFrame(com), estado


def resumen_miembro(miembro: Miembro, obj: Objetivos, rac: pd.DataFrame, com: pd.DataFrame,
                    recetas: dict[str, Receta], comp: Composicion, hogar: Hogar, op: Opciones) -> pd.DataFrame:
    filas = []
    for d in range(op.dias):
        tot = {n: 0.0 for n in NUTRIENTES}
        for r in rac[rac.n_dia == d + 1].itertuples() if len(rac) else []:
            for n in NUTRIENTES:
                tot[n] += r.k * recetas[r.receta].nutrientes[n]
        for c_ in com[com.n_dia == d + 1].itertuples() if len(com) else []:
            for n in NUTRIENTES:
                tot[n] += c_.gramos * float(comp.tabla.at[c_.id, n]) / 100.0
        frac = sum(REPARTO_HOGAR[m] for m in COMIDAS_HOGAR
                   if miembro.id in {x.id for x in hogar.presentes(d, m)})
        kcal_obj = obj.kcal * frac
        filas.append(dict(miembro=miembro.id, n_dia=d + 1, perfil=obj.perfil.clave, kcal_obj=round(kcal_obj),
                          kcal_desv=round((tot["kcal"] - kcal_obj) / kcal_obj, 3) if kcal_obj else 0.0,
                          prot_obj=f"{obj.proteina[0] * frac:.0f}-{obj.proteina[1] * frac:.0f}",
                          **{n: round(v, 1) for n, v in tot.items()}))
    return pd.DataFrame(filas)


def generar_hogar(hogar: Hogar, recetas: list[Receta], comp: Composicion, op: Opciones | None = None,
                  cobertura_min: float = 0.9) -> MenuHogar:
    op = op or Opciones()
    objs = {m.id: objetivos_seguros(m.persona(), PERFILES[m.perfil]) for m in hogar.miembros}
    avisos = [f"{m.id}: {a}" for m in hogar.miembros for a in objs[m.id].avisos]
    por_id = {r.id: r for r in recetas}
    estado = ""
    for intento in (1, 2):
        platos = etapa1_platos(recetas, hogar, objs, op, cobertura_min)
        rac_l, com_l, res_l = [], [], []
        for m in hogar.miembros:
            rac, com, estado = etapa2_miembro(m, objs[m.id], platos, por_id, comp, hogar, op)
            rac_l.append(rac)
            com_l.append(com)
            res_l.append(resumen_miembro(m, objs[m.id], rac, com, por_id, comp, hogar, op))
        resumen = pd.concat(res_l, ignore_index=True)
        raciones = pd.concat(rac_l, ignore_index=True)
        fuera = resumen[resumen["kcal_desv"].abs() > 0.10]
        if fuera.empty or intento == 2:
            break
        # reintento: penaliza los platos de los días fuera de ±10 % en los que alguien llegó al tope de ración
        tope = raciones[(raciones.k >= op.k_max - 1e-6) | (raciones.k <= op.k_min + 1e-6)]
        malas = set(tope.merge(fuera[["miembro", "n_dia"]], on=["miembro", "n_dia"])["receta"])
        if not malas:
            break
        op = Opciones(**{**op.__dict__, "penalizar": {**op.penalizar, **{r: 25.0 for r in malas}}})
        avisos.append(f"Reintento de la etapa 1 penalizando {len(malas)} plato(s) que dejaban a alguien fuera de ±10 %.")
    for r in fuera.itertuples():
        avisos.append(f"{r.miembro}: día {r.n_dia} con energía {r.kcal_desv:+.0%} sobre su objetivo (fuera de ±10 %).")
    return MenuHogar(platos, raciones, pd.concat(com_l, ignore_index=True), resumen, objs, avisos, estado)
