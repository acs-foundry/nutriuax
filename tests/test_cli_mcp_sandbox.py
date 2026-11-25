"""Tests de CLI Anything-Craft, servidor MCP STDIO, PathSandbox, lanzador endurecido y Office bridge."""
import io
import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd
import pytest

from nutriuax import cli, composicion, generador, lanzador, mcp, objetivos, office
from nutriuax.sandbox import PathSandbox, SandboxError


def test_cli_anything_craft_verbs(capsys):
    assert cli.main(["version"]) == 0
    assert "nutriuax" in capsys.readouterr().out

    assert cli.main(["doctor", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["ok"] is True and doc["highs_available"] is True and doc["builtin_recipes"] >= 30

    assert cli.main(["commands", "--json"]) == 0
    cmds = json.loads(capsys.readouterr().out)
    assert len(cmds) == 12

    assert cli.main(["describe", "diet.generate", "--json"]) == 0
    desc = json.loads(capsys.readouterr().out)
    assert desc["mcp_tool"] == "nutriuax_diet_generate"

    assert cli.main(["run", "--cmd", 'clinical.anthropometry={"sexo":"H","edad":35,"peso":78,"talla":178}']) == 0
    ant = json.loads(capsys.readouterr().out)
    assert ant["clasificacion_oms"] == "Normopeso"

    assert cli.main(["buscar", "lentejas", "--limit", "5"]) == 0
    bus = json.loads(capsys.readouterr().out)
    assert bus["total"] >= 1


def test_sandbox_rejects_traversal_and_symlinks(tmp_path):
    allowed = tmp_path / "allowed"
    secret = tmp_path / "secret"
    allowed.mkdir()
    secret.mkdir()
    secret_file = secret / "private.txt"
    secret_file.write_text("TOP SECRET", encoding="utf-8")
    link = allowed / "escape_link.txt"
    os.symlink(secret_file, link)

    sb = PathSandbox.from_args(read_roots=[str(allowed)], write_roots=[str(allowed)])
    # Traversal blocked
    with pytest.raises(SandboxError):
        sb.check_read(allowed / ".." / "secret" / "private.txt")
    # Symlink escape blocked
    with pytest.raises(SandboxError):
        sb.check_read(link)
    with pytest.raises(SandboxError):
        sb.check_write(link)
    # Empty sandbox blocks all access
    sb_empty = PathSandbox.from_args()
    with pytest.raises(SandboxError):
        sb_empty.check_read(allowed / "a.txt")
    with pytest.raises(SandboxError):
        sb_empty.check_write(allowed / "a.txt")


def test_mcp_stdio_lifecycle_tools_and_line_cap(tmp_path):
    sb = PathSandbox.from_args(read_roots=[str(tmp_path)], write_roots=[str(tmp_path)])
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nutriuax_doctor", "arguments": {}}},
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "nutriuax_report_export", "arguments": {"output_dir": "/etc/forbidden_dir"}},
        },
    ]
    raw_in = "".join(json.dumps(r) + "\n" for r in requests).encode("utf-8")
    out_buf = io.BytesIO()
    assert mcp.serve_stdio(sb, io.BytesIO(raw_in), out_buf) == 0
    lines = [json.loads(x) for x in out_buf.getvalue().decode("utf-8").splitlines() if x.strip()]
    assert len(lines) == 5  # notification produces no response
    assert lines[0]["result"]["serverInfo"]["name"] == "nutriuax-mcp"
    assert len(lines[2]["result"]["tools"]) == 12
    doc_payload = json.loads(lines[3]["result"]["content"][0]["text"])
    assert doc_payload["ok"] is True
    # Forbidden write path rejected cleanly by PathSandbox
    assert lines[4]["result"]["isError"] is True
    assert "outside allowed roots" in lines[4]["result"]["content"][0]["text"]

    # Oversized line cap (> MAX_MCP_LINE_BYTES) handled without OOM
    huge = b'{"jsonrpc":"2.0","id":9,"method":"ping","pad":"' + (b"A" * (mcp.MAX_MCP_LINE_BYTES + 100)) + b'"}\n'
    out_huge = io.BytesIO()
    assert mcp.serve_stdio(sb, io.BytesIO(huge), out_huge) == 0
    err_resp = json.loads(out_huge.getvalue().decode("utf-8").strip())
    assert err_resp["error"]["code"] == -32600


def test_office_dossier_xss_safe_and_excel_8_sheets(tmp_path):
    comp = composicion.cargar()
    p = objetivos.Persona(codigo='<script>alert("xss")</script>', kcal_manual=2000)
    obj = objetivos.calcular_objetivos(p, objetivos.PERFILES["uax_mediterranea"])
    menu = generador.generar(comp, obj, dias=1, semilla=0, tiempo_max=15)

    html_doc = office.generar_informe_html(menu, p, comp, medicamentos=["ieca_ara2"])
    assert "<script>" not in html_doc
    assert "&lt;script&gt;" in html_doc

    xls_bytes = office.exportar_excel_clinico(menu, p, comp, medicamentos=["ieca_ara2"])
    xls = pd.ExcelFile(io.BytesIO(xls_bytes))
    assert len(xls.sheet_names) == 8

    res = office.exportar_dossier_completo(
        menu, p, comp, tmp_path / "dossier", medicamentos=["ieca_ara2"], formatos=("md", "html", "xlsx", "json", "docx")
    )
    assert Path(res["archivos"]["md"]).exists()
    assert Path(res["archivos"]["html"]).exists()
    assert Path(res["archivos"]["xlsx"]).exists()
    assert Path(res["archivos"]["json"]).exists()


def test_lanzador_rejects_oversized_post_and_sets_security_headers():
    class Dummy:
        def estado(self):
            return {"activo": False, "modo": None}

        def arrancar(self, m):
            pass

        def parar(self):
            pass

    srv = lanzador.crear_servidor(0, Dummy(), lista=lambda: False)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        with urllib.request.urlopen(base + "/", timeout=5) as r:
            assert r.headers.get("X-Content-Type-Options") == "nosniff"
            assert r.headers.get("X-Frame-Options") == "DENY"
        req = urllib.request.Request(base + "/arrancar", data=b"x" * (lanzador.MAX_POST_BYTES + 10), method="POST")
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=5)
        assert exc.value.code == 413
    finally:
        srv.shutdown()
