"""Anything-Craft standard CLI for NutriUAX (`nutriuax-cli` and `python -m nutriuax`).

Supports:
- Craft-Anything standard verbs: `version`, `doctor`, `commands`, `describe`, `run`, `mcp`
  (with `--automation-read-root` & `--automation-write-root` sandbox confinement for `craft_box.py`).
- Direct clinical/dietetics subcommands: `menu` (JSON v1 backward compatible), `dieta`, `buscar`,
  `antropometria`, `intercambios`, `farmacos`, `encuesta`, `adherencia`, `exportar`, `gui`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import __version__
from .commands import COMMANDS, dispatch, parse_cmd_spec
from .mcp import serve_stdio
from .sandbox import PathSandbox, SandboxError

RAIZ = Path(__file__).resolve().parents[2]


def _emit(data: object, as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(data)


def launch_gui(argv: list[str] | None = None) -> int:
    """Launches the local Streamlit Studio GUI (`nutriuax` binary)."""
    ap = argparse.ArgumentParser(prog="nutriuax", description="NutriUAX Studio (GUI local)")
    ap.add_argument("--modo", choices=("estudio", "consulta", "hogar"), default=os.environ.get("NUTRIUAX_MODO", "consulta"))
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--headless", action="store_true")
    a = ap.parse_args(argv)
    env = os.environ.copy()
    env["NUTRIUAX_MODO"] = a.modo
    env["PYTHONPATH"] = str(RAIZ / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(RAIZ / "app.py"),
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(a.port),
    ]
    if a.headless:
        cmd += ["--server.headless", "true"]
    return subprocess.call(cmd, env=env)


def _add_sandbox_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--automation-read-root", action="append", default=[], dest="read_roots",
                   help="Directorio raíz permitido para lectura (repetible)")
    p.add_argument("--automation-write-root", action="append", default=[], dest="write_roots",
                   help="Directorio raíz permitido para escritura (repetible)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="nutriuax-cli",
        description="NutriUAX · Nutrición clínica, optimización de BCAA, encuestas y CLI/MCP compatible con Anything-Craft",
    )
    ap.add_argument("--version", action="version", version=f"nutriuax {__version__}")
    sub = ap.add_subparsers(dest="orden", required=True)

    # --- Craft-Anything standard commands ---
    sub.add_parser("version", help="Imprime la versión de NutriUAX")

    p_doc = sub.add_parser("doctor", help="Comprueba solver HiGHS, base FDC, recetas MIT y puente ArtCraft")
    p_doc.add_argument("--json", action="store_true", dest="as_json")

    p_cmds = sub.add_parser("commands", help="Lista todos los comandos simétricos CLI/MCP")
    p_cmds.add_argument("--json", action="store_true", dest="as_json")
    p_cmds.add_argument("--search", default="", help="Filtrar por subcadena")

    p_desc = sub.add_parser("describe", help="Muestra el esquema JSON y ayuda de un comando")
    p_desc.add_argument("command_id", help="Identificador del comando (p. ej. diet.generate)")
    p_desc.add_argument("--json", action="store_true", dest="as_json")

    p_run = sub.add_parser("run", help="Ejecuta uno o más comandos headless estilo Craft-Anything (--cmd 'id={json}')")
    p_run.add_argument("--cmd", action="append", default=[], help="Comando en formato 'id={json}' (repetible)")
    p_run.add_argument("--script", type=Path, help="Fichero con un comando 'id={json}' por línea")
    _add_sandbox_args(p_run)

    p_mcp = sub.add_parser("mcp", help="Inicia el servidor MCP JSON-RPC 2.0 por STDIO (compatible con craft_box.py)")
    _add_sandbox_args(p_mcp)

    # --- Backward-compatible household JSON v1 command (T27 / T29) ---
    p_menu = sub.add_parser("menu", help="Genera un menú de hogar/consulta desde un JSON de entrada v1")
    p_menu.add_argument("--entrada", type=Path, required=True, help="JSON de entrada (schema/entrada_v1.json)")
    p_menu.add_argument("--salida", type=Path, help="JSON de salida (por defecto, a stdout)")
    p_menu.add_argument("--recetas", type=Path, help="Biblioteca de recetas (por defecto, config/fuentes.toml)")

    # --- Direct clinical ergonomic subcommands ---
    p_dieta = sub.add_parser("dieta", help="Genera una dieta clínica individual (MILP) en JSON")
    p_dieta.add_argument("--perfil", default="uax_mediterranea")
    p_dieta.add_argument("--sexo", choices=("H", "M"), default="M")
    p_dieta.add_argument("--edad", type=int, default=30)
    p_dieta.add_argument("--peso", type=float, default=70.0)
    p_dieta.add_argument("--talla", type=float, default=170.0)
    p_dieta.add_argument("--actividad", type=float, default=1.55)
    p_dieta.add_argument("--masa-magra", type=float, default=None)
    p_dieta.add_argument("--kcal-manual", type=float, default=None)
    p_dieta.add_argument("--dias", type=int, default=3)
    p_dieta.add_argument("--semilla", type=int, default=0)
    p_dieta.add_argument("--vetar", action="append", default=[], help="ID de alimento a excluir (repetible)")
    p_dieta.add_argument("--farmaco", action="append", default=[], help="Clave de fármaco del vademécum (repetible)")
    p_dieta.add_argument("--salida", type=Path)

    p_bus = sub.add_parser("buscar", help="Busca alimentos en el catálogo y en USDA FDC (~7.800 alimentos)")
    p_bus.add_argument("query", help="Texto de búsqueda en español o inglés")
    p_bus.add_argument("--limit", type=int, default=15)
    p_bus.add_argument("--source", choices=("catalog", "fdc", "both"), default="both")

    p_ant = sub.add_parser("antropometria", help="Evalúa IMC, 5 ecuaciones TMB/EER, peso ideal y cribado MUST")
    p_ant.add_argument("--sexo", choices=("H", "M"), required=True)
    p_ant.add_argument("--edad", type=int, required=True)
    p_ant.add_argument("--peso", type=float, required=True)
    p_ant.add_argument("--talla", type=float, required=True)
    p_ant.add_argument("--actividad", type=float, default=1.55)
    p_ant.add_argument("--cintura", type=float, default=None)
    p_ant.add_argument("--cadera", type=float, default=None)
    p_ant.add_argument("--perdida-peso-pct", type=float, default=None)
    p_ant.add_argument("--enfermedad-aguda", action="store_true")

    p_int = sub.add_parser("intercambios", help="Muestra la guía española de intercambios (1 intercambio = X g)")
    p_int.add_argument("--grupo", default=None)

    p_far = sub.add_parser("farmacos", help="Lista o evalúa interacciones fármaco-nutriente (24 fármacos/clases)")
    p_far.add_argument("--listar", action="store_true")
    p_far.add_argument("--med", action="append", default=[], help="Clave de fármaco (repetible)")

    p_enc = sub.add_parser("encuesta", help="Calcula un registro de N días o FFQ PREDIMED-Plus desde un JSON")
    p_enc.add_argument("--tipo", choices=("diario", "ffq"), default="diario")
    p_enc.add_argument("--entrada", type=Path, required=True)
    p_enc.add_argument("--peso", type=float, default=70.0)
    p_enc.add_argument("--ventana", choices=("1_ano", "8_semanas"), default="1_ano")

    p_adh = sub.add_parser("adherencia", help="Evalúa MEDAS-14, Maroni 24h y adherencia combinada desde un JSON")
    p_adh.add_argument("--entrada", type=Path, required=True)

    p_exp = sub.add_parser("exportar", help="Exporta dossier clínico completo (MD, HTML, XLSX, JSON y DOCX/PDF vía WordCraft)")
    p_exp.add_argument("--perfil", default="uax_mediterranea")
    p_exp.add_argument("--codigo", default="P001")
    p_exp.add_argument("--sexo", choices=("H", "M"), default="M")
    p_exp.add_argument("--edad", type=int, default=30)
    p_exp.add_argument("--peso", type=float, default=70.0)
    p_exp.add_argument("--talla", type=float, default=170.0)
    p_exp.add_argument("--dias", type=int, default=3)
    p_exp.add_argument("--farmaco", action="append", default=[])
    p_exp.add_argument("--salida-dir", type=Path, required=True)

    p_gui = sub.add_parser("gui", help="Abre la interfaz gráfica local de NutriUAX Studio")
    p_gui.add_argument("--modo", choices=("estudio", "consulta", "hogar"), default="consulta")
    p_gui.add_argument("--port", type=int, default=8501)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)

    if a.orden == "version":
        print(f"nutriuax {__version__}")
        return 0

    if a.orden == "gui":
        return launch_gui(["--modo", a.modo, "--port", str(a.port)])

    if a.orden == "doctor":
        sb = PathSandbox.from_args(default_cwd_if_empty=True)
        info = dispatch("doctor", {}, sb)
        if a.as_json:
            _emit(info, True)
        else:
            status = "OK" if info["ok"] else "WARN"
            print(
                f"NutriUAX {info['version']} [{status}] · Python {info['python']} · HiGHS={info['highs_available']} · "
                f"Catálogo={info['catalog_foods']} ({info['catalog_source']}) · FDC={info['fdc_full_foods']} · "
                f"Recetas MIT={info['builtin_recipes']} · Perfiles={info['profiles_count']} · Fármacos={info['drug_rules_count']}"
            )
            ac = info["artcraft_office"]
            print("ArtCraft Office:", ", ".join(f"{k}={'sí' if v else 'no'}" for k, v in ac.items()))
        return 0 if info["ok"] else 1

    if a.orden == "commands":
        q = a.search.lower().strip()
        items = [
            {"id": c.id, "mcp_tool": "nutriuax_" + c.id.replace(".", "_"), "summary": c.summary}
            for c in COMMANDS.values()
            if not q or q in c.id.lower() or q in c.summary.lower()
        ]
        if a.as_json:
            _emit(items, True)
        else:
            for it in items:
                print(f"{it['id']:26s}  {it['summary']}")
        return 0

    if a.orden == "describe":
        if a.command_id not in COMMANDS:
            print(f"Error: comando desconocido «{a.command_id}»", file=sys.stderr)
            return 2
        spec = COMMANDS[a.command_id]
        doc = {
            "id": spec.id,
            "mcp_tool": "nutriuax_" + spec.id.replace(".", "_"),
            "summary": spec.summary,
            "inputSchema": spec.input_schema,
        }
        _emit(doc, True)
        return 0

    if a.orden == "mcp":
        sb = PathSandbox.from_args(a.read_roots, a.write_roots, default_cwd_if_empty=False)
        return serve_stdio(sb)

    if a.orden == "run":
        sb = PathSandbox.from_args(a.read_roots, a.write_roots, default_cwd_if_empty=not (a.read_roots or a.write_roots))
        specs: list[str] = list(a.cmd)
        if a.script:
            for line in sb.read_text_bounded(a.script).splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    specs.append(line)
        if not specs:
            print("Error: proporciona al menos un --cmd o --script.", file=sys.stderr)
            return 2
        results = []
        try:
            for sp in specs:
                cid, params = parse_cmd_spec(sp)
                results.append({"command": cid, "result": dispatch(cid, params, sb)})
        except (KeyError, ValueError, SandboxError, FileNotFoundError, json.JSONDecodeError, RuntimeError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        _emit(results[0]["result"] if len(results) == 1 else results, True)
        return 0

    # --- Backward compatible `menu` command (exact contract verified by tests/test_api.py & test_criterio_final.py) ---
    if a.orden == "menu":
        from .api import EntradaInvalida, generar_menu

        try:
            entrada = json.loads(a.entrada.read_text(encoding="utf-8"))
            salida = generar_menu(entrada, a.recetas)
        except (EntradaInvalida, FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        texto = json.dumps(salida, ensure_ascii=False, indent=1)
        if a.salida:
            a.salida.write_text(texto + "\n", encoding="utf-8")
            n_av = len(salida["avisos"])
            print(f"Menú de {salida['semana']['dias']} días escrito en {a.salida} ({n_av} aviso(s)).")
        else:
            print(texto)
        return 0

    # --- Ergonomic subcommands backed by symmetrical command registry ---
    sb_local = PathSandbox.from_args(default_cwd_if_empty=True)
    try:
        if a.orden == "dieta":
            res = dispatch(
                "diet.generate",
                {
                    "perfil": a.perfil,
                    "sexo": a.sexo,
                    "edad": a.edad,
                    "peso": a.peso,
                    "talla": a.talla,
                    "actividad": a.actividad,
                    "masa_magra": a.masa_magra,
                    "kcal_manual": a.kcal_manual,
                    "dias": a.dias,
                    "semilla": a.semilla,
                    "vetados": a.vetar,
                    "medicamentos": a.farmaco,
                },
                sb_local,
            )
            if a.salida:
                a.salida.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"Dieta escrita en {a.salida} ({res['criterios_en_rango']} criterios en rango).")
            else:
                _emit(res, True)
            return 0

        if a.orden == "buscar":
            _emit(dispatch("foods.search", {"query": a.query, "limit": a.limit, "source": a.source}, sb_local), True)
            return 0

        if a.orden == "antropometria":
            payload = {
                "sexo": a.sexo,
                "edad": a.edad,
                "peso": a.peso,
                "talla": a.talla,
                "actividad": a.actividad,
                "cintura_cm": a.cintura,
                "cadera_cm": a.cadera,
                "perdida_peso_pct_3_6m": a.perdida_peso_pct,
                "efecto_enfermedad_aguda": a.enfermedad_aguda,
            }
            _emit(dispatch("clinical.anthropometry", payload, sb_local), True)
            return 0

        if a.orden == "intercambios":
            _emit(dispatch("exchanges.guide", {"grupo": a.grupo}, sb_local), True)
            return 0

        if a.orden == "farmacos":
            _emit(dispatch("drugs.check", {"listar": a.listar or not a.med, "medicamentos": a.med}, sb_local), True)
            return 0

        if a.orden == "encuesta":
            datos = json.loads(a.entrada.read_text(encoding="utf-8"))
            if a.tipo == "diario":
                regs = datos if isinstance(datos, list) else datos.get("registros", [])
                res = dispatch("survey.diary", {"registros": regs, "peso_kg": a.peso}, sb_local)
            else:
                resps = datos if isinstance(datos, list) else datos.get("respuestas", [])
                res = dispatch("survey.ffq", {"respuestas": resps, "peso_kg": a.peso, "ventana": a.ventana}, sb_local)
            _emit(res, True)
            return 0

        if a.orden == "adherencia":
            datos = json.loads(a.entrada.read_text(encoding="utf-8"))
            _emit(dispatch("survey.adherence", datos, sb_local), True)
            return 0

        if a.orden == "exportar":
            sb_out = PathSandbox.from_args(write_roots=[str(a.salida_dir.resolve())])
            res = dispatch(
                "report.export",
                {
                    "output_dir": str(a.salida_dir.resolve()),
                    "perfil": a.perfil,
                    "codigo": a.codigo,
                    "sexo": a.sexo,
                    "edad": a.edad,
                    "peso": a.peso,
                    "talla": a.talla,
                    "dias": a.dias,
                    "medicamentos": a.farmaco,
                },
                sb_out,
            )
            _emit(res, True)
            return 0
    except (KeyError, ValueError, FileNotFoundError, json.JSONDecodeError, SandboxError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
