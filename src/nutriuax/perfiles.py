"""Perfiles dietéticos como datos (ADR-0004): un TOML por perfil en `config/perfiles/`.

Cada fichero da los campos de `objetivos.Perfil` que cambian respecto a los valores por defecto (o respecto al
perfil del que «parte_de»). Validación estricta: cualquier error dice el fichero y el campo. Los suelos de
seguridad NO viven aquí (`seguridad.py`): un TOML no puede desactivarlos.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

try:  # Python ≥ 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

from .objetivos import COMIDAS, Perfil

DIR_PERFILES = Path(__file__).resolve().parents[2] / "config" / "perfiles"
AMBITOS = {"estudio", "clinico", "hogar"}
RANGOS = {"proteina_gkg", "grasa_pct", "hc_pct", "ajuste_pct", "edad"}
MODOS_ENERGIA = {"mifflin", "eer_iom_2005"}
DICCIONARIOS = {"aa_min_mgkg", "aa_max_mgkg", "semanal_min", "semanal_max"}
CONJUNTOS = {"excluir_etiquetas"}
ESPECIALES = {"parte_de"}
CAMPOS = {f.name for f in dataclasses.fields(Perfil)} - {"clave"}


class PerfilInvalido(ValueError):
    """Error de un fichero de perfil; el mensaje empieza por el nombre del fichero."""


def _leer(dir_: Path) -> dict[str, tuple[Path, dict]]:
    crudos = {}
    for ruta in sorted(Path(dir_).glob("*.toml")):
        try:
            with ruta.open("rb") as fh:
                crudos[ruta.stem] = (ruta, tomllib.load(fh))
        except tomllib.TOMLDecodeError as e:
            raise PerfilInvalido(f"{ruta.name}: TOML mal formado ({e})") from None
    return crudos


def _validar_campos(ruta: Path, d: dict) -> None:
    def err(msg):
        raise PerfilInvalido(f"{ruta.name}: {msg}")

    desconocidos = set(d) - CAMPOS - ESPECIALES
    if desconocidos:
        err(f"campo(s) desconocido(s): {', '.join(sorted(desconocidos))}")
    for k in RANGOS & set(d):
        v = d[k]
        if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)):
            err(f"{k} debe ser [mín, máx]")
        if v[0] > v[1]:
            err(f"{k}: rango invertido {v}")
        if v[0] < 0 and k != "ajuste_pct":
            err(f"{k}: valores negativos {v}")
    for k in DICCIONARIOS & set(d):
        if not isinstance(d[k], dict) or not all(isinstance(x, (int, float)) and x >= 0 for x in d[k].values()):
            err(f"{k} debe ser una tabla de números ≥ 0")
    if "energia_modo" in d and d["energia_modo"] not in MODOS_ENERGIA:
        err(f"energia_modo «{d['energia_modo']}» no es uno de {sorted(MODOS_ENERGIA)}")
    if "ajuste_pct" in d and not (-20 <= d["ajuste_pct"][0] and d["ajuste_pct"][1] <= 20):
        err("ajuste_pct fuera de [-20, 20] (los suelos de seguridad no admiten más)")
    if "ambito" in d and d["ambito"] not in AMBITOS:
        err(f"ambito «{d['ambito']}» no es uno de {sorted(AMBITOS)}")
    if "comidas" in d and (not d["comidas"] or set(d["comidas"]) - set(COMIDAS)):
        err(f"comidas debe ser una lista no vacía de {COMIDAS}")
    if "fuentes" in d and (not isinstance(d["fuentes"], list) or not all(isinstance(x, str) and x.strip()
                                                                         for x in d["fuentes"])):
        err("fuentes debe ser una lista de textos")


def _resolver(clave: str, crudos: dict, pila: tuple[str, ...] = ()) -> dict:
    ruta, d = crudos[clave]
    if clave in pila:
        raise PerfilInvalido(f"{ruta.name}: ciclo en parte_de ({' → '.join(pila + (clave,))})")
    padre = d.get("parte_de")
    base: dict = {}
    if padre is not None:
        if padre not in crudos:
            raise PerfilInvalido(f"{ruta.name}: parte_de «{padre}» no existe")
        base = _resolver(padre, crudos, pila + (clave,))
    out = dict(base)
    for k, v in d.items():
        if k in ESPECIALES:
            continue
        if k in DICCIONARIOS and k in out:
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def _a_perfil(clave: str, ruta: Path, d: dict) -> Perfil:
    if not d.get("fuentes"):
        raise PerfilInvalido(f"{ruta.name}: falta «fuentes» (cada perfil debe citar de dónde salen sus valores)")
    for k in ("nombre", "descripcion", "proteina_gkg"):
        if k not in d:
            raise PerfilInvalido(f"{ruta.name}: falta «{k}»")
    kw = {}
    for k, v in d.items():
        if k in RANGOS:
            kw[k] = (v[0], v[1])
        elif k in CONJUNTOS:
            kw[k] = set(v)
        elif k in DICCIONARIOS:
            kw[k] = dict(v)
        elif k == "fuentes":
            kw[k] = tuple(v)
        else:
            kw[k] = v
    # aa_min_mgkg parte de los mínimos OMS por defecto (como en v0.1) y el perfil los sobrescribe
    if "aa_min_mgkg" in kw:
        kw["aa_min_mgkg"] = {**Perfil(clave, "", "", (0, 0)).aa_min_mgkg, **kw["aa_min_mgkg"]}
    return Perfil(clave=clave, **kw)


def cargar_perfiles(dir_: Path | None = None) -> dict[str, Perfil]:
    """Todos los perfiles del directorio, en orden de nombre de fichero."""
    crudos = _leer(Path(dir_) if dir_ else DIR_PERFILES)
    for ruta, d in crudos.values():
        _validar_campos(ruta, d)
    return {clave: _a_perfil(clave, crudos[clave][0], _resolver(clave, crudos)) for clave in crudos}
