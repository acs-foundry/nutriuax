"""Evaluación antropométrica, 5 ecuaciones energéticas, cribado nutricional (MUST / MNA-SF),
carga ácida renal (PRAL) y calidad proteica / aminoácido limitante (WHO 2007 AAS + umbral de leucina).

Todos los cálculos son 100 % locales, deterministas y respaldados por literatura primaria.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .generador import Menu
from .objetivos import Persona, eer_iom_2005, tmb_mifflin

# Patrón de puntuación aminoacídica para adultos (WHO/FAO/UNU 2007, TRS 935, Tabla 23), mg / g proteína.
# Nota: la base FDC separa metionina (Met) y fenilalanina (Phe); usamos los valores individuales de referencia
# de la tabla WHO 2007 (Met 16 mg/g prot, Phe 30 mg/g prot — SAA totales 22, AAA totales 38).
WHO_PATRON_AAS_MG_G: dict[str, float] = {
    "his": 15.0,
    "ile": 30.0,
    "leu": 59.0,
    "lys": 45.0,
    "met": 16.0,
    "phe": 30.0,
    "thr": 23.0,
    "trp": 6.0,
    "val": 39.0,
}


def tmb_harris_benedict_1984(p: Persona) -> float:
    """Ecuación de Harris-Benedict revisada por Roza & Shizgal (Am J Clin Nutr 1984)."""
    if p.sexo == "H":
        return 88.362 + 13.397 * p.peso + 4.799 * p.talla - 5.677 * p.edad
    return 447.593 + 9.247 * p.peso + 3.098 * p.talla - 4.330 * p.edad


def tmb_owen(p: Persona) -> float:
    """Ecuaciones de Owen (Am J Clin Nutr 1986/1987), útiles en sobrepeso/obesidad."""
    if p.sexo == "H":
        return 879.0 + 10.2 * p.peso
    return 795.0 + 7.18 * p.peso


def masa_magra_boer(p: Persona) -> float:
    """Estimación antropométrica de masa libre de grasa (Boer, Am J Physiol 1984)."""
    if p.sexo == "H":
        lbm = 0.407 * p.peso + 0.267 * p.talla - 19.2
    else:
        lbm = 0.252 * p.peso + 0.473 * p.talla - 48.3
    return max(15.0, min(p.peso * 0.95, lbm))


def tmb_cunningham(p: Persona, masa_magra_kg: float | None = None) -> float:
    """Ecuación de Cunningham (Am J Clin Nutr 1980) basada en masa libre de grasa (deportistas/DXA/BIA)."""
    lbm = masa_magra_kg if (masa_magra_kg and masa_magra_kg > 0) else (p.masa_magra or masa_magra_boer(p))
    return 500.0 + 22.0 * lbm


def peso_ideal_devine(p: Persona) -> float:
    """Peso corporal ideal por fórmula de Devine (1974), altura en cm."""
    pulgadas_sobre_60 = max(0.0, (p.talla / 2.54) - 60.0)
    base = 50.0 if p.sexo == "H" else 45.5
    return base + 2.3 * pulgadas_sobre_60


def clasificar_imc_oms(imc: float) -> str:
    if imc < 16.0:
        return "Delgadez severa"
    if imc < 17.0:
        return "Delgadez moderada"
    if imc < 18.5:
        return "Bajo peso"
    if imc < 25.0:
        return "Normopeso"
    if imc < 30.0:
        return "Sobrepeso"
    if imc < 35.0:
        return "Obesidad grado I"
    if imc < 40.0:
        return "Obesidad grado II"
    return "Obesidad grado III"


def evaluar_antropometria(
    p: Persona,
    cintura_cm: float | None = None,
    cadera_cm: float | None = None,
) -> dict[str, Any]:
    """Evaluación antropométrica completa y comparativa de 5 ecuaciones energéticas."""
    if p.peso <= 0 or p.talla <= 0:
        raise ValueError("peso y talla deben ser > 0")
    talla_m = p.talla / 100.0
    imc = p.peso / (talla_m ** 2)
    pi = peso_ideal_devine(p)
    peso_ajustado = pi + 0.25 * (p.peso - pi) if imc >= 30.0 else p.peso
    lbm_estimada = p.masa_magra if (p.masa_magra and p.masa_magra > 0) else masa_magra_boer(p)
    grasa_pct_est = max(3.0, min(65.0, (1.0 - lbm_estimada / p.peso) * 100.0))

    mifflin = tmb_mifflin(p)
    hb = tmb_harris_benedict_1984(p)
    owen = tmb_owen(p)
    cunn = tmb_cunningham(p, lbm_estimada)
    pal = p.factor_actividad

    ecuaciones = {
        "mifflin_st_jeor_1990": {"tmb_kcal": round(mifflin, 1), "get_kcal": round(mifflin * pal, 1)},
        "harris_benedict_1984": {"tmb_kcal": round(hb, 1), "get_kcal": round(hb * pal, 1)},
        "owen_1986": {"tmb_kcal": round(owen, 1), "get_kcal": round(owen * pal, 1)},
        "cunningham_1980": {"tmb_kcal": round(cunn, 1), "get_kcal": round(cunn * pal, 1)},
    }
    if p.edad < 19:
        ecuaciones["eer_iom_2005_pediatrico"] = {"tmb_kcal": None, "get_kcal": round(eer_iom_2005(p), 1)}

    out: dict[str, Any] = {
        "imc": round(imc, 2),
        "clasificacion_oms": clasificar_imc_oms(imc),
        "peso_ideal_devine_kg": round(pi, 1),
        "peso_ajustado_kg": round(peso_ajustado, 1),
        "masa_magra_kg": round(lbm_estimada, 1),
        "masa_magra_origen": "medida_dxa_bia" if p.masa_magra else "estimada_boer_1984",
        "grasa_corporal_estimada_pct": round(grasa_pct_est, 1),
        "ecuaciones_energeticas": ecuaciones,
    }

    if cintura_cm is not None and cintura_cm > 0:
        whtr = cintura_cm / p.talla
        riesgo_whtr = (
            "bajo" if whtr < 0.50 else ("moderado_central" if whtr < 0.60 else "alto_cardiometabolico")
        )
        out["indice_cintura_talla"] = round(whtr, 3)
        out["riesgo_cintura_talla"] = riesgo_whtr
        if cadera_cm is not None and cadera_cm > 0:
            whr = cintura_cm / cadera_cm
            umbral = 0.90 if p.sexo == "H" else 0.85
            out["indice_cintura_cadera"] = round(whr, 3)
            out["riesgo_cintura_cadera"] = "elevado" if whr >= umbral else "normal"
    return out


def cribado_must(
    imc: float,
    perdida_peso_pct_3_6m: float = 0.0,
    efecto_enfermedad_aguda: bool = False,
) -> dict[str, Any]:
    """Cribado universal de malnutrición MUST (BAPEN, Elia 2003; 0–6 puntos)."""
    p_imc = 0 if imc > 20.0 else (1 if imc >= 18.5 else 2)
    p_perdida = 0 if perdida_peso_pct_3_6m < 5.0 else (1 if perdida_peso_pct_3_6m <= 10.0 else 2)
    p_aguda = 2 if efecto_enfermedad_aguda else 0
    total = p_imc + p_perdida + p_aguda
    if total == 0:
        riesgo, accion = "bajo", "Cuidados clínicos habituales; repetir cribado periódicamente."
    elif total == 1:
        riesgo, accion = "medio", "Observar ingesta durante 3 días y reevaluar; valorar enriquecimiento dietético."
    else:
        riesgo, accion = "alto", "Derivar a dietista-nutricionista/unidad de nutrición y planificar soporte nutricional."
    return {
        "instrumento": "MUST",
        "puntuacion": total,
        "riesgo": riesgo,
        "desglose": {"imc": p_imc, "perdida_peso": p_perdida, "enfermedad_aguda": p_aguda},
        "plan_accion": accion,
    }


def cribado_mna_sf(
    ingesta_0_2: int,
    perdida_peso_0_3: int,
    movilidad_0_2: int,
    estres_agudo_0_2: int,
    neuropsic_0_2: int,
    imc_o_pantorrilla_0_3: int,
) -> dict[str, Any]:
    """Mini Nutritional Assessment Short-Form (MNA-SF, Rubenstein et al., J Gerontol 2001; 0–14 puntos)."""
    limites = (
        ("ingesta_0_2", ingesta_0_2, 2),
        ("perdida_peso_0_3", perdida_peso_0_3, 3),
        ("movilidad_0_2", movilidad_0_2, 2),
        ("estres_agudo_0_2", estres_agudo_0_2, 2),
        ("neuropsic_0_2", neuropsic_0_2, 2),
        ("imc_o_pantorrilla_0_3", imc_o_pantorrilla_0_3, 3),
    )
    for nom, val, mx in limites:
        if not (0 <= int(val) <= mx):
            raise ValueError(f"{nom} debe estar entre 0 y {mx}")
    total = sum(int(v) for _, v, _ in limites)
    if total >= 12:
        estado = "estado_nutricional_normal"
    elif total >= 8:
        estado = "riesgo_malnutricion"
    else:
        estado = "malnutricion"
    return {
        "instrumento": "MNA-SF",
        "puntuacion": total,
        "estado": estado,
        "rango": "12-14 normal | 8-11 riesgo | 0-7 malnutrición",
    }


def calcular_pral(
    proteina_g: float,
    fosforo_mg: float,
    potasio_mg: float,
    calcio_mg: float,
    magnesio_mg: float | None = None,
) -> dict[str, Any]:
    """Carga ácida renal potencial PRAL (Remer & Manz, J Am Diet Assoc 1995), en mEq/día.

    PRAL = 0,49 × Proteína(g) + 0,037 × P(mg) − 0,021 × K(mg) − 0,026 × Mg(mg) − 0,013 × Ca(mg).
    Si no se aporta magnesio medido, se estima conservadoramente como 0,085 × K(mg) (relación
    dietética típica en dietas mixtas mediterráneas) indicando `magnesio_estimado = True`.
    """
    mg_est = magnesio_mg is None
    mg = float(magnesio_mg) if magnesio_mg is not None else round(0.085 * float(potasio_mg), 1)
    pral = (
        0.49 * float(proteina_g)
        + 0.037 * float(fosforo_mg)
        - 0.021 * float(potasio_mg)
        - 0.026 * mg
        - 0.013 * float(calcio_mg)
    )
    clasif = "alcalinizante" if pral < -2.0 else ("neutro" if pral <= 5.0 else ("acidificante_moderado" if pral <= 20.0 else "acidificante_alto"))
    return {
        "pral_meq_dia": round(pral, 2),
        "clasificacion": clasif,
        "magnesio_usado_mg": round(mg, 1),
        "magnesio_estimado": mg_est,
        "referencia": "Remer & Manz, J Am Diet Assoc 1995",
    }


def calidad_proteica_menu(menu: Menu, edad: int = 30) -> dict[str, Any]:
    """Evalúa calidad proteica del menú: Amino Acid Score (WHO 2007), AA limitante, PRAL medio y
    disparo anabólico de leucina por toma principal (≥ 2,5 g en adultos; ≥ 3,0 g si edad ≥ 65).
    """
    r = menu.resumen
    prot_media = float(r["proteina"].mean())
    scores: dict[str, float] = {}
    for aa, ref in WHO_PATRON_AAS_MG_G.items():
        if aa in r.columns and prot_media > 0:
            mg_por_g = float(r[aa].mean()) / prot_media
            scores[aa] = round(100.0 * mg_por_g / ref, 1)
    aa_limitante = min(scores, key=scores.get) if scores else None
    aas_global = min(100.0, scores[aa_limitante]) if aa_limitante else None

    pral_dias = [
        calcular_pral(row.proteina, row.fosforo, row.potasio, row.calcio)["pral_meq_dia"]
        for row in r.itertuples(index=False)
    ]
    pral_medio = round(sum(pral_dias) / max(len(pral_dias), 1), 2)

    # Análisis de disparo anabólico de leucina por comida principal (Desayuno, Comida, Cena)
    umbral_leu_g = 3.0 if edad >= 65 else 2.5
    it = menu.items
    principales = it[it["cod_comida"].isin(["D", "C", "X"])] if "cod_comida" in it.columns else it
    por_toma = (
        principales.groupby(["n_dia", "dia", "comida"], as_index=False)["leu"].sum()
        if not principales.empty else pd.DataFrame(columns=["n_dia", "dia", "comida", "leu"])
    )
    if not por_toma.empty:
        por_toma["leu_g"] = (por_toma["leu"] / 1000.0).round(2)
        por_toma["alcanza_umbral"] = por_toma["leu_g"] >= umbral_leu_g
        tomas_ok = int(por_toma["alcanza_umbral"].sum())
        tomas_tot = int(len(por_toma))
    else:
        tomas_ok, tomas_tot = 0, 0

    pct_animal = round(100.0 * float(r["proteina_animal"].mean()) / max(prot_media, 1e-6), 1)
    pct_vegetal = round(100.0 - pct_animal, 1)

    return {
        "proteina_media_g": round(prot_media, 1),
        "proteina_animal_pct": pct_animal,
        "proteina_vegetal_pct": pct_vegetal,
        "aas_por_aa_pct": scores,
        "aminoacido_limitante": aa_limitante,
        "aas_global_pct": aas_global,
        "pral_medio_meq_dia": pral_medio,
        "pral_por_dia": pral_dias,
        "umbral_leucina_toma_g": umbral_leu_g,
        "tomas_principales_con_umbral_leu": tomas_ok,
        "tomas_principales_totales": tomas_tot,
        "tomas_leucina_detalle": por_toma.round(2).to_dict(orient="records"),
    }
