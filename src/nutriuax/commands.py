"""Symmetrical command registry shared by `nutriuax-cli` (run/commands/describe) and `nutriuax-cli mcp`.

Follows the Anything-Craft (`craft-anything` / `craft_box.py`) architecture: every domain operation
is exposed as a declarative, self-describing command with JSON Schema input validation and sandboxed
filesystem access (`PathSandbox`). Zero dependency on CraftBio.
"""
from __future__ import annotations

import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pulp

from . import (
    __version__,
    api,
    base_fdc,
    clinica,
    coccion,
    composicion,
    encuestas,
    farmacos,
    generador,
    intercambios,
    objetivos,
    office,
    recetas,
)
from .sandbox import PathSandbox


@dataclass(frozen=True)
class CommandSpec:
    id: str
    summary: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any], PathSandbox], dict[str, Any]]


def _persona_from_args(args: dict[str, Any]) -> objetivos.Persona:
    return objetivos.Persona(
        codigo=str(args.get("codigo", "P001")),
        sexo=str(args.get("sexo", "M")).upper(),
        edad=int(args.get("edad", 30)),
        peso=float(args.get("peso", 70.0)),
        talla=float(args.get("talla", 170.0)),
        factor_actividad=float(args.get("actividad", 1.55)),
        masa_magra=float(args["masa_magra"]) if args.get("masa_magra") else None,
        kcal_manual=float(args["kcal_manual"]) if args.get("kcal_manual") else None,
    )


def _cmd_doctor(args: dict[str, Any], sandbox: PathSandbox) -> dict[str, Any]:
    comp = composicion.cargar()
    fdc_full = base_fdc.cargar_completa()
    rec_list = recetas.cargar_recetas()
    solver_ok = False
    try:
        solver_ok = bool(pulp.HiGHS(msg=False).available())
    except Exception:
        solver_ok = False
    return {
        "app": "nutriuax",
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pulp_version": getattr(pulp, "__version__", "unknown"),
        "highs_available": solver_ok,
        "catalog_foods": int(len(comp.tabla)),
        "catalog_source": comp.fuente,
        "fdc_full_foods": int(len(fdc_full)) if fdc_full is not None else 0,
        "builtin_recipes": int(len(rec_list)),
        "profiles_count": int(len(objetivos.PERFILES)),
        "drug_rules_count": int(len(farmacos.VADEMECUM)),
        "artcraft_office": office.herramientas_artcraft_disponibles(),
        "sandbox_read_roots": [str(p) for p in sandbox.read_roots],
        "sandbox_write_roots": [str(p) for p in sandbox.write_roots],
        "ok": solver_ok and len(comp.tabla) > 0,
    }


def _cmd_profiles_list(args: dict[str, Any], _sandbox: PathSandbox) -> dict[str, Any]:
    ambito = args.get("ambito")
    out = []
    for clave, pf in objetivos.PERFILES.items():
        if ambito and pf.ambito != ambito:
            continue
        out.append(
            {
                "clave": clave,
                "nombre": pf.nombre,
                "ambito": pf.ambito,
                "descripcion": pf.descripcion,
                "proteina_gkg": list(pf.proteina_gkg),
                "grasa_pct": list(pf.grasa_pct),
                "hc_pct": list(pf.hc_pct),
                "sodio_max": pf.sodio_max,
                "potasio_max": pf.potasio_max,
                "fosforo_max": pf.fosforo_max,
                "fuentes": list(pf.fuentes),
            }
        )
    return {"total": len(out), "perfiles": out}


def _cmd_foods_search(args: dict[str, Any], _sandbox: PathSandbox) -> dict[str, Any]:
    q = str(args.get("query", "")).strip()
    if not q:
        raise ValueError("`query` es obligatorio.")
    limit = max(1, min(int(args.get("limit", 15)), 100))
    fuente = str(args.get("source", "both")).lower()
    resultados: list[dict[str, Any]] = []

    if fuente in ("catalog", "both"):
        comp = composicion.cargar()
        ql = q.lower()
        sub = comp.tabla[
            comp.tabla["nombre"].str.lower().str.contains(ql, na=False, regex=False)
            | comp.tabla.index.str.lower().str.contains(ql, na=False, regex=False)
        ].head(limit)
        for fid, r in sub.iterrows():
            resultados.append(
                {
                    "source": "catalog",
                    "id": str(fid),
                    "nombre": str(r["nombre"]),
                    "grupo": str(r["grupo"]),
                    "kcal": round(float(r["kcal"]), 1),
                    "proteina": round(float(r["proteina"]), 1),
                    "grasa": round(float(r["grasa"]), 1),
                    "hc": round(float(r["hc"]), 1),
                    "leu_mg": round(float(r["leu"]), 0),
                    "ile_mg": round(float(r["ile"]), 0),
                    "val_mg": round(float(r["val"]), 0),
                    "potasio_mg": round(float(r["potasio"]), 0),
                    "fosforo_mg": round(float(r["fosforo"]), 0),
                }
            )

    if fuente in ("fdc", "both") and len(resultados) < limit:
        restante = limit - len(resultados)
        fdc_base = base_fdc.cargar_completa()
        df_fdc = base_fdc.buscar(q, n=restante, base=fdc_base)
        for r in df_fdc.itertuples(index=False):
            ndb = str(r.ndb)
            row = fdc_base.loc[ndb] if (fdc_base is not None and ndb in fdc_base.index) else {}
            def _opt_f(col: str, ndig: int = 1) -> float | None:
                v = row.get(col) if hasattr(row, "get") else None
                if v is None or v != v:
                    return None
                return round(float(v), ndig)
            resultados.append(
                {
                    "source": "fdc",
                    "id": f"fdc_{ndb}",
                    "ndb": ndb,
                    "nombre": str(r.descripcion),
                    "categoria": str(r.categoria),
                    "kcal": _opt_f("kcal", 1),
                    "proteina": _opt_f("proteina", 1),
                    "grasa": _opt_f("grasa", 1),
                    "hc": _opt_f("hc", 1),
                    "leu_mg": _opt_f("leu", 0),
                    "tiene_aa": bool(r.tiene_aa),
                }
            )
    return {"query": q, "total": len(resultados), "resultados": resultados}


def _cmd_clinical_anthropometry(args: dict[str, Any], _sandbox: PathSandbox) -> dict[str, Any]:
    persona = _persona_from_args(args)
    res = clinica.evaluar_antropometria(
        persona,
        cintura_cm=float(args["cintura_cm"]) if args.get("cintura_cm") else None,
        cadera_cm=float(args["cadera_cm"]) if args.get("cadera_cm") else None,
    )
    if args.get("perdida_peso_pct_3_6m") is not None or args.get("efecto_enfermedad_aguda"):
        res["must"] = clinica.cribado_must(
            imc=res["imc"],
            perdida_peso_pct_3_6m=float(args.get("perdida_peso_pct_3_6m", 0.0)),
            efecto_enfermedad_aguda=bool(args.get("efecto_enfermedad_aguda", False)),
        )
    if args.get("mna_sf"):
        m = args["mna_sf"]
        res["mna_sf"] = clinica.cribado_mna_sf(
            int(m["ingesta_0_2"]),
            int(m["perdida_peso_0_3"]),
            int(m["movilidad_0_2"]),
            int(m["estres_agudo_0_2"]),
            int(m["neuropsic_0_2"]),
            int(m["imc_o_pantorrilla_0_3"]),
        )
    return res


def _cmd_diet_generate(args: dict[str, Any], _sandbox: PathSandbox) -> dict[str, Any]:
    clave = str(args.get("perfil", "uax_mediterranea"))
    if clave not in objetivos.PERFILES:
        raise ValueError(f"Perfil desconocido «{clave}». Disponibles: {list(objetivos.PERFILES)}")
    persona = _persona_from_args(args)
    perfil = objetivos.PERFILES[clave]
    if perfil.ambito == "hogar":
        from .seguridad import objetivos_seguros

        obj = objetivos_seguros(persona, perfil)
    else:
        obj = objetivos.calcular_objetivos(persona, perfil)
    comp = composicion.cargar()
    dias = max(1, min(int(args.get("dias", 3)), 7))
    semilla = int(args.get("semilla", 0))
    vetados = set(args.get("vetados", []))
    erc_doble = bool(args.get("erc_doble_coccion", clave in ("erc_nd", "erc_hd")))
    menu = generador.generar(comp, obj, dias=dias, semilla=semilla, vetados=vetados, tiempo_max=int(args.get("tiempo_max", 25)))
    enr = coccion.enriquecer_menu_coccion(menu.items, comp, erc_doble_coccion=erc_doble)
    inter = intercambios.intercambios_de_menu(menu, comp)
    cal = clinica.calidad_proteica_menu(menu, edad=persona.edad)
    chk = generador.comprobar(menu)
    meds = farmacos.evaluar_interacciones(list(args.get("medicamentos", [])), menu=menu)
    return {
        "estado_solver": menu.estado,
        "fuente": menu.fuente,
        "perfil": clave,
        "objetivos": obj.como_dict(),
        "criterios_en_rango": f"{int(chk['ok'].sum())}/{len(chk)}",
        "resumen_diario": menu.resumen.round(2).to_dict(orient="records"),
        "intercambios_media": inter["media_diaria"],
        "calidad_proteica": cal,
        "farmacos": meds,
        "items": enr.round(2).to_dict(orient="records"),
    }


def _cmd_household_generate(args: dict[str, Any], sandbox: PathSandbox) -> dict[str, Any]:
    if "entrada_path" in args and args["entrada_path"]:
        raw_txt = sandbox.read_text_bounded(args["entrada_path"])
        entrada = json.loads(raw_txt)
    elif "entrada" in args and isinstance(args["entrada"], dict):
        entrada = args["entrada"]
    else:
        raise ValueError("Proporciona `entrada` (dict JSON v1) o `entrada_path` (ruta dentro de read-root).")
    rec_path: Path | None = None
    if args.get("recetas_path"):
        rec_path = sandbox.check_read(args["recetas_path"])
    salida = api.generar_menu(entrada, rec_path)
    if args.get("salida_path"):
        out_p = sandbox.check_write(args["salida_path"])
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(salida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        salida["escrito_en"] = str(out_p)
    return salida


def _cmd_exchanges_guide(args: dict[str, Any], _sandbox: PathSandbox) -> dict[str, Any]:
    comp = composicion.cargar()
    grupo = args.get("grupo")
    df = intercambios.guia_intercambios(comp, grupo=grupo)
    return {
        "grupos": {k: v.nombre for k, v in intercambios.GRUPOS_INTERCAMBIO.items()},
        "total": int(len(df)),
        "equivalencias": df.to_dict(orient="records"),
    }


def _cmd_drugs_check(args: dict[str, Any], _sandbox: PathSandbox) -> dict[str, Any]:
    if args.get("listar"):
        return {"total": len(farmacos.VADEMECUM), "farmacos": farmacos.listar_farmacos()}
    meds = list(args.get("medicamentos", []))
    resumen = args.get("resumen_diario")
    return farmacos.evaluar_interacciones(meds, resumen_diario=resumen)


def _cmd_survey_diary(args: dict[str, Any], _sandbox: PathSandbox) -> dict[str, Any]:
    comp = composicion.cargar()
    return encuestas.calcular_registro_diario(
        registros=list(args.get("registros", [])),
        comp=comp,
        peso_kg=float(args.get("peso_kg", 70.0)),
        masa_magra_kg=float(args["masa_magra_kg"]) if args.get("masa_magra_kg") else None,
    )


def _cmd_survey_ffq(args: dict[str, Any], _sandbox: PathSandbox) -> dict[str, Any]:
    comp = composicion.cargar()
    return encuestas.calcular_ffq_predimed(
        respuestas=list(args.get("respuestas", [])),
        comp=comp,
        peso_kg=float(args.get("peso_kg", 70.0)),
        ventana=str(args.get("ventana", "1_ano")),
    )


def _cmd_survey_adherence(args: dict[str, Any], _sandbox: PathSandbox) -> dict[str, Any]:
    out: dict[str, Any] = {}
    medas_pts = args.get("medas14_puntos")
    if isinstance(args.get("medas14_respuestas"), dict):
        med = encuestas.calcular_medas14(args["medas14_respuestas"])
        out["medas14"] = {"puntuacion": med.puntuacion, "categoria": med.categoria, "detalle": med.detalle}
        medas_pts = med.puntuacion
    if args.get("proteinas_diarias_g"):
        adh = encuestas.evaluar_adherencia(
            participante=str(args.get("participante", "P001")),
            brazo=str(args.get("brazo", "mediterranea")),
            proteinas_diarias_g=[float(x) for x in args["proteinas_diarias_g"]],
            kcal_diarias=[float(x) for x in args.get("kcal_diarias", [])],
            peso_kg=float(args.get("peso_kg", 70.0)),
            nuu_g_dia=float(args["nuu_g_dia"]) if args.get("nuu_g_dia") is not None else None,
            medas14_puntos=int(medas_pts) if medas_pts is not None else None,
        )
        out["adherencia"] = adh.__dict__
    elif args.get("nuu_g_dia") is not None:
        out["maroni_proteina_g"] = encuestas.proteina_maroni(
            float(args["nuu_g_dia"]), float(args.get("peso_kg", 70.0))
        )
    if not out:
        raise ValueError("Proporciona `medas14_respuestas`, `proteinas_diarias_g` o `nuu_g_dia`.")
    return out


def _cmd_report_export(args: dict[str, Any], sandbox: PathSandbox) -> dict[str, Any]:
    out_dir_raw = args.get("output_dir")
    if not out_dir_raw:
        raise ValueError("`output_dir` es obligatorio.")
    out_dir = sandbox.check_write(out_dir_raw)
    clave = str(args.get("perfil", "uax_mediterranea"))
    if clave not in objetivos.PERFILES:
        raise ValueError(f"Perfil desconocido «{clave}».")
    persona = _persona_from_args(args)
    perfil = objetivos.PERFILES[clave]
    if perfil.ambito == "hogar":
        from .seguridad import objetivos_seguros

        obj = objetivos_seguros(persona, perfil)
    else:
        obj = objetivos.calcular_objetivos(persona, perfil)
    comp = composicion.cargar()
    menu = generador.generar(
        comp,
        obj,
        dias=max(1, min(int(args.get("dias", 3)), 7)),
        semilla=int(args.get("semilla", 0)),
        vetados=set(args.get("vetados", [])),
        tiempo_max=int(args.get("tiempo_max", 25)),
    )
    formatos = tuple(args.get("formatos", ["md", "html", "xlsx", "json", "docx", "pdf"]))
    return office.exportar_dossier_completo(
        menu=menu,
        persona=persona,
        comp=comp,
        directorio_salida=out_dir,
        prefijo=args.get("prefijo"),
        medicamentos=list(args.get("medicamentos", [])),
        erc_doble_coccion=bool(args.get("erc_doble_coccion", clave in ("erc_nd", "erc_hd"))),
        formatos=formatos,
    )


COMMANDS: dict[str, CommandSpec] = {
    c.id: c
    for c in [
        CommandSpec(
            id="doctor",
            summary="Diagnóstico del entorno: solver HiGHS, catálogo USDA FDC, recetas MIT, perfiles y puente ArtCraft Office.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_cmd_doctor,
        ),
        CommandSpec(
            id="profiles.list",
            summary="Lista los perfiles dietéticos y clínicos disponibles (estudio, clínico y hogar) con sus rangos y fuentes.",
            input_schema={
                "type": "object",
                "properties": {"ambito": {"type": "string", "enum": ["estudio", "clinico", "hogar"]}},
                "additionalProperties": False,
            },
            handler=_cmd_profiles_list,
        ),
        CommandSpec(
            id="foods.search",
            summary="Busca alimentos en el catálogo curado y en la base completa USDA FoodData Central (~7.800 alimentos).",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "Término en español o inglés"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 15},
                    "source": {"type": "string", "enum": ["catalog", "fdc", "both"], "default": "both"},
                },
                "additionalProperties": False,
            },
            handler=_cmd_foods_search,
        ),
        CommandSpec(
            id="clinical.anthropometry",
            summary="Evalúa IMC OMS, cintura/talla, peso ideal Devine, masa magra Boer, 5 ecuaciones TMB/EER y cribados MUST/MNA-SF.",
            input_schema={
                "type": "object",
                "required": ["sexo", "edad", "peso", "talla"],
                "properties": {
                    "codigo": {"type": "string", "default": "P001"},
                    "sexo": {"type": "string", "enum": ["H", "M"]},
                    "edad": {"type": "integer", "minimum": 2, "maximum": 115},
                    "peso": {"type": "number", "minimum": 10, "maximum": 300},
                    "talla": {"type": "number", "minimum": 60, "maximum": 240},
                    "actividad": {"type": "number", "default": 1.55},
                    "masa_magra": {"type": "number"},
                    "cintura_cm": {"type": "number"},
                    "cadera_cm": {"type": "number"},
                    "perdida_peso_pct_3_6m": {"type": "number"},
                    "efecto_enfermedad_aguda": {"type": "boolean"},
                    "mna_sf": {"type": "object"},
                },
                "additionalProperties": False,
            },
            handler=_cmd_clinical_anthropometry,
        ),
        CommandSpec(
            id="diet.generate",
            summary="Genera un menú optimizado por MILP (PuLP+HiGHS) con control de BCAA, minerales, pesos crudo/cocinado, intercambios, PRAL y alertas de fármacos.",
            input_schema={
                "type": "object",
                "properties": {
                    "codigo": {"type": "string", "default": "P001"},
                    "perfil": {"type": "string", "default": "uax_mediterranea"},
                    "sexo": {"type": "string", "enum": ["H", "M"], "default": "M"},
                    "edad": {"type": "integer", "default": 30},
                    "peso": {"type": "number", "default": 70.0},
                    "talla": {"type": "number", "default": 170.0},
                    "actividad": {"type": "number", "default": 1.55},
                    "masa_magra": {"type": "number"},
                    "kcal_manual": {"type": "number"},
                    "dias": {"type": "integer", "minimum": 1, "maximum": 7, "default": 3},
                    "semilla": {"type": "integer", "default": 0},
                    "vetados": {"type": "array", "items": {"type": "string"}},
                    "medicamentos": {"type": "array", "items": {"type": "string"}},
                    "erc_doble_coccion": {"type": "boolean"},
                    "tiempo_max": {"type": "integer", "default": 25},
                },
                "additionalProperties": False,
            },
            handler=_cmd_diet_generate,
        ),
        CommandSpec(
            id="household.generate",
            summary="Genera un menú semanal compartido para un hogar de N miembros (contrato JSON v1 con alérgenos UE-14 y batch cooking).",
            input_schema={
                "type": "object",
                "properties": {
                    "entrada": {"type": "object", "description": "Documento JSON v1 conforme a schema/entrada_v1.json"},
                    "entrada_path": {"type": "string", "description": "Ruta a JSON v1 dentro de --automation-read-root"},
                    "recetas_path": {"type": "string", "description": "Biblioteca de recetas opcional dentro de read-root"},
                    "salida_path": {"type": "string", "description": "Ruta de salida opcional dentro de --automation-write-root"},
                },
                "additionalProperties": False,
            },
            handler=_cmd_household_generate,
        ),
        CommandSpec(
            id="exchanges.guide",
            summary="Devuelve la tabla de equivalencias del sistema español de intercambios (1 intercambio = X gramos por alimento).",
            input_schema={
                "type": "object",
                "properties": {
                    "grupo": {
                        "type": "string",
                        "enum": list(intercambios.GRUPOS_INTERCAMBIO.keys()),
                    }
                },
                "additionalProperties": False,
            },
            handler=_cmd_exchanges_guide,
        ),
        CommandSpec(
            id="drugs.check",
            summary="Consulta el vademécum de 24 fármacos/clases y evalúa interacciones fármaco-nutriente frente a una ingesta diaria.",
            input_schema={
                "type": "object",
                "properties": {
                    "listar": {"type": "boolean", "default": False},
                    "medicamentos": {"type": "array", "items": {"type": "string"}},
                    "resumen_diario": {"type": "object"},
                },
                "additionalProperties": False,
            },
            handler=_cmd_drugs_check,
        ),
        CommandSpec(
            id="survey.diary",
            summary="Calcula un registro dietético de N días (p. ej. 3 días) con conversión crudo/cocinado y aminoácidos esenciales (Leu/Ile/Val).",
            input_schema={
                "type": "object",
                "required": ["registros", "peso_kg"],
                "properties": {
                    "registros": {"type": "array", "items": {"type": "object"}},
                    "peso_kg": {"type": "number"},
                    "masa_magra_kg": {"type": "number"},
                },
                "additionalProperties": False,
            },
            handler=_cmd_survey_diary,
        ),
        CommandSpec(
            id="survey.ffq",
            summary="Calcula ingesta media diaria desde un FFQ PREDIMED-Plus de 9 categorías de frecuencia (ventana 1_ano u 8_semanas).",
            input_schema={
                "type": "object",
                "required": ["respuestas"],
                "properties": {
                    "respuestas": {"type": "array", "items": {"type": "object"}},
                    "peso_kg": {"type": "number", "default": 70.0},
                    "ventana": {"type": "string", "enum": ["1_ano", "8_semanas"], "default": "1_ano"},
                },
                "additionalProperties": False,
            },
            handler=_cmd_survey_ffq,
        ),
        CommandSpec(
            id="survey.adherence",
            summary="Evalúa MEDAS-14, proteína estimada por Maroni (NUU 24h) y clasificación combinada de adherencia según config/adherencia.toml.",
            input_schema={
                "type": "object",
                "properties": {
                    "participante": {"type": "string", "default": "P001"},
                    "brazo": {"type": "string", "enum": ["mediterranea", "hiperproteica"], "default": "mediterranea"},
                    "proteinas_diarias_g": {"type": "array", "items": {"type": "number"}},
                    "kcal_diarias": {"type": "array", "items": {"type": "number"}},
                    "peso_kg": {"type": "number", "default": 70.0},
                    "nuu_g_dia": {"type": "number"},
                    "medas14_puntos": {"type": "integer"},
                    "medas14_respuestas": {"type": "object"},
                },
                "additionalProperties": False,
            },
            handler=_cmd_survey_adherence,
        ),
        CommandSpec(
            id="report.export",
            summary="Genera y exporta un dossier clínico completo (MD, HTML, XLSX, JSON y opcionalmente DOCX/PDF vía wordcraft-cli) dentro de --automation-write-root.",
            input_schema={
                "type": "object",
                "required": ["output_dir"],
                "properties": {
                    "output_dir": {"type": "string"},
                    "prefijo": {"type": "string"},
                    "codigo": {"type": "string", "default": "P001"},
                    "perfil": {"type": "string", "default": "uax_mediterranea"},
                    "sexo": {"type": "string", "enum": ["H", "M"], "default": "M"},
                    "edad": {"type": "integer", "default": 30},
                    "peso": {"type": "number", "default": 70.0},
                    "talla": {"type": "number", "default": 170.0},
                    "actividad": {"type": "number", "default": 1.55},
                    "dias": {"type": "integer", "minimum": 1, "maximum": 7, "default": 3},
                    "semilla": {"type": "integer", "default": 0},
                    "medicamentos": {"type": "array", "items": {"type": "string"}},
                    "formatos": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
            },
            handler=_cmd_report_export,
        ),
    ]
}


def dispatch(command_id: str, args: dict[str, Any], sandbox: PathSandbox) -> dict[str, Any]:
    if command_id not in COMMANDS:
        raise KeyError(f"Comando desconocido: {command_id}")
    return COMMANDS[command_id].handler(args or {}, sandbox)


def parse_cmd_spec(spec: str) -> tuple[str, dict[str, Any]]:
    """Parsea una expresión estilo Craft-Anything `id={json}` o `id`."""
    if "=" in spec:
        cid, raw_json = spec.split("=", 1)
        data = json.loads(raw_json) if raw_json.strip() else {}
        if not isinstance(data, dict):
            raise ValueError(f"Los argumentos de `{cid}` deben ser un objeto JSON.")
        return cid.strip(), data
    return spec.strip(), {}
