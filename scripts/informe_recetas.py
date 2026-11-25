"""T23 · Informe de recetas calculables de la biblioteca externa (cifras agregadas; no copia recetas).

Uso: PYTHONPATH=src python scripts/informe_recetas.py [RUTA_BIBLIOTECA] → data/informe_recetas.md
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
from nutriuax import recetas as rc  # noqa: E402


def main() -> None:
    ruta = sys.argv[1] if len(sys.argv) > 1 else None
    rs = rc.cargar_recetas(ruta)
    t = rc.como_tabla(rs)
    minimo = rc.cobertura_minima()
    t["calculable"] = t["cobertura"] >= minimo
    plato = t["rol"].isin(["principal", "primero", "guarnicion"])
    lin = [f"# Recetas calculables · {len(t)} recetas de `{rc.ruta_biblioteca(ruta).name}`", "",
           f"- Cobertura mínima para ofrecer una receta al generador: {minimo:.0%} de sus gramos",
           f"- Calculables: **{int(t.calculable.sum())}** ({t.calculable.mean():.1%}); "
           f"platos (principal/primero/guarnición) calculables: {int((t.calculable & plato).sum())}",
           f"- Cobertura media por receta: {t.cobertura.mean():.1%}; mediana {t.cobertura.median():.1%}", "",
           "| rol | recetas | calculables | kcal/ración (mediana) | proteína g/ración (mediana) | Leu mg/ración (mediana) |",
           "|---|---:|---:|---:|---:|---:|"]
    for rol, g in t.groupby("rol"):
        ok = g[g.calculable]
        lin.append(f"| {rol} | {len(g)} | {len(ok)} | {ok.kcal.median():.0f} | {ok.proteina.median():.1f} | "
                   f"{ok.leu.median():.0f} |")
    lin += ["", "## Recetas no calculables con más peso sin mapear (id · cobertura)", ""]
    lin += [f"- {r.id} · {r.cobertura:.0%}" for r in t[~t.calculable].sort_values("cobertura").head(30).itertuples()]
    (RAIZ / "data" / "informe_recetas.md").write_text("\n".join(lin) + "\n", encoding="utf-8")
    print("\n".join(lin[:6]))


if __name__ == "__main__":
    main()
