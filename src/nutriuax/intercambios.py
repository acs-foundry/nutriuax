"""Sistema español de intercambios de alimentos (estándar dietético clínico tipo EasyDiet / SENC / SED).

Convierte cualquier menú optimizado de NutriUAX en raciones de intercambio equivalentes por grupo
(Lácteos, Cereales/Legumbres/Tubérculos, Verduras, Frutas, Proteicos, Grasas y Azúcares/Opcionales)
y genera una guía personalizada de equivalencias en gramos (1 intercambio = X g) para que el paciente
pueda sustituir alimentos de forma flexible sin desajustar energía ni macronutrientes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .composicion import Composicion
from .generador import Menu


@dataclass(frozen=True)
class GrupoIntercambio:
    clave: str
    nombre: str
    kcal_ref: float
    proteina_ref_g: float
    hc_ref_g: float
    grasa_ref_g: float
    nutriente_pivote: str  # nutriente que define 1 intercambio
    cantidad_pivote: float
    descripcion: str


# Estándar español de intercambios (Russolillo & Marques-Lopes, Sistema de Intercambios para la
# Confección de Dietas y Planificación de Menús; Guía de Alimentación Española SENC/FESNAD).
GRUPOS_INTERCAMBIO: dict[str, GrupoIntercambio] = {
    "lacteos": GrupoIntercambio(
        clave="lacteos",
        nombre="Lácteos",
        kcal_ref=120.0,
        proteina_ref_g=7.0,
        hc_ref_g=10.0,
        grasa_ref_g=5.0,
        nutriente_pivote="kcal",
        cantidad_pivote=120.0,
        descripcion="1 intercambio ≈ 200 ml leche / 2 yogures naturales / 60 g queso fresco",
    ),
    "cereales_legumbres": GrupoIntercambio(
        clave="cereales_legumbres",
        nombre="Cereales, tubérculos y legumbres",
        kcal_ref=100.0,
        proteina_ref_g=3.0,
        hc_ref_g=20.0,
        grasa_ref_g=0.5,
        nutriente_pivote="hc",
        cantidad_pivote=20.0,
        descripcion="1 intercambio ≈ 20 g HC (40 g pan / 70 g arroz cocido / 100 g patata / 80 g legumbre cocida)",
    ),
    "verduras": GrupoIntercambio(
        clave="verduras",
        nombre="Verduras y hortalizas",
        kcal_ref=40.0,
        proteina_ref_g=2.0,
        hc_ref_g=6.0,
        grasa_ref_g=0.3,
        nutriente_pivote="kcal",
        cantidad_pivote=40.0,
        descripcion="1 intercambio ≈ 150–200 g de verdura variada",
    ),
    "frutas": GrupoIntercambio(
        clave="frutas",
        nombre="Frutas",
        kcal_ref=60.0,
        proteina_ref_g=0.8,
        hc_ref_g=15.0,
        grasa_ref_g=0.2,
        nutriente_pivote="hc",
        cantidad_pivote=15.0,
        descripcion="1 intercambio ≈ 15 g HC (1 manzana/naranja/pera mediana o 100 g plátano)",
    ),
    "proteicos": GrupoIntercambio(
        clave="proteicos",
        nombre="Proteicos (carne, pescado, huevo, tofu)",
        kcal_ref=110.0,
        proteina_ref_g=14.0,
        hc_ref_g=0.5,
        grasa_ref_g=5.0,
        nutriente_pivote="proteina",
        cantidad_pivote=14.0,
        descripcion="1 intercambio ≈ 14 g proteína (~50 g carne/ave, ~65 g pescado, 2 huevos pequeños, 80 g tofu)",
    ),
    "grasas": GrupoIntercambio(
        clave="grasas",
        nombre="Grasas y frutos secos",
        kcal_ref=90.0,
        proteina_ref_g=0.5,
        hc_ref_g=0.5,
        grasa_ref_g=10.0,
        nutriente_pivote="grasa",
        cantidad_pivote=10.0,
        descripcion="1 intercambio ≈ 10 g grasa (10 g AOVE = 1 cda / 15–20 g frutos secos / 65 g aguacate)",
    ),
    "azucares": GrupoIntercambio(
        clave="azucares",
        nombre="Azúcares y opcionales",
        kcal_ref=60.0,
        proteina_ref_g=0.2,
        hc_ref_g=15.0,
        grasa_ref_g=0.0,
        nutriente_pivote="kcal",
        cantidad_pivote=60.0,
        descripcion="1 intercambio ≈ 60 kcal (20 g miel / 25 g mermelada / 10 g chocolate 70 %)",
    ),
}

_MAPA_GRUPO_CATALOGO: dict[str, str] = {
    "lacteos": "lacteos",
    "cereales": "cereales_legumbres",
    "tuberculos": "cereales_legumbres",
    "legumbres": "cereales_legumbres",
    "verduras": "verduras",
    "frutas": "frutas",
    "carnes": "proteicos",
    "pescados": "proteicos",
    "huevos": "proteicos",
    "suplementos": "proteicos",
    "grasas": "grasas",
    "frutos_secos": "grasas",
    "azucares": "azucares",
}


def clasificar_grupo_intercambio(id_alimento: str, comp: Composicion) -> str:
    """Asigna un alimento del catálogo (o FDC extra) a su grupo clínico de intercambio."""
    if id_alimento in comp.tabla.index:
        meta = comp.tabla.loc[id_alimento]
        rol = str(meta.get("rol", ""))
        grp = str(meta.get("grupo", ""))
        if id_alimento == "tofu" or rol == "proteina" or rol == "suplemento":
            return "proteicos"
        if grp in _MAPA_GRUPO_CATALOGO:
            return _MAPA_GRUPO_CATALOGO[grp]
        if rol == "lacteo":
            return "lacteos"
        if rol in ("cereal", "legumbre"):
            return "cereales_legumbres"
        if rol == "verdura":
            return "verduras"
        if rol == "fruta":
            return "frutas"
        if rol in ("grasa", "frutos_secos"):
            return "grasas"
        if rol == "dulce":
            return "azucares"
    return "proteicos"


def gramos_por_intercambio(id_alimento: str, comp: Composicion) -> tuple[str, float]:
    """Devuelve `(clave_grupo, gramos_equivalentes_a_1_intercambio)` para un alimento."""
    clave = clasificar_grupo_intercambio(id_alimento, comp)
    gi = GRUPOS_INTERCAMBIO[clave]
    if id_alimento not in comp.tabla.index:
        return clave, 100.0
    val_100 = float(comp.tabla.at[id_alimento, gi.nutriente_pivote])
    if val_100 <= 0.1:
        # Fallback por kcal si el nutriente pivote es casi nulo (ej. queso curado con pocos HC)
        kcal_100 = float(comp.tabla.at[id_alimento, "kcal"])
        g_eq = (gi.kcal_ref / max(kcal_100, 1.0)) * 100.0
    else:
        g_eq = (gi.cantidad_pivote / val_100) * 100.0
    return clave, round(min(max(g_eq, 5.0), 400.0), 1)


def intercambios_de_items(items: pd.DataFrame, comp: Composicion) -> pd.DataFrame:
    """Añade columnas `grupo_intercambio`, `nombre_grupo` e `intercambios` a cada fila de `items`."""
    out = items.copy()
    claves, nombres, raciones, eq_1 = [], [], [], []
    for r in out.itertuples(index=False):
        fid = str(r.id)
        clave, g_eq = gramos_por_intercambio(fid, comp)
        gi = GRUPOS_INTERCAMBIO[clave]
        n_inter = float(r.gramos) / max(g_eq, 1e-6)
        claves.append(clave)
        nombres.append(gi.nombre)
        eq_1.append(g_eq)
        raciones.append(round(n_inter, 2))
    out["grupo_intercambio"] = claves
    out["nombre_grupo"] = nombres
    out["gramos_1_intercambio"] = eq_1
    out["intercambios"] = raciones
    return out


def intercambios_de_menu(menu: Menu, comp: Composicion) -> dict[str, Any]:
    """Calcula la tabla diaria, por comida y la media diaria de intercambios del menú."""
    enr = intercambios_de_items(menu.items, comp)
    orden_grupos = list(GRUPOS_INTERCAMBIO.keys())

    por_dia = (
        enr.pivot_table(index=["n_dia", "dia"], columns="grupo_intercambio", values="intercambios",
                        aggfunc="sum", fill_value=0.0)
        .reindex(columns=orden_grupos, fill_value=0.0)
        .round(2)
        .reset_index()
    )
    por_comida = (
        enr.pivot_table(index=["comida"], columns="grupo_intercambio", values="intercambios",
                        aggfunc="sum", fill_value=0.0)
        .reindex(columns=orden_grupos, fill_value=0.0)
    )
    n_dias = max(1, int(enr["n_dia"].nunique()))
    por_comida_media = (por_comida / n_dias).round(2).reset_index()
    media_diaria = {g: round(float(por_dia[g].mean()), 2) for g in orden_grupos}

    return {
        "detalle": enr,
        "por_dia": por_dia,
        "por_comida_media": por_comida_media,
        "media_diaria": media_diaria,
        "definiciones": {
            k: {
                "nombre": v.nombre,
                "kcal_ref": v.kcal_ref,
                "proteina_ref_g": v.proteina_ref_g,
                "hc_ref_g": v.hc_ref_g,
                "grasa_ref_g": v.grasa_ref_g,
                "descripcion": v.descripcion,
            }
            for k, v in GRUPOS_INTERCAMBIO.items()
        },
    }


def guia_intercambios(comp: Composicion, grupo: str | None = None) -> pd.DataFrame:
    """Tabla completa de equivalencias (1 intercambio = X g) para entrega al paciente."""
    filas = []
    for fid in comp.tabla.index:
        clave, g_eq = gramos_por_intercambio(fid, comp)
        if grupo and clave != grupo:
            continue
        meta = comp.tabla.loc[fid]
        factor = g_eq / 100.0
        filas.append(
            {
                "grupo_intercambio": clave,
                "grupo_nombre": GRUPOS_INTERCAMBIO[clave].nombre,
                "id": fid,
                "alimento": str(meta["nombre"]),
                "gramos_1_intercambio": g_eq,
                "kcal": round(float(meta["kcal"]) * factor, 1),
                "proteina_g": round(float(meta["proteina"]) * factor, 1),
                "hc_g": round(float(meta["hc"]) * factor, 1),
                "grasa_g": round(float(meta["grasa"]) * factor, 1),
                "leu_mg": round(float(meta["leu"]) * factor, 0),
                "potasio_mg": round(float(meta["potasio"]) * factor, 0),
                "fosforo_mg": round(float(meta["fosforo"]) * factor, 0),
            }
        )
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    return df.sort_values(["grupo_intercambio", "alimento"]).reset_index(drop=True)
