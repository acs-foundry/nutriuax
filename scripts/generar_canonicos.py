"""T22 · Genera data/alimentos_canonicos.csv desde scripts/canonicos_fuente.csv.

Las filas con `ndb` lo usan tal cual; las que traen `consulta` (en inglés) toman el primer resultado de la base FDC
completa (sin glosario). El resultado lleva la descripción FDC para revisarlo a mano; `laurel`, `tinta_calamar`
y `nulo` no tienen NDB (sin aporte). Uso: PYTHONPATH=src python scripts/generar_canonicos.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
from nutriuax import base_fdc as b  # noqa: E402


def main() -> None:
    fuente = pd.read_csv(RAIZ / "scripts" / "canonicos_fuente.csv", dtype=str, keep_default_na=False)
    base = b.cargar_completa(RAIZ / "data")
    g = base.set_index("ndb")
    sin_glosario = RAIZ / "__sin_glosario"
    filas = []
    for r in fuente.itertuples():
        ndb = r.ndb.zfill(5) if r.ndb else ""
        if not ndb and r.consulta:
            res = b.buscar(r.consulta, n=1, base=base, data_dir=sin_glosario)
            if res.empty:
                raise SystemExit(f"{r.alimento}: sin resultado para «{r.consulta}»")
            ndb = res["ndb"].iloc[0]
        if ndb and ndb not in g.index:
            raise SystemExit(f"{r.alimento}: NDB {ndb} no existe")
        desc = g.at[ndb, "descripcion"] if ndb else ""
        aa = bool(ndb) and bool(pd.notna(g.at[ndb, "leu"]))
        filas.append(dict(alimento=r.alimento, ndb=ndb, descripcion_fdc=desc, g_por_ud=r.g_por_ud,
                          g_por_ml=r.g_por_ml, alergenos=r.alergenos, tiene_aa=aa, nota=r.nota))
    out = pd.DataFrame(filas)
    out.to_csv(RAIZ / "data" / "alimentos_canonicos.csv", index=False)
    print(f"{len(out)} alimentos canónicos; sin AA en FDC: {int((~out.tiene_aa & (out.ndb != '')).sum())}")


if __name__ == "__main__":
    main()
