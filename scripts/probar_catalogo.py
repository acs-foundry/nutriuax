"""Comprueba que el catálogo propuesto carga, se importa de FDC y el generador resuelve con él."""
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(sys.argv[1])
sys.path.insert(0, str(REPO / "src"))
from nutriuax import composicion as c, generador as g, importar_fdc, objetivos as o  # noqa: E402

tmp = Path(tempfile.mkdtemp(dir=Path(sys.argv[2])))
shutil.copy(REPO / "data" / "catalogo_propuesto.csv", tmp / "alimentos.csv")
rev = importar_fdc.importar(REPO / "fdc_sr_legacy.zip", tmp)
print("emparejados por búsqueda:", int((rev["modo"] != "ndb").sum()), "· sin AA:", int(rev["sin_aminoacidos_fdc"].sum()))
comp = c.cargar(tmp)
t = comp.tabla
print("fuente:", comp.fuente, "· alimentos:", len(t), "· por rol:", t["rol"].value_counts().to_dict())
assert (t["min_g"] <= t["porcion_g"]).all() and (t["porcion_g"] <= t["max_g"]).all(), \
    t.index[(t["min_g"] > t["porcion_g"]) | (t["porcion_g"] > t["max_g"])].tolist()
atw = 4 * t["proteina"] + 9 * t["grasa"] + 4 * t["hc"]
rel = (t["kcal"] - atw).abs() / t["kcal"]
mal = t.index[(t["kcal"] >= 30) & (rel >= 0.25)].tolist()
print("Atwater fuera de ±25 %:", mal)
for clave in o.PERFILES:
    obj = o.calcular_objetivos(o.Persona(sexo="H", edad=25, peso=75, talla=178), o.PERFILES[clave])
    t0 = time.time()
    m = g.generar(comp, obj, dias=7, tiempo_max=25)
    ch = g.comprobar(m)
    print(f"{clave:20s} {time.time()-t0:5.1f} s · {m.estado} · fuera de rango {int((~ch.ok).sum())}/{len(ch)} · "
          f"alimentos distintos {m.items['id'].nunique()}")
