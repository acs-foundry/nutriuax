"""T19 · Regresión del estudio UAX: los 5 perfiles clínicos y los menús de referencia no pueden cambiar.

Si este test falla, NO regeneres la referencia para que pase: averigua qué cambió. Solo se regenera con
`scripts/congelar_regresion_uax.py` tras aprobar explícitamente el cambio clínico."""
import json

import pandas as pd
import pytest

from regresion_uax import CASOS, DIR, generar_caso, perfiles_como_dict


def test_perfiles_clinicos_identicos():
    ref = json.loads((DIR / "perfiles.json").read_text(encoding="utf-8"))
    actual = json.loads(json.dumps(perfiles_como_dict(), sort_keys=True))
    for clave in ref:
        # se comparan todos los campos de la referencia; los campos nuevos de metadatos (fuentes, ambito, orden…)
        # son aditivos y no intervienen en el cálculo
        faltan = set(ref[clave]) - set(actual[clave])
        assert not faltan, f"perfil {clave}: faltan campos {faltan}"
        assert {k: actual[clave][k] for k in ref[clave]} == ref[clave], f"perfil {clave} cambió"


@pytest.mark.parametrize("caso", CASOS, ids=[c["nombre"] for c in CASOS])
def test_menu_uax_identico(caso):
    ref = pd.read_csv(DIR / f"menu_{caso['nombre']}.csv")
    actual = generar_caso(caso)
    pd.testing.assert_frame_equal(actual.astype(ref.dtypes.to_dict()), ref, check_exact=True)
