"""Exportación de dossiers clínicos (Markdown, HTML XSS-safe, Excel clínico y puente ArtCraft Office).

Totalmente independiente y compatible con `anything-craft`:
- Genera Markdown y HTML autocontenidos listos para imprimir o entregar en consulta.
- Genera Excel clínico ampliado (pesos crudo/cocinado, intercambios EasyDiet, PRAL/EAA, fármacos).
- Si `wordcraft-cli` o `deckcraft-cli` están instalados en el sistema (opcionales, sin dependencia
  de CraftBio), compila automáticamente versiones `.docx`, `.pdf` o `.pptx` con `shell=False`.
"""
from __future__ import annotations

import html
import io
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from . import clinica, coccion, farmacos, intercambios
from .composicion import Composicion
from .generador import Menu, comprobar
from .objetivos import DIAS, NOMBRE_COMIDA, Persona


def _esc(val: Any) -> str:
    return html.escape(str(val), quote=True)


def generar_informe_markdown(
    menu: Menu,
    persona: Persona,
    comp: Composicion,
    medicamentos: list[str] | None = None,
    erc_doble_coccion: bool = False,
) -> str:
    """Genera un dossier clínico completo en Markdown listo para WordCraft o impresión."""
    o = menu.objetivos
    enr = coccion.enriquecer_menu_coccion(menu.items, comp, erc_doble_coccion=erc_doble_coccion)
    inter = intercambios.intercambios_de_menu(menu, comp)
    cal = clinica.calidad_proteica_menu(menu, edad=persona.edad)
    antro = clinica.evaluar_antropometria(persona)
    meds = farmacos.evaluar_interacciones(medicamentos or [], menu=menu)
    chk = comprobar(menu)
    n_ok = int(chk["ok"].sum())

    lineas: list[str] = [
        f"# Plan Nutricional Clínico · {o.perfil.nombre}",
        "",
        f"- **Fecha:** {date.today().isoformat()}",
        f"- **Código paciente:** `{persona.codigo}` (seudonimizado)",
        f"- **Antropometría:** IMC {antro['imc']} kg/m² ({antro['clasificacion_oms']}) · "
        f"Peso ideal Devine {antro['peso_ideal_devine_kg']} kg · Masa magra {antro['masa_magra_kg']} kg ({antro['masa_magra_origen']})",
        f"- **Objetivos diarios:** {o.kcal:.0f} kcal · Proteína {o.proteina[0]:.0f}–{o.proteina[1]:.0f} g/día · "
        f"Grasa {o.grasa_pct[0]}–{o.grasa_pct[1]} % · HC {o.hc_pct[0]}–{o.hc_pct[1]} %",
        f"- **Cumplimiento del menú:** {n_ok}/{len(chk)} criterios en rango · Fuente composición: `{menu.fuente}`",
        "",
        "## 1. Menú Diario (Pesos en Crudo y Cocinado)",
        "",
    ]

    for n_dia in sorted(enr["n_dia"].unique()):
        dia_nom = DIAS[(int(n_dia) - 1) % 7]
        lineas.append(f"### Día {n_dia} · {dia_nom}")
        lineas.append("")
        lineas.append("| Comida | Alimento | Crudo (g) | Cocinado (g) | Técnica | kcal | Prot (g) | Leu (mg) |")
        lineas.append("| :--- | :--- | ---: | ---: | :--- | ---: | ---: | ---: |")
        sub = enr[enr["n_dia"] == n_dia]
        for r in sub.itertuples(index=False):
            lineas.append(
                f"| {r.comida} | {r.nombre} | {r.gramos_crudo:.0f} | {r.gramos_cocinado:.0f} | "
                f"{r.tecnica} | {r.kcal:.0f} | {r.proteina:.1f} | {r.leu:.0f} |"
            )
        lineas.append("")

    lineas.extend([
        "## 2. Resumen Nutricional, BCAA y Calidad Proteica",
        "",
        f"- **Proteína media:** {cal['proteina_media_g']} g/día ({cal['proteina_animal_pct']} % animal / {cal['proteina_vegetal_pct']} % vegetal)",
        f"- **Puntuación Aminoacídica (WHO 2007 AAS):** {cal['aas_global_pct']} % (AA limitante: `{cal['aminoacido_limitante']}`)",
        f"- **Disparo anabólico de leucina (≥ {cal['umbral_leucina_toma_g']} g/toma principal):** "
        f"{cal['tomas_principales_con_umbral_leu']}/{cal['tomas_principales_totales']} tomas principales",
        f"- **Carga ácida renal potencial (PRAL medio):** {cal['pral_medio_meq_dia']} mEq/día",
        "",
        "| Día | kcal | Prot (g) | g/kg | %P | %G | %HC | Fibra | Leu (mg/kg) | Ile (mg/kg) | Val (mg/kg) | Na (mg) | K (mg) | P (mg) |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for r in menu.resumen.itertuples(index=False):
        lineas.append(
            f"| {r.dia} | {r.kcal:.0f} | {r.proteina:.1f} | {r.proteina_gkg:.2f} | "
            f"{r.pct_proteina:.1f} | {r.pct_grasa:.1f} | {r.pct_hc:.1f} | {r.fibra:.1f} | "
            f"{r.leu_mgkg:.1f} | {r.ile_mgkg:.1f} | {r.val_mgkg:.1f} | "
            f"{r.sodio:.0f} | {r.potasio:.0f} | {r.fosforo:.0f} |"
        )

    lineas.extend([
        "",
        "## 3. Distribución de Intercambios (Sistema Español)",
        "",
        "| Grupo de intercambio | Media diaria (intercambios/día) | Referencia (1 intercambio) |",
        "| :--- | ---: | :--- |",
    ])
    for clave, media in inter["media_diaria"].items():
        defin = inter["definiciones"][clave]
        lineas.append(f"| {defin['nombre']} | {media:.2f} | {defin['descripcion']} |")

    if meds["alertas"]:
        lineas.extend(["", "## 4. Alertas Fármaco-Nutriente", ""])
        for al in meds["alertas"]:
            lineas.append(f"### [{al['severidad'].upper()}] {al['farmaco']} ({al['clase']})")
            lineas.append(f"- **Mecanismo:** {al['mecanismo']}")
            lineas.append(f"- **Recomendación:** {al['recomendacion']}")
            for d in al["disparadores"]:
                lineas.append(f"- **Detectado en este menú:** {d}")
            lineas.append(f"- *Referencia:* {al['referencia']}")
            lineas.append("")

    compra = (
        enr.groupby("nombre", as_index=False)[["gramos_crudo", "gramos_cocinado"]]
        .sum()
        .sort_values("nombre")
    )
    lineas.extend([
        "",
        "## 5. Lista de la Compra Semanal (Peso Neto Crudo Estimado)",
        "",
        "| Alimento | Comprar en crudo (g) | Equivalente cocinado (g) |",
        "| :--- | ---: | ---: |",
    ])
    for r in compra.itertuples(index=False):
        lineas.append(f"| {r.nombre} | {r.gramos_crudo:.0f} | {r.gramos_cocinado:.0f} |")

    lineas.extend([
        "",
        "---",
        "*Generado localmente por NutriUAX (MIT). Herramienta de apoyo a la decisión dietética; validar clínicamente antes de prescribir.*",
    ])
    return "\n".join(lineas) + "\n"


def generar_informe_html(
    menu: Menu,
    persona: Persona,
    comp: Composicion,
    medicamentos: list[str] | None = None,
    erc_doble_coccion: bool = False,
) -> str:
    """Genera un informe HTML clínico autocontenido y seguro frente a XSS (`html.escape`)."""
    o = menu.objetivos
    enr = coccion.enriquecer_menu_coccion(menu.items, comp, erc_doble_coccion=erc_doble_coccion)
    inter = intercambios.intercambios_de_menu(menu, comp)
    cal = clinica.calidad_proteica_menu(menu, edad=persona.edad)
    antro = clinica.evaluar_antropometria(persona)
    meds = farmacos.evaluar_interacciones(medicamentos or [], menu=menu)

    filas_res = "".join(
        f"<tr><td>{_esc(r.dia)}</td><td>{r.kcal:.0f}</td><td>{r.proteina:.1f}</td><td>{r.proteina_gkg:.2f}</td>"
        f"<td>{r.pct_proteina:.1f}%</td><td>{r.pct_grasa:.1f}%</td><td>{r.pct_hc:.1f}%</td><td>{r.fibra:.1f}</td>"
        f"<td>{r.leu_mgkg:.1f}</td><td>{r.ile_mgkg:.1f}</td><td>{r.val_mgkg:.1f}</td>"
        f"<td>{r.sodio:.0f}</td><td>{r.potasio:.0f}</td><td>{r.fosforo:.0f}</td></tr>"
        for r in menu.resumen.itertuples(index=False)
    )

    dias_html = []
    for n_dia in sorted(enr["n_dia"].unique()):
        dia_nom = DIAS[(int(n_dia) - 1) % 7]
        sub = enr[enr["n_dia"] == n_dia]
        filas = "".join(
            f"<tr><td>{_esc(r.comida)}</td><td>{_esc(r.nombre)}</td><td>{r.gramos_crudo:.0f} g</td>"
            f"<td>{r.gramos_cocinado:.0f} g</td><td>{_esc(r.tecnica)}</td><td>{r.kcal:.0f}</td>"
            f"<td>{r.proteina:.1f}</td><td>{r.leu:.0f}</td></tr>"
            for r in sub.itertuples(index=False)
        )
        dias_html.append(
            f"<h3>Día {int(n_dia)} · {_esc(dia_nom)}</h3>"
            f"<table><thead><tr><th>Comida</th><th>Alimento</th><th>Crudo</th><th>Cocinado</th>"
            f"<th>Técnica</th><th>kcal</th><th>Prot (g)</th><th>Leu (mg)</th></tr></thead>"
            f"<tbody>{filas}</tbody></table>"
        )

    inter_html = "".join(
        f"<tr><td>{_esc(inter['definiciones'][k]['nombre'])}</td><td>{v:.2f}</td>"
        f"<td>{_esc(inter['definiciones'][k]['descripcion'])}</td></tr>"
        for k, v in inter["media_diaria"].items()
    )

    meds_html = ""
    if meds["alertas"]:
        cards = "".join(
            f"<div class='alert {_esc(al['severidad'])}'><b>[{_esc(al['severidad'].upper())}] {_esc(al['farmaco'])}</b>"
            f"<p>{_esc(al['mecanismo'])}</p><p><b>Recomendación:</b> {_esc(al['recomendacion'])}</p>"
            + ("".join(f"<p class='trig'>• {_esc(d)}</p>" for d in al["disparadores"]))
            + f"<small>{_esc(al['referencia'])}</small></div>"
            for al in meds["alertas"]
        )
        meds_html = f"<h2>Alertas Fármaco-Nutriente</h2>{cards}"

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NutriUAX · Plan Nutricional {_esc(persona.codigo)}</title>
<style>
  body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; color: #1E293B; max-width: 1020px; margin: 24px auto; padding: 0 18px; line-height: 1.45; }}
  header {{ background: linear-gradient(120deg, #0F6B5E, #164E63); color: #fff; border-radius: 14px; padding: 20px 26px; margin-bottom: 20px; }}
  header h1 {{ margin: 0 0 6px; font-size: 1.55rem; }} header p {{ margin: 0; opacity: .92; }}
  .kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0 22px; }}
  .kpi {{ border: 1px solid #CBD5E1; border-left: 4px solid #0F6B5E; border-radius: 10px; padding: 10px 14px; background: #F8FAFC; }}
  .kpi small {{ color: #64748B; text-transform: uppercase; font-size: .72rem; font-weight: 700; display: block; }}
  .kpi b {{ font-size: 1.15rem; }}
  h2 {{ color: #0F6B5E; border-bottom: 2px solid #E2E8F0; padding-bottom: 4px; margin-top: 26px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0 18px; font-size: .88rem; }}
  th, td {{ border: 1px solid #E2E8F0; padding: 6px 8px; text-align: left; }}
  th {{ background: #F1F5F9; font-weight: 600; }}
  .alert {{ border-radius: 10px; padding: 12px 16px; margin: 10px 0; border-left: 5px solid #94A3B8; background: #F8FAFC; }}
  .alert.alta {{ border-left-color: #DC2626; background: #FEF2F2; }}
  .alert.media {{ border-left-color: #D97706; background: #FFFBEB; }}
  .trig {{ color: #991B1B; margin: 4px 0; }}
  footer {{ margin-top: 30px; padding-top: 12px; border-top: 1px solid #E2E8F0; font-size: .8rem; color: #64748B; }}
</style></head><body>
<header>
  <h1>NutriUAX · Plan Nutricional Clínico</h1>
  <p>Perfil: <b>{_esc(o.perfil.nombre)}</b> · Paciente: <b>{_esc(persona.codigo)}</b> · Fecha: {_esc(date.today().isoformat())}</p>
</header>
<div class="kpis">
  <div class="kpi"><small>Energía objetivo</small><b>{o.kcal:.0f} kcal/día</b></div>
  <div class="kpi"><small>IMC ({_esc(antro['clasificacion_oms'])})</small><b>{antro['imc']} kg/m²</b></div>
  <div class="kpi"><small>Calidad proteica (WHO AAS)</small><b>{cal['aas_global_pct']}% ({_esc(cal['aminoacido_limitante'])})</b></div>
  <div class="kpi"><small>PRAL renal medio</small><b>{cal['pral_medio_meq_dia']} mEq/d</b></div>
</div>
<h2>Resumen Diario y Aminoácidos Ramificados (BCAA)</h2>
<table><thead><tr><th>Día</th><th>kcal</th><th>Prot</th><th>g/kg</th><th>%P</th><th>%G</th><th>%HC</th><th>Fibra</th>
<th>Leu/kg</th><th>Ile/kg</th><th>Val/kg</th><th>Na</th><th>K</th><th>P</th></tr></thead><tbody>{filas_res}</tbody></table>
<h2>Intercambios Diarios Medios</h2>
<table><thead><tr><th>Grupo</th><th>Intercambios/día</th><th>Equivalencia</th></tr></thead><tbody>{inter_html}</tbody></table>
{meds_html}
<h2>Menú Detallado (Crudo y Cocinado)</h2>
{"".join(dias_html)}
<footer>NutriUAX · Software abierto (MIT) · Composición: USDA FoodData Central SR Legacy (CC0). Herramienta de apoyo a la decisión dietética; validar clínicamente antes de prescribir.</footer>
</body></html>"""


def exportar_excel_clinico(
    menu: Menu,
    persona: Persona,
    comp: Composicion,
    medicamentos: list[str] | None = None,
    erc_doble_coccion: bool = False,
) -> bytes:
    """Excel clínico ampliado (8 hojas): Menú Crudo/Cocinado, Intercambios, Resumen+PRAL,
    Comprobación, Fármacos, Lista de Compra Crudo, Guía de Intercambios y Parámetros."""
    buf = io.BytesIO()
    o = menu.objetivos
    enr = coccion.enriquecer_menu_coccion(menu.items, comp, erc_doble_coccion=erc_doble_coccion)
    inter = intercambios.intercambios_de_menu(menu, comp)
    cal = clinica.calidad_proteica_menu(menu, edad=persona.edad)
    meds = farmacos.evaluar_interacciones(medicamentos or [], menu=menu)
    guia = intercambios.guia_intercambios(comp)

    res_ext = menu.resumen.copy()
    res_ext["pral_meq"] = cal["pral_por_dia"]

    cols_menu = [
        "n_dia", "dia", "comida", "nombre", "gramos_crudo", "gramos_cocinado", "tecnica",
        "kcal", "proteina", "grasa", "hc", "fibra", "leu", "ile", "val", "sodio", "potasio", "fosforo",
    ]
    compra = (
        enr.groupby("nombre", as_index=False)[["gramos_crudo", "gramos_cocinado"]]
        .sum()
        .sort_values("nombre")
    )

    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        enr[cols_menu].round(1).to_excel(xw, sheet_name="Menú Crudo-Cocinado", index=False)
        inter["por_dia"].to_excel(xw, sheet_name="Intercambios", index=False)
        res_ext.round(1).to_excel(xw, sheet_name="Resumen y PRAL", index=False)
        comprobar(menu).to_excel(xw, sheet_name="Comprobación", index=False)
        pd.DataFrame(meds["alertas"] or [{"info": "Sin medicamentos declarados"}]).to_excel(
            xw, sheet_name="Fármaco-Nutriente", index=False
        )
        compra.round(1).to_excel(xw, sheet_name="Lista Compra Crudo", index=False)
        guia.to_excel(xw, sheet_name="Guía Intercambios", index=False)
        params = {
            "Fecha": date.today().isoformat(),
            "Código": persona.codigo,
            "Perfil": o.perfil.nombre,
            "Energía objetivo (kcal)": round(o.kcal),
            "Proteína (g/día)": f"{o.proteina[0]:.0f}-{o.proteina[1]:.0f}",
            "AAS WHO 2007 (%)": cal["aas_global_pct"],
            "Aminoácido limitante": cal["aminoacido_limitante"],
            "PRAL medio (mEq/día)": cal["pral_medio_meq_dia"],
            "Tomas principales ≥ umbral Leu": f"{cal['tomas_principales_con_umbral_leu']}/{cal['tomas_principales_totales']}",
            "Fuente composición": menu.fuente,
        }
        pd.DataFrame(list(params.items()), columns=["Parámetro", "Valor"]).to_excel(
            xw, sheet_name="Parámetros", index=False
        )
        for ws in xw.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = max(
                    10, min(46, max(len(str(c.value or "")) for c in col) + 2)
                )
    return buf.getvalue()


def herramientas_artcraft_disponibles() -> dict[str, str | None]:
    """Detecta CLIs opcionales del ecosistema ArtCraft Office instaladas en PATH."""
    return {
        "wordcraft_cli": shutil.which("wordcraft-cli"),
        "gridcraft_cli": shutil.which("gridcraft-cli"),
        "deckcraft_cli": shutil.which("deckcraft-cli"),
    }


def exportar_dossier_completo(
    menu: Menu,
    persona: Persona,
    comp: Composicion,
    directorio_salida: Path,
    prefijo: str | None = None,
    medicamentos: list[str] | None = None,
    erc_doble_coccion: bool = False,
    formatos: tuple[str, ...] = ("md", "html", "xlsx", "json", "docx", "pdf"),
) -> dict[str, Any]:
    """Exporta un dossier clínico multipropósito (MD/HTML/XLSX/JSON + DOCX/PDF vía wordcraft-cli)."""
    directorio_salida.mkdir(parents=True, exist_ok=True)
    stem = prefijo or f"dossier_{persona.codigo}_{menu.objetivos.perfil.clave}"
    # Sanear el nombre base
    stem = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in stem)
    archivos: dict[str, str] = {}
    avisos: list[str] = []

    md_texto = generar_informe_markdown(menu, persona, comp, medicamentos, erc_doble_coccion)
    md_path = directorio_salida / f"{stem}.md"
    if "md" in formatos or "docx" in formatos or "pdf" in formatos:
        md_path.write_text(md_texto, encoding="utf-8")
        if "md" in formatos:
            archivos["md"] = str(md_path)

    if "html" in formatos:
        html_path = directorio_salida / f"{stem}.html"
        html_path.write_text(
            generar_informe_html(menu, persona, comp, medicamentos, erc_doble_coccion),
            encoding="utf-8",
        )
        archivos["html"] = str(html_path)

    if "xlsx" in formatos:
        xlsx_path = directorio_salida / f"{stem}.xlsx"
        xlsx_path.write_bytes(exportar_excel_clinico(menu, persona, comp, medicamentos, erc_doble_coccion))
        archivos["xlsx"] = str(xlsx_path)

    if "json" in formatos:
        enr = coccion.enriquecer_menu_coccion(menu.items, comp, erc_doble_coccion=erc_doble_coccion)
        inter = intercambios.intercambios_de_menu(menu, comp)
        payload = {
            "codigo": persona.codigo,
            "perfil": menu.objetivos.perfil.clave,
            "fuente": menu.fuente,
            "estado_solver": menu.estado,
            "objetivos": menu.objetivos.como_dict(),
            "calidad_proteica": clinica.calidad_proteica_menu(menu, edad=persona.edad),
            "intercambios_media": inter["media_diaria"],
            "farmacos": farmacos.evaluar_interacciones(medicamentos or [], menu=menu),
            "resumen_diario": menu.resumen.round(2).to_dict(orient="records"),
            "items": enr.round(2).to_dict(orient="records"),
        }
        json_path = directorio_salida / f"{stem}.json"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        archivos["json"] = str(json_path)

    wc = shutil.which("wordcraft-cli")
    for fmt in ("docx", "pdf"):
        if fmt not in formatos:
            continue
        if not wc:
            avisos.append(f"Omitido .{fmt}: `wordcraft-cli` no está en PATH (opcional).")
            continue
        out_file = directorio_salida / f"{stem}.{fmt}"
        proc = subprocess.run(
            [wc, "convert", str(md_path), str(out_file)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode == 0 and out_file.exists():
            archivos[fmt] = str(out_file)
        else:
            avisos.append(f"wordcraft-cli no pudo generar .{fmt}: {(proc.stderr or proc.stdout).strip()[:200]}")

    return {
        "directorio": str(directorio_salida),
        "archivos": archivos,
        "artcraft_detectado": herramientas_artcraft_disponibles(),
        "avisos": avisos,
    }
