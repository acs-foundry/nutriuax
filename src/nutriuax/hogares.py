"""Hogares guardados en local (T31): p. ej. «Familia Ejemplo», para cargarlo por defecto en el modo Menú familiar.

Edad, peso y talla son datos de salud: se guardan SOLO en este equipo, fuera del repo y de la sincronización, en
`~/.config/nutriuax/hogares/<nombre>.json` (o en `$NUTRIUAX_HOGARES`), con permisos 0600. Nunca se suben a GitHub.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

import pandas as pd

COLUMNAS = ["id", "nombre", "sexo", "edad", "peso", "talla", "actividad", "perfil", "alergias"]
POR_DEFECTO = "_por_defecto.txt"
MAX_HOGAR_BYTES = 1 * 1024 * 1024  # 1 MiB


def directorio() -> Path:
    d = Path(os.environ.get("NUTRIUAX_HOGARES") or Path.home() / ".config" / "nutriuax" / "hogares")
    d.mkdir(parents=True, exist_ok=True)
    try:
        d.chmod(0o700)
    except OSError:
        pass
    return d


def _archivo(nombre: str) -> Path:
    s = unicodedata.normalize("NFKD", nombre.lower())
    s = re.sub(r"[^a-z0-9]+", "-", "".join(c for c in s if not unicodedata.combining(c))).strip("-")
    if not s:
        raise ValueError("Pon un nombre al hogar")
    return directorio() / f"{s}.json"


def _leer_json_acotado(p: Path) -> dict:
    if p.stat().st_size > MAX_HOGAR_BYTES:
        raise ValueError(f"El fichero de hogar supera {MAX_HOGAR_BYTES} bytes")
    return json.loads(p.read_text(encoding="utf-8"))


def listar() -> list[str]:
    """Nombres de los hogares guardados (tal como se escribieron)."""
    out = []
    for p in sorted(directorio().glob("*.json")):
        try:
            out.append(_leer_json_acotado(p).get("nombre", p.stem))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return out


def guardar(nombre: str, miembros: pd.DataFrame, por_defecto: bool = True) -> Path:
    df = miembros.copy()
    for c in COLUMNAS:
        if c not in df.columns:
            df[c] = ""
    df = df[COLUMNAS].dropna(subset=["id"])
    doc = {"nombre": nombre, "version": 1, "miembros": json.loads(df.to_json(orient="records", force_ascii=False))}
    ruta = _archivo(nombre)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(ruta)
    if por_defecto:
        def_path = directorio() / POR_DEFECTO
        tmp_def = def_path.with_suffix(".tmp")
        tmp_def.write_text(nombre, encoding="utf-8")
        tmp_def.chmod(0o600)
        tmp_def.replace(def_path)
    return ruta


def cargar(nombre: str) -> pd.DataFrame:
    doc = _leer_json_acotado(_archivo(nombre))
    df = pd.DataFrame(doc.get("miembros", []))
    for c in COLUMNAS:
        if c not in df.columns:
            df[c] = ""
    return df[COLUMNAS]


def por_defecto() -> str | None:
    p = directorio() / POR_DEFECTO
    if p.exists():
        nombre = p.read_text(encoding="utf-8").strip()
        if nombre in listar():
            return nombre
    return None
