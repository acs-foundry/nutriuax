"""Importa composición (macros, minerales y aminoácidos) desde USDA FoodData Central SR Legacy.

Uso (en el portátil, con conexión):
    1. Descarga el CSV de SR Legacy (CC0):
       https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip
    2. python -m nutriuax.importar_fdc RUTA/AL/zip
Escribe data/composicion_fdc.csv (por 100 g) y data/revision_fdc.csv, que lista para cada
alimento la descripción FDC elegida y si se emparejó por NDB o por búsqueda (→ revisar con dietista).
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

from .composicion import DATA_DIR

# número de nutriente FDC (SR) → nombre interno; minerales y AA se pasan a mg
NUM = {
    "208": ("kcal", 1), "203": ("proteina", 1), "204": ("grasa", 1), "606": ("agsat", 1),
    "205": ("hc", 1), "291": ("fibra", 1), "307": ("sodio", 1), "306": ("potasio", 1),
    "305": ("fosforo", 1), "301": ("calcio", 1),
    "504": ("leu", 1000), "503": ("ile", 1000), "510": ("val", 1000), "505": ("lys", 1000),
    "506": ("met", 1000), "508": ("phe", 1000), "502": ("thr", 1000), "501": ("trp", 1000),
    "512": ("his", 1000),
}


def _leer(z: zipfile.ZipFile, nombre: str) -> pd.DataFrame:
    cand = [n for n in z.namelist() if n.endswith("/" + nombre) or n == nombre]
    if not cand:
        raise FileNotFoundError(f"{nombre} no está en el zip")
    with z.open(cand[0]) as fh:
        return pd.read_csv(io.TextIOWrapper(fh, encoding="utf-8"), dtype=str)


def _puntuar(desc: str, consulta: str) -> float:
    t = set(re.findall(r"[a-z0-9]+", consulta.lower()))
    d = set(re.findall(r"[a-z0-9]+", desc.lower()))
    return len(t & d) / max(len(t), 1) - 0.002 * len(d)


def importar(zip_path: Path, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    z = zipfile.ZipFile(zip_path)
    food = _leer(z, "food.csv")[["fdc_id", "description"]]
    sr = _leer(z, "sr_legacy_food.csv")[["fdc_id", "NDB_number"]]
    nutrient = _leer(z, "nutrient.csv")[["id", "nutrient_nbr"]]
    fn = _leer(z, "food_nutrient.csv")[["fdc_id", "nutrient_id", "amount"]]
    food = food.merge(sr, on="fdc_id")
    food["NDB_number"] = food["NDB_number"].str.zfill(5)

    alim = pd.read_csv(data_dir / "alimentos.csv", dtype={"ndb": str})
    elegidos, revision = [], []
    for r in alim.itertuples():
        ndb = (r.ndb or "").strip().zfill(5) if isinstance(r.ndb, str) and r.ndb.strip() else ""
        hit = food[food["NDB_number"] == ndb] if ndb else food.iloc[0:0]
        modo = "ndb"
        if hit.empty:
            sc = food["description"].map(lambda d: _puntuar(d, r.busqueda_fdc))
            hit = food.loc[[sc.idxmax()]]
            modo = "busqueda (REVISAR)"
        h = hit.iloc[0]
        elegidos.append((r.id, h["fdc_id"]))
        revision.append(dict(id=r.id, nombre=r.nombre, modo=modo, fdc_id=h["fdc_id"],
                             ndb=h["NDB_number"], descripcion_fdc=h["description"]))

    sel = pd.DataFrame(elegidos, columns=["id", "fdc_id"])
    nmap = nutrient.assign(nbr=nutrient["nutrient_nbr"].str.replace(r"\.0$", "", regex=True))
    nmap = nmap[nmap["nbr"].isin(NUM)]
    fn = fn[fn["fdc_id"].isin(sel["fdc_id"])].merge(nmap, left_on="nutrient_id", right_on="id")
    fn["col"] = fn["nbr"].map(lambda k: NUM[k][0])
    fn["valor"] = fn["amount"].astype(float) * fn["nbr"].map(lambda k: NUM[k][1])
    ancho = fn.pivot_table(index="fdc_id", columns="col", values="valor", aggfunc="first").reset_index()
    out = sel.merge(ancho, on="fdc_id", how="left").drop(columns="fdc_id")
    for col, _ in NUM.values():
        if col not in out.columns:
            out[col] = float("nan")
    out.to_csv(data_dir / "composicion_fdc.csv", index=False)
    rev = pd.DataFrame(revision)
    faltan = out.set_index("id")[["leu", "ile", "val"]].isna().any(axis=1)
    rev["sin_aminoacidos_fdc"] = rev["id"].map(faltan).fillna(True)
    rev.to_csv(data_dir / "revision_fdc.csv", index=False)
    return rev


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zip", type=Path)
    a = ap.parse_args(argv)
    rev = importar(a.zip)
    n_rev = (rev["modo"] != "ndb").sum()
    print(f"composicion_fdc.csv escrito ({len(rev)} alimentos). Revisar emparejamiento: {n_rev}. "
          f"Ver data/revision_fdc.csv")
    from . import base_fdc
    ruta = base_fdc.generar_completa(a.zip)
    print(f"{ruta.name} escrito ({len(base_fdc.cargar_completa())} alimentos de la base completa FDC).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
