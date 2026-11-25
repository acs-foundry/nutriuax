"""T26 · Rendimiento del modo hogar: hogar sintético de 5 × 7 días × 4 comidas con la biblioteca real.

Uso: PYTHONPATH=src python scripts/benchmark_hogar.py [--recetas RUTA] [--repeticiones 3]
Criterio (ADR-0005): < 60 s en omarchy. Imprime tiempos por etapa y el peor desvío de energía.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
from nutriuax import api, hogar  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recetas", type=Path)
    ap.add_argument("--repeticiones", type=int, default=1)
    a = ap.parse_args()
    entrada = json.loads((RAIZ / "docs" / "ejemplos" / "entrada_hogar_sintetico.json").read_text(encoding="utf-8"))
    tiempos = []
    for i in range(a.repeticiones):
        t0 = time.perf_counter()
        sal = api.generar_menu(entrada, a.recetas)
        tiempos.append(time.perf_counter() - t0)
        peor = max(abs(n["desviacion_kcal"]) for n in sal["nutrientes"])
        print(f"repetición {i + 1}: {tiempos[-1]:.1f} s · peor desvío de energía {peor:.1%} · "
              f"{len(sal['avisos'])} aviso(s)")
    med = statistics.median(tiempos)
    print(f"Mediana {med:.1f} s (K = {hogar.K_PRESELECCION}, {len(entrada['hogar']['miembros'])} miembros, "
          f"{entrada['semana']['dias']} días) → {'CUMPLE' if med < 60 else 'NO CUMPLE'} < 60 s")


if __name__ == "__main__":
    main()
