"""T19 · Congela la referencia del estudio UAX (perfiles y menús) para el test de regresión.

Ejecutar SOLO cuando se acepte a propósito un cambio en la referencia clínica:
    PYTHONPATH=src python scripts/congelar_regresion_uax.py
Escribe tests/regresion/perfiles.json y tests/regresion/menu_<caso>.csv.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tests"))
from regresion_uax import CASOS, DIR, generar_caso, perfiles_como_dict  # noqa: E402


def main() -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / "perfiles.json").write_text(json.dumps(perfiles_como_dict(), ensure_ascii=False, indent=1, sort_keys=True)
                                       + "\n", encoding="utf-8")
    for caso in CASOS:
        items = generar_caso(caso)
        items.to_csv(DIR / f"menu_{caso['nombre']}.csv", index=False)
        print(caso["nombre"], len(items), "líneas,", items["gramos"].sum(), "g")


if __name__ == "__main__":
    main()
