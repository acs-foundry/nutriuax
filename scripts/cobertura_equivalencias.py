"""T22 · Informe de cobertura de la tabla de equivalencias sobre una biblioteca de recetas (formato Menú Familiar).

Uso: PYTHONPATH=src python scripts/cobertura_equivalencias.py RUTA/biblioteca.json [--salida DIR]
Mide el % de GRAMOS mapeados (ud sin gramos por unidad y ml sin densidad cuentan como no convertibles; para
ponderarlos se usa 50 g/ud). Escribe en DIR (por defecto data/): cobertura_equivalencias.md (resumen, top sin
mapear) y equivalencias_revisar.csv (nombres mapeados con confianza media/baja o marcados «revisar», para la
dietista). No copia la biblioteca: solo nombres de ingredientes y cifras agregadas.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
from nutriuax import equivalencias as eq  # noqa: E402

G_UD_DESCONOCIDO = 50.0


def analizar(recetas: list[dict]) -> pd.DataFrame:
    tablas = eq.cargar()
    filas = []
    for r in recetas:
        for i in r.get("ingredientes", []):
            e = eq.resolver(i["n"], float(i["q"]), i["u"], tablas)
            peso = e.gramos if e.gramos is not None else (float(i["q"]) * (G_UD_DESCONOCIDO if i["u"] == "ud" else 1))
            filas.append(dict(receta=r["id"], nombre=i["n"], normalizado=eq.normalizar(i["n"]), u=i["u"],
                              alimento=e.alimento, convertido=e.gramos is not None, gramos=peso,
                              confianza=e.confianza, revisar=e.revisar))
    return pd.DataFrame(filas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("biblioteca", type=Path)
    ap.add_argument("--salida", type=Path, default=RAIZ / "data")
    a = ap.parse_args()
    recetas = json.loads(a.biblioteca.read_text(encoding="utf-8"))
    df = analizar(recetas)
    tot = df["gramos"].sum()
    ok = df.loc[df["alimento"].notna() & df["convertido"], "gramos"].sum()
    sin = df[df["alimento"].isna()]
    noconv = df[df["alimento"].notna() & ~df["convertido"]]
    top = sin.groupby("normalizado").agg(gramos=("gramos", "sum"), veces=("nombre", "size"),
                                         ejemplo=("nombre", "first")).sort_values("gramos", ascending=False)
    # cobertura por receta
    por_receta = df.assign(m=df["alimento"].notna() & df["convertido"]).groupby("receta").apply(
        lambda g: g.loc[g["m"], "gramos"].sum() / g["gramos"].sum() if g["gramos"].sum() else 1.0)
    lineas = [
        f"# Cobertura de equivalencias · {len(recetas)} recetas, {len(df)} ingredientes, "
        f"{df['normalizado'].nunique()} nombres normalizados",
        "",
        f"- **Gramos mapeados y convertibles: {ok / tot:.1%}** (objetivo ≥ 95 %)",
        f"- Sin regla: {sin['gramos'].sum() / tot:.1%} de los gramos ({sin['normalizado'].nunique()} nombres)",
        f"- Con regla pero sin gramos por unidad/densidad: {noconv['gramos'].sum() / tot:.1%} "
        f"({', '.join(sorted(noconv['alimento'].unique())[:20])})",
        f"- Recetas con ≥ 95 % de sus gramos mapeados: {(por_receta >= 0.95).mean():.1%}; "
        f"≥ 90 %: {(por_receta >= 0.90).mean():.1%}",
        "",
        "## Top 50 sin mapear (por gramos)",
        "",
        "| nombre normalizado | gramos | veces | ejemplo |",
        "|---|---:|---:|---|",
        *[f"| {n} | {r.gramos:.0f} | {r.veces} | {r.ejemplo} |" for n, r in top.head(50).iterrows()],
    ]
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "cobertura_equivalencias.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    rev = df[df["alimento"].notna() & (df["revisar"] | df["confianza"].isin(["media", "baja"]))]
    (rev.groupby(["normalizado", "alimento", "confianza"]).agg(gramos=("gramos", "sum"), veces=("nombre", "size"),
                                                              ejemplo=("nombre", "first"))
        .sort_values("gramos", ascending=False).reset_index()
        .to_csv(a.salida / "equivalencias_revisar.csv", index=False))
    print("\n".join(lineas[:8]))


if __name__ == "__main__":
    main()
