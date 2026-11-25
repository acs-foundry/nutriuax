"""Exportación del menú a Excel (una hoja por vista)."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

from .generador import Menu, comprobar
from .objetivos import Persona

COLS_ITEMS = ["n_dia", "dia", "comida", "nombre", "gramos", "kcal", "proteina", "grasa", "hc", "fibra",
              "leu", "ile", "val", "sodio", "potasio", "fosforo"]


def a_excel(menu: Menu, persona: Persona) -> bytes:
    buf = io.BytesIO()
    o = menu.objetivos
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        menu.items[COLS_ITEMS].round(1).to_excel(xw, sheet_name="Menú", index=False)
        menu.resumen.round(1).to_excel(xw, sheet_name="Resumen diario", index=False)
        comprobar(menu).to_excel(xw, sheet_name="Comprobación", index=False)
        compra = (menu.items.groupby("nombre", as_index=False)["gramos"].sum()
                  .sort_values("nombre").rename(columns={"gramos": "gramos_semana"}))
        compra.to_excel(xw, sheet_name="Lista de la compra", index=False)
        params = {
            "Fecha": date.today().isoformat(), "Código": persona.codigo, "Perfil": o.perfil.nombre,
            "Peso (kg)": persona.peso, "Masa magra (kg)": persona.masa_magra,
            "Energía objetivo (kcal)": round(o.kcal), "Proteína (g/día)": f"{o.proteina[0]:.0f}-{o.proteina[1]:.0f}",
            "kg de referencia para AA": o.kg_referencia,
            "Fuente de composición": menu.fuente,
            "Aviso": ("Tabla SEMILLA con aminoácidos estimados por patrón: no usar para resultados."
                      if menu.fuente != "fdc" else "USDA FoodData Central SR Legacy (CC0)."),
            **{f"Mín. {k}": round(v, 1) for k, v in o.minimos.items()},
            **{f"Máx. {k}": round(v, 1) for k, v in o.maximos.items()},
        }
        pd.DataFrame(list(params.items()), columns=["Parámetro", "Valor"]).to_excel(
            xw, sheet_name="Parámetros", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = max(
                    10, min(45, max(len(str(c.value or "")) for c in col) + 2))
    return buf.getvalue()
