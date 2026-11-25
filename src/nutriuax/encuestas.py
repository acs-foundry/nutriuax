"""Calculador de encuestas dietéticas y adherencia clínica (T08, T09, T10).

Implementa:
1. Registro dietético de N días (3 días estándar): acepta alimentos del catálogo, códigos `fdc_<ndb>`
   o nombres resueltos por la tabla de equivalencias, con conversión crudo ↔ cocinado (`coccion.py`),
   calculando energía, macronutrientes, fibra, proteína animal/vegetal, 9 aminoácidos esenciales
   (incluyendo Leu/Ile/Val en mg/día y mg/kg de peso o masa magra) y minerales (Na, K, P, Ca).
2. FFQ PREDIMED-Plus (9 categorías estándar de frecuencia): convierte ítems con ración estándar y
   categoría de frecuencia en gramos/día e ingesta nutricional diaria (soporta ventana anual clásica
   o ventana adaptada de 8 semanas con aviso explícito de alcance).
3. MEDAS-14 (Schröder et al., J Nutr 2011; 14 ítems, 0–14 puntos).
4. Fórmula de Maroni (1985) de nitrógeno ureico urinario de 24 h (NUU) y clasificación combinada de
   adherencia a partir de `config/adherencia.toml`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

from . import base_fdc, coccion, equivalencias as eq
from .composicion import AMINOACIDOS, NUTRIENTES, Composicion

RAIZ = Path(__file__).resolve().parents[2]

# Categorías estándar del FFQ PREDIMED-Plus → raciones/día (Fernández-Ballart et al., Br J Nutr 2010)
FRECUENCIAS_FFQ: dict[str, float] = {
    "nunca": 0.0,
    "0": 0.0,
    "1-3/mes": 2.0 / 30.0,
    "1/sem": 1.0 / 7.0,
    "2-4/sem": 3.0 / 7.0,
    "5-6/sem": 5.5 / 7.0,
    "1/dia": 1.0,
    "2-3/dia": 2.5,
    "4-6/dia": 5.0,
    ">6/dia": 6.5,
}


@dataclass(frozen=True)
class ResultadoMEDAS14:
    puntuacion: int
    categoria: str  # "adherente" | "parcial" | "no_adherente"
    detalle: dict[str, bool]


@dataclass(frozen=True)
class ResultadoAdherencia:
    participante: str
    brazo: str
    clasificacion: str            # "adherente" | "parcial" | "no_adherente"
    proteina_media_gkg: float
    dias_proteina_en_rango: int
    dias_totales: int
    proteina_ok: bool
    maroni_proteina_g: float | None
    maroni_diff_rel: float | None
    maroni_ok: bool | None
    sin_maroni: bool
    medas14: int | None
    medas14_estado: str | None
    pct_proteina_media: float
    notas: list[str]


def cargar_config_adherencia(ruta: Path | None = None) -> dict[str, Any]:
    p = Path(ruta) if ruta else RAIZ / "config" / "adherencia.toml"
    with p.open("rb") as fh:
        return tomllib.load(fh)


def _resolver_alimentos_registro(
    registros: list[dict[str, Any]], comp: Composicion
) -> tuple[Composicion, pd.DataFrame, list[str]]:
    """Normaliza ítems de un registro alimentario (id catálogo, `fdc_<ndb>`, o nombre español)."""
    avisos: list[str] = []
    tablas_eq = eq.cargar()
    base_completa = base_fdc.cargar_completa()
    extras: list[pd.Series] = []
    filas: list[dict[str, Any]] = []

    for idx, r in enumerate(registros, start=1):
        al = str(r.get("alimento") or r.get("id") or "").strip()
        if not al:
            avisos.append(f"Línea {idx}: alimento vacío ignorado.")
            continue
        gramos = float(r.get("gramos") or 0.0)
        unidad = str(r.get("unidad") or "g").strip().lower()
        estado = str(r.get("estado") or "crudo").strip().lower()
        tecnica = str(r.get("tecnica") or "").strip().lower()
        fid: str | None = None
        nombre = al

        if al in comp.tabla.index:
            fid = al
            nombre = str(comp.tabla.at[al, "nombre"])
        elif al.lower().startswith("fdc_") and base_completa is not None:
            ndb = al[4:].strip().zfill(5)
            try:
                fila = base_fdc.fila_composicion(ndb, base=base_completa)
                extras.append(fila)
                fid = str(fila.name)
                nombre = str(fila["nombre"])
            except KeyError:
                avisos.append(f"Línea {idx}: código FDC «{al}» no encontrado.")
                continue
        else:
            res_eq = eq.resolver(al, gramos if gramos > 0 else 100.0, unidad, tablas_eq)
            if res_eq.alimento and res_eq.alimento in tablas_eq.canonicos.index:
                ndb = str(tablas_eq.canonicos.at[res_eq.alimento, "ndb"]).strip()
                if ndb and base_completa is not None:
                    try:
                        fila = base_fdc.fila_composicion(ndb, base=base_completa)
                        extras.append(fila)
                        fid = str(fila.name)
                        nombre = f"{al} ({res_eq.alimento})"
                        if res_eq.gramos is not None:
                            gramos = float(res_eq.gramos)
                    except KeyError:
                        pass
            if fid is None and base_completa is not None:
                bus = base_fdc.buscar(al, n=1, base=base_completa)
                if not bus.empty:
                    ndb = str(bus.iloc[0]["ndb"])
                    fila = base_fdc.fila_composicion(ndb, base=base_completa)
                    extras.append(fila)
                    fid = str(fila.name)
                    nombre = str(fila["nombre"])
                    avisos.append(f"Línea {idx}: «{al}» emparejado por búsqueda FDC → {nombre} (revisar).")

        if fid is None:
            avisos.append(f"Línea {idx}: sin equivalencia para «{al}».")
            continue
        if gramos <= 0:
            avisos.append(f"Línea {idx}: gramos ≤ 0 para «{al}» ignorado.")
            continue

        filas.append(
            {
                "participante": str(r.get("participante") or "P001"),
                "dia": int(r.get("dia") or 1),
                "comida": str(r.get("comida") or "C"),
                "id": fid,
                "nombre": nombre,
                "gramos": gramos,
                "estado": estado,
                "tecnica": tecnica,
            }
        )

    comp_out = comp.anadir(extras) if extras else comp
    return comp_out, pd.DataFrame(filas), avisos


def calcular_registro_diario(
    registros: list[dict[str, Any]],
    comp: Composicion,
    peso_kg: float,
    masa_magra_kg: float | None = None,
) -> dict[str, Any]:
    """Calcula un registro dietético de N días (p. ej. 3 días) con conversión crudo/cocinado y AA."""
    if peso_kg <= 0:
        raise ValueError("peso_kg debe ser > 0")
    comp_eff, df_items, avisos = _resolver_alimentos_registro(registros, comp)
    if df_items.empty:
        return {"items": [], "diario": [], "media": {}, "avisos": avisos, "fuente": comp_eff.fuente}

    calc = coccion.calcular_con_coccion(comp_eff, df_items, aplicar_aceite_absorbido=True)
    cols = NUTRIENTES + ["proteina_animal", "proteina_vegetal"]
    diario = calc.groupby(["participante", "dia"], sort=True)[cols].sum().reset_index()
    kg_aa = float(masa_magra_kg) if (masa_magra_kg and masa_magra_kg > 0) else float(peso_kg)

    diario["proteina_gkg"] = diario["proteina"] / float(peso_kg)
    diario["pct_proteina"] = (400.0 * diario["proteina"] / diario["kcal"].replace(0, float("nan"))).fillna(0.0)
    diario["pct_grasa"] = (900.0 * diario["grasa"] / diario["kcal"].replace(0, float("nan"))).fillna(0.0)
    diario["pct_hc"] = (400.0 * diario["hc"] / diario["kcal"].replace(0, float("nan"))).fillna(0.0)
    diario["bcaa_mg"] = diario["leu"] + diario["ile"] + diario["val"]
    for aa in ("leu", "ile", "val"):
        diario[f"{aa}_mgkg"] = diario[aa] / kg_aa
    diario["bcaa_mgkg"] = diario["bcaa_mg"] / kg_aa

    num_cols = [c for c in diario.columns if c not in ("participante", "dia")]
    media = {c: round(float(diario[c].mean()), 2) for c in num_cols}
    media["dias"] = int(len(diario))
    media["kg_referencia_aa"] = round(kg_aa, 2)

    return {
        "items": calc.round(2).to_dict(orient="records"),
        "diario": diario.round(2).to_dict(orient="records"),
        "media": media,
        "avisos": avisos,
        "fuente": comp_eff.fuente,
    }


def calcular_ffq_predimed(
    respuestas: list[dict[str, Any]],
    comp: Composicion,
    peso_kg: float = 70.0,
    ventana: str = "1_ano",
) -> dict[str, Any]:
    """Calcula ingesta media diaria desde un FFQ PREDIMED-Plus (9 categorías de frecuencia).

    Cada respuesta: `{"alimento": str, "racion_g": float, "frecuencia": str}` donde `frecuencia`
    es una clave de `FRECUENCIAS_FFQ` (`nunca`, `1-3/mes`, `1/sem`, `2-4/sem`, `5-6/sem`,
    `1/dia`, `2-3/dia`, `4-6/dia`, `>6/dia`).
    """
    avisos: list[str] = []
    if ventana == "8_semanas":
        avisos.append(
            "Ventana adaptada a 8 semanas: no validada formalmente frente al FFQ anual PREDIMED-Plus "
            "(usar el registro de 3 días como referencia primaria del periodo)."
        )
    registros: list[dict[str, Any]] = []
    for idx, r in enumerate(respuestas, start=1):
        freq_raw = str(r.get("frecuencia") or "nunca").strip().lower().replace(" ", "")
        if freq_raw not in FRECUENCIAS_FFQ:
            avisos.append(f"Ítem FFQ {idx}: frecuencia «{r.get('frecuencia')}» no reconocida.")
            continue
        mult = FRECUENCIAS_FFQ[freq_raw]
        racion_g = float(r.get("racion_g") or 0.0)
        g_dia = racion_g * mult
        if g_dia <= 0:
            continue
        registros.append(
            {
                "participante": str(r.get("participante") or "P001"),
                "dia": 1,
                "comida": "FFQ",
                "alimento": r.get("alimento"),
                "gramos": g_dia,
                "estado": str(r.get("estado") or "crudo"),
            }
        )
    res = calcular_registro_diario(registros, comp, peso_kg=peso_kg)
    res["ventana"] = ventana
    res["avisos"] = avisos + res["avisos"]
    res["items_activos"] = len(registros)
    return res


def calcular_medas14(respuestas: dict[str, Any], cfg_ruta: Path | None = None) -> ResultadoMEDAS14:
    """Puntuación validada MEDAS-14 (Schröder et al., J Nutr 2011; 0–14 puntos).

    Claves esperadas (valores numéricos diarios/semanales o booleanos):
    1. `aove_grasa_principal` (bool): usa aceite de oliva como grasa culinaria principal.
    2. `aove_cucharadas_dia` (float): ≥ 4 cucharadas/día (≥ 40–50 g).
    3. `verdura_raciones_dia` (float): ≥ 2 raciones/día (≥ 1 cruda/ensalada).
    4. `fruta_raciones_dia` (float): ≥ 3 piezas/raciones/día.
    5. `carne_roja_raciones_dia` (float): < 1 ración/día (carne roja, hamburguesas, embutidos).
    6. `mantequilla_raciones_dia` (float): < 1 ración/día (mantequilla, margarina, nata).
    7. `bebidas_azucaradas_dia` (float): < 1 bebida/día.
    8. `vino_copas_semana` (float): ≥ 7 copas/semana (criterio histórico PREDIMED; en clínica sin alcohol = 0).
    9. `legumbres_raciones_semana` (float): ≥ 3 raciones/semana.
    10. `pescado_marisco_semana` (float): ≥ 3 raciones/semana.
    11. `bolleria_comercial_semana` (float): < 3 veces/semana.
    12. `frutos_secos_semana` (float): ≥ 3 raciones/semana.
    13. `prefiere_ave_sobre_roja` (bool): prefiere pollo/pavo/conejo a ternera/cerdo/embutido.
    14. `sofrito_semana` (float): ≥ 2 veces/semana (sofrito con tomate, cebolla, ajo y AOVE).
    """
    cfg = cargar_config_adherencia(cfg_ruta).get("medas14", {})
    adh_min = int(cfg.get("adherente_min", 9))
    par_min = int(cfg.get("parcial_min", 7))

    def _f(k: str, default: float = 0.0) -> float:
        return float(respuestas.get(k, default))

    detalle = {
        "01_aove_principal": bool(respuestas.get("aove_grasa_principal", False)),
        "02_aove_4_cucharadas_dia": _f("aove_cucharadas_dia") >= 4.0,
        "03_verdura_2_dia": _f("verdura_raciones_dia") >= 2.0,
        "04_fruta_3_dia": _f("fruta_raciones_dia") >= 3.0,
        "05_carne_roja_lt1_dia": _f("carne_roja_raciones_dia", 1.0) < 1.0,
        "06_mantequilla_lt1_dia": _f("mantequilla_raciones_dia", 1.0) < 1.0,
        "07_bebidas_azucaradas_lt1_dia": _f("bebidas_azucaradas_dia", 1.0) < 1.0,
        "08_vino_7_semana": _f("vino_copas_semana") >= 7.0,
        "09_legumbres_3_semana": _f("legumbres_raciones_semana") >= 3.0,
        "10_pescado_3_semana": _f("pescado_marisco_semana") >= 3.0,
        "11_bolleria_lt3_semana": _f("bolleria_comercial_semana", 3.0) < 3.0,
        "12_frutos_secos_3_semana": _f("frutos_secos_semana") >= 3.0,
        "13_prefiere_ave": bool(respuestas.get("prefiere_ave_sobre_roja", False)),
        "14_sofrito_2_semana": _f("sofrito_semana") >= 2.0,
    }
    puntos = sum(1 for v in detalle.values() if v)
    cat = "adherente" if puntos >= adh_min else ("parcial" if puntos >= par_min else "no_adherente")
    return ResultadoMEDAS14(puntuacion=puntos, categoria=cat, detalle=detalle)


def proteina_maroni(nuu_g_dia: float, peso_kg: float) -> float:
    """Ingesta proteica estimada (g/día) a partir de nitrógeno ureico en orina de 24 h (Maroni 1985):
    P (g/d) = 6,25 × (NUU [g/d] + 0,031 × peso [kg]).
    """
    if nuu_g_dia < 0 or peso_kg <= 0:
        raise ValueError("nuu_g_dia debe ser ≥ 0 y peso_kg > 0")
    return round(6.25 * (float(nuu_g_dia) + 0.031 * float(peso_kg)), 2)


def evaluar_adherencia(
    participante: str,
    brazo: str,
    proteinas_diarias_g: list[float],
    kcal_diarias: list[float],
    peso_kg: float,
    nuu_g_dia: float | None = None,
    medas14_puntos: int | None = None,
    cfg_ruta: Path | None = None,
) -> ResultadoAdherencia:
    """Clasificación combinada de adherencia según `config/adherencia.toml`."""
    if not proteinas_diarias_g or peso_kg <= 0:
        raise ValueError("Se requiere al menos 1 día de ingesta proteica y peso_kg > 0")
    cfg = cargar_config_adherencia(cfg_ruta)
    p_cfg = cfg["proteina"]
    brazo_k = brazo.strip().lower()
    if brazo_k not in p_cfg["objetivo_gkg"]:
        raise ValueError(f"Brazo «{brazo}» no configurado (disponibles: {list(p_cfg['objetivo_gkg'])})")

    objetivo = float(p_cfg["objetivo_gkg"][brazo_k])
    tol_p = float(p_cfg["tolerancia_relativa"])
    dias_min = int(p_cfg["dias_minimos"])
    lo_gkg, hi_gkg = objetivo * (1.0 - tol_p), objetivo * (1.0 + tol_p)

    gkg_dias = [float(g) / float(peso_kg) for g in proteinas_diarias_g]
    en_rango = sum(1 for v in gkg_dias if lo_gkg <= v <= hi_gkg)
    dias_tot = len(gkg_dias)
    prot_ok = en_rango >= min(dias_min, dias_tot)
    prot_media_g = sum(proteinas_diarias_g) / dias_tot
    prot_media_gkg = prot_media_g / float(peso_kg)
    kcal_media = sum(kcal_diarias) / len(kcal_diarias) if kcal_diarias else 0.0
    pct_prot = (400.0 * prot_media_g / kcal_media) if kcal_media > 0 else 0.0

    notas: list[str] = []
    if brazo_k == "hiperproteica":
        pct_inf = float(p_cfg.get("pct_energia_informativo", {}).get("hiperproteica", 30.0))
        if pct_prot < pct_inf:
            notas.append(
                f"Informativo: % energía proteica ({pct_prot:.1f} %) < {pct_inf:.0f} %; prevalece criterio g/kg."
            )

    maroni_g: float | None = None
    maroni_diff: float | None = None
    maroni_ok: bool | None = None
    sin_maroni = nuu_g_dia is None
    if not sin_maroni:
        maroni_g = proteina_maroni(float(nuu_g_dia), peso_kg)
        tol_m = float(cfg["maroni"]["tolerancia_relativa"])
        maroni_diff = abs(maroni_g - prot_media_g) / max(prot_media_g, 1e-6)
        maroni_ok = maroni_diff <= tol_m
    else:
        notas.append("sin_maroni: no se aportó NUU de 24 h.")

    med_estado: str | None = None
    if brazo_k == "mediterranea" and medas14_puntos is not None:
        m_cfg = cfg["medas14"]
        if medas14_puntos >= int(m_cfg["adherente_min"]):
            med_estado = "adherente"
        elif medas14_puntos >= int(m_cfg["parcial_min"]):
            med_estado = "parcial"
        else:
            med_estado = "no_adherente"

    # Combinación: todos → adherente; uno de prot/maroni (o ambos con MEDAS parcial) → parcial; ninguno → no_adherente
    if sin_maroni:
        if prot_ok and med_estado in (None, "adherente"):
            clasif = "adherente"
        elif prot_ok and med_estado == "parcial":
            clasif = "parcial"
        elif prot_ok or med_estado == "adherente":
            clasif = "parcial"
        else:
            clasif = "no_adherente"
    else:
        assert maroni_ok is not None
        if prot_ok and maroni_ok:
            if med_estado in (None, "adherente"):
                clasif = "adherente"
            elif med_estado == "parcial":
                clasif = "parcial"
            else:
                clasif = "parcial"
        elif prot_ok or maroni_ok:
            clasif = "parcial"
        else:
            clasif = "no_adherente"

    return ResultadoAdherencia(
        participante=participante,
        brazo=brazo_k,
        clasificacion=clasif,
        proteina_media_gkg=round(prot_media_gkg, 3),
        dias_proteina_en_rango=en_rango,
        dias_totales=dias_tot,
        proteina_ok=prot_ok,
        maroni_proteina_g=maroni_g,
        maroni_diff_rel=round(maroni_diff, 3) if maroni_diff is not None else None,
        maroni_ok=maroni_ok,
        sin_maroni=sin_maroni,
        medas14=medas14_puntos,
        medas14_estado=med_estado,
        pct_proteina_media=round(pct_prot, 1),
        notas=notas,
    )
