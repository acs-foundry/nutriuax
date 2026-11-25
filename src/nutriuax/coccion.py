"""Conversión crudo ↔ cocinado, retención de nutrientes y absorción de aceite (T16, ADR-0003).

Permite mostrar al paciente/dietista tanto el peso en CRUDO (compra y preparación) como el peso
estimado COCINADO (ración en el plato), teniendo en cuenta si la entrada de la tabla de composición
USDA FDC está almacenada en crudo o ya cocinada (evitando dobles conversiones), y reconvertir
registros dietéticos pesados en crudo o cocinado aplicando factores de rendimiento (USDA RF6 /
Bognár 2002) y técnicas específicas de nefrología (`doble_coccion_erc` para reducción de potasio).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .composicion import AMINOACIDOS, DATA_DIR, Composicion

# Aporte nutricional por 100 g de AOVE absorbido durante salteado/plancha/fritura (USDA NDB 04053)
_AOVE_KCAL_100G = 884.0
_AOVE_GRASA_100G = 100.0
_AOVE_AGSAT_100G = 13.8

TECNICA_DEFECTO: dict[str, str] = {
    "arroz": "hervido",
    "pasta": "hervido",
    "legumbre": "hervido",
    "carne": "plancha",
    "ave": "plancha",
    "pescado": "horno",
    "huevo": "plancha",
    "verdura": "vapor",
    "patata": "hervido",
    "tal_cual": "crudo",
}

_MARCADORES_COCINADO = (
    "cooked", "boiled", "roasted", "grilled", "broiled", "baked", "steamed", "braised", "fried",
    "hard-boiled", "cocido", "cocida", "cocidos", "cocidas", "plancha", "horno", "asado", "asada",
    "guisado", "guisada", "vapor", "salteado", "salteados", "hervido", "hervida",
)
_MARCADORES_CRUDO = ("raw", "dry", "uncooked", "crudo", "cruda", "seco", "seca", "copos")


@dataclass(frozen=True)
class FactorCoccion:
    grupo_coccion: str
    tecnica: str
    rendimiento_peso: float
    retencion_proteina: float
    retencion_potasio: float
    retencion_fosforo: float
    aceite_absorbido_g_100g: float
    fuente: str


@lru_cache(maxsize=4)
def cargar_factores(data_dir: Path | None = None) -> dict[tuple[str, str], FactorCoccion]:
    ruta = Path(data_dir or DATA_DIR) / "coccion.csv"
    df = pd.read_csv(ruta, comment="#")
    out: dict[tuple[str, str], FactorCoccion] = {}
    for r in df.itertuples(index=False):
        fc = FactorCoccion(
            grupo_coccion=str(r.grupo_coccion).strip(),
            tecnica=str(r.tecnica).strip(),
            rendimiento_peso=float(r.rendimiento_peso),
            retencion_proteina=float(r.retencion_proteina),
            retencion_potasio=float(r.retencion_potasio),
            retencion_fosforo=float(r.retencion_fosforo),
            aceite_absorbido_g_100g=float(r.aceite_absorbido_g_100g),
            fuente=str(r.fuente),
        )
        out[(fc.grupo_coccion, fc.tecnica)] = fc
    return out


def es_referencia_cocinada(nombre: str = "", busqueda_fdc: str = "") -> bool:
    """Detecta si el registro base (catálogo o FDC) ya representa el alimento COCINADO."""
    txt = f"{nombre} {busqueda_fdc}".lower()
    if any(k in txt for k in _MARCADORES_COCINADO):
        return True
    if any(k in txt for k in _MARCADORES_CRUDO):
        return False
    return False


def inferir_grupo_coccion(id_alimento: str, grupo: str = "", nombre: str = "", etiquetas: set[str] | None = None) -> str:
    """Infiere el grupo de cocción a partir del id, grupo y nombre del alimento."""
    txt = f"{id_alimento} {grupo} {nombre}".lower()
    et = etiquetas or set()
    if any(k in txt for k in ("arroz", "quinoa", "cuscus", "cuscús", "rice")):
        return "arroz"
    if any(k in txt for k in ("pasta", "espagueti", "macarron", "fideo", "spaghetti")):
        return "pasta"
    if grupo == "legumbres" or any(k in txt for k in ("lenteja", "garbanzo", "alubia", "judia", "lentil", "chickpea", "bean")):
        if any(k in txt for k in ("tofu", "hummus", "soja_bebida", "bebida de soja")):
            return "tal_cual"
        return "legumbre"
    if any(k in txt for k in ("patata", "boniato", "potato")):
        return "patata"
    if grupo == "huevos" or "huevo" in txt or "egg" in txt:
        if "clara" in txt and "raw" in txt:
            return "huevo"
        return "huevo"
    if grupo == "pescados" or "pescado" in et or any(k in txt for k in ("merluza", "salmon", "salmón", "bacalao", "atun", "atún", "dorada", "sardina", "caballa", "gamba", "mejillon")):
        if any(k in txt for k in ("lata", "conserva", "ahumad", "natural", "canned")):
            return "tal_cual"
        return "pescado"
    if "carne_blanca" in et or any(k in txt for k in ("pollo", "pavo", "conejo", "chicken", "turkey", "rabbit")):
        if any(k in txt for k in ("fiambre", "embutido", "jamon", "jamón")):
            return "tal_cual"
        return "ave"
    if grupo == "carnes" or "carne_roja" in et or any(k in txt for k in ("ternera", "cerdo", "lomo", "beef", "pork")):
        if any(k in txt for k in ("jamon", "jamón", "lomo_embuchado", "chorizo", "procesada", "cured")):
            return "tal_cual"
        return "carne"
    if grupo == "verduras":
        if any(k in txt for k in ("lechuga", "tomate", "pepino", "ensalada", "gazpacho", "aguacate", "pimiento", "cebolla", "zanahoria")):
            return "tal_cual"
        return "verdura"
    return "tal_cual"


def obtener_factor(grupo_coccion: str, tecnica: str | None = None, data_dir: Path | None = None) -> FactorCoccion:
    factores = cargar_factores(data_dir)
    tec = tecnica or TECNICA_DEFECTO.get(grupo_coccion, "crudo")
    if (grupo_coccion, tec) in factores:
        return factores[(grupo_coccion, tec)]
    if (grupo_coccion, TECNICA_DEFECTO.get(grupo_coccion, "crudo")) in factores:
        return factores[(grupo_coccion, TECNICA_DEFECTO[grupo_coccion])]
    return factores[("tal_cual", "crudo")]


def crudo_a_cocinado(gramos_crudo: float, grupo_coccion: str, tecnica: str | None = None,
                     data_dir: Path | None = None) -> float:
    """Convierte gramos en crudo a gramos estimados en plato cocinado."""
    f = obtener_factor(grupo_coccion, tecnica, data_dir)
    return round(float(gramos_crudo) * f.rendimiento_peso, 1)


def cocinado_a_crudo(gramos_cocinado: float, grupo_coccion: str, tecnica: str | None = None,
                     data_dir: Path | None = None) -> float:
    """Convierte gramos pesados en cocinado a su equivalente en crudo."""
    f = obtener_factor(grupo_coccion, tecnica, data_dir)
    return round(float(gramos_cocinado) / max(f.rendimiento_peso, 1e-6), 1)


def enriquecer_menu_coccion(items: pd.DataFrame, comp: Composicion,
                            tecnicas_por_grupo: dict[str, str] | None = None,
                            erc_doble_coccion: bool = False) -> pd.DataFrame:
    """Añade `grupo_coccion`, `tecnica`, `referencia_fdc`, `gramos_crudo` y `gramos_cocinado`.

    Respeta si el alimento del catálogo ya está expresado en peso COCINADO (como pechuga a la
    plancha, arroz cocido o lentejas cocidas en USDA SR Legacy) o en CRUDO (copos de avena, clara
    de huevo), calculando siempre el peso complementario sin duplicar factores.
    """
    out = items.copy()
    tec_map = dict(tecnicas_por_grupo or {})
    if erc_doble_coccion:
        tec_map.setdefault("legumbre", "doble_coccion_erc")
        tec_map.setdefault("verdura", "doble_coccion_erc")
        tec_map.setdefault("patata", "doble_coccion_erc")
    grupos, tecnicas, refs, g_crudo, g_cocinado = [], [], [], [], []
    for r in out.itertuples(index=False):
        fid = str(r.id)
        if fid in comp.tabla.index:
            meta = comp.tabla.loc[fid]
            nombre = str(meta.get("nombre", ""))
            busq = str(meta.get("busqueda_fdc", ""))
            grp = inferir_grupo_coccion(fid, str(meta.get("grupo", "")), nombre, meta.get("etiquetas_set"))
            ya_cocinado = es_referencia_cocinada(nombre, busq)
        else:
            nombre = str(getattr(r, "nombre", ""))
            grp = inferir_grupo_coccion(fid, "", nombre)
            ya_cocinado = es_referencia_cocinada(nombre, "")
        tec = tec_map.get(grp, TECNICA_DEFECTO.get(grp, "crudo"))
        g_base = float(r.gramos)
        if grp == "tal_cual":
            g_raw = round(g_base, 1)
            g_ck = round(g_base, 1)
        elif ya_cocinado:
            g_ck = round(g_base, 1)
            g_raw = cocinado_a_crudo(g_base, grp, tec)
        else:
            g_raw = round(g_base, 1)
            g_ck = crudo_a_cocinado(g_base, grp, tec)
        grupos.append(grp)
        tecnicas.append(tec)
        refs.append("cocinado" if ya_cocinado else "crudo")
        g_crudo.append(g_raw)
        g_cocinado.append(g_ck)
    out["grupo_coccion"] = grupos
    out["tecnica"] = tecnicas
    out["referencia_fdc"] = refs
    out["gramos_crudo"] = g_crudo
    out["gramos_cocinado"] = g_cocinado
    return out


def calcular_con_coccion(comp: Composicion, items: pd.DataFrame,
                         aplicar_aceite_absorbido: bool = False) -> pd.DataFrame:
    """Calcula nutrientes aceptando columnas opcionales `estado` ('crudo'|'cocinado') y `tecnica`.

    Compara el estado declarado por el usuario (`estado`) con el estado de la entrada en la tabla
    de composición (`crudo` o `cocinado`), convirtiendo el peso únicamente cuando difieren y
    aplicando factores de retención (incluyendo lixiviación de potasio en `doble_coccion_erc`).
    """
    df = items.copy()
    estados = df["estado"].fillna("crudo").astype(str).str.lower() if "estado" in df.columns else pd.Series(
        ["crudo"] * len(df), index=df.index)
    tecnicas_in = df["tecnica"].fillna("").astype(str).str.lower() if "tecnica" in df.columns else pd.Series(
        [""] * len(df), index=df.index)

    g_crudo_list, g_coc_list, g_fdc_list, fac_list, ref_coc_list = [], [], [], [], []
    for idx, r in df.iterrows():
        fid = str(r["id"])
        meta = comp.tabla.loc[fid] if fid in comp.tabla.index else {}
        nombre = str(meta.get("nombre", r.get("nombre", ""))) if hasattr(meta, "get") else str(r.get("nombre", ""))
        busq = str(meta.get("busqueda_fdc", "")) if hasattr(meta, "get") else ""
        grp = inferir_grupo_coccion(
            fid,
            str(meta.get("grupo", "")) if hasattr(meta, "get") else "",
            nombre,
            meta.get("etiquetas_set") if hasattr(meta, "get") else None,
        )
        ref_cocinado = es_referencia_cocinada(nombre, busq)
        est = estados.loc[idx]
        tec = tecnicas_in.loc[idx] or (TECNICA_DEFECTO.get(grp, "crudo") if (est == "cocinado" or ref_cocinado) else "crudo")
        fc = obtener_factor(grp, tec)
        g_in = float(r["gramos"])

        if grp == "tal_cual":
            g_raw = g_ck = g_fdc = g_in
        elif est == "cocinado":
            g_ck = g_in
            g_raw = g_in / max(fc.rendimiento_peso, 1e-6)
            g_fdc = g_ck if ref_cocinado else g_raw
        else:  # usuario introduce peso en crudo
            g_raw = g_in
            g_ck = g_in * fc.rendimiento_peso
            g_fdc = g_ck if ref_cocinado else g_raw

        g_crudo_list.append(round(g_raw, 1))
        g_coc_list.append(round(g_ck, 1))
        g_fdc_list.append(round(g_fdc, 2))
        fac_list.append(fc)
        ref_coc_list.append(ref_cocinado)

    df["gramos_crudo"] = g_crudo_list
    df["gramos_cocinado"] = g_coc_list
    calc_in = df.copy()
    calc_in["gramos"] = g_fdc_list
    out = comp.calcular(calc_in)

    for i, (fc, ref_coc) in enumerate(zip(fac_list, ref_coc_list)):
        idx = out.index[i]
        # Si la referencia FDC era cruda pero el alimento se cocinó, aplicamos factores de retención completos
        if not ref_coc and fc.tecnica != "crudo":
            out.at[idx, "proteina"] *= fc.retencion_proteina
            out.at[idx, "proteina_animal"] *= fc.retencion_proteina
            out.at[idx, "proteina_vegetal"] *= fc.retencion_proteina
            for aa in AMINOACIDOS:
                out.at[idx, aa] *= fc.retencion_proteina
            out.at[idx, "potasio"] *= fc.retencion_potasio
            out.at[idx, "fosforo"] *= fc.retencion_fosforo
        elif ref_coc and fc.tecnica == "doble_coccion_erc":
            # La referencia ya estaba hervida (~65% K); la doble cocción ERC reduce adicionalmente K y P
            base_herv = obtener_factor(fc.grupo_coccion, "hervido")
            out.at[idx, "potasio"] *= fc.retencion_potasio / max(base_herv.retencion_potasio, 1e-6)
            out.at[idx, "fosforo"] *= fc.retencion_fosforo / max(base_herv.retencion_fosforo, 1e-6)

        if aplicar_aceite_absorbido and fc.aceite_absorbido_g_100g > 0 and (estados.iloc[i] == "cocinado" or fc.tecnica in ("salteado", "fritura")):
            aceite_g = df.at[idx, "gramos_crudo"] * fc.aceite_absorbido_g_100g / 100.0
            out.at[idx, "kcal"] += aceite_g * _AOVE_KCAL_100G / 100.0
            out.at[idx, "grasa"] += aceite_g * _AOVE_GRASA_100G / 100.0
            out.at[idx, "agsat"] += aceite_g * _AOVE_AGSAT_100G / 100.0
    return out
