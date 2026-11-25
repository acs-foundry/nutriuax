"""Suelos de seguridad (ADR-0004 §3). Viven en código, no en los TOML, y en modo hogar no se pueden desactivar.

    - Energía ≥ gasto basal (Mifflin) y déficit ≤ 20 % del gasto total.
    - Con déficit, proteína ≥ 1,2 g/kg.
    - Menores de 18 años: nunca déficit (energía ≥ su requerimiento EER), nunca perfil fuera de su rango de edad.

Si lo pedido (perfil, ajuste manual o energía fijada a mano) viola un suelo, se recorta al suelo y se devuelve un
aviso en `Objetivos.avisos`; nunca se lanza en silencio. Un perfil fuera de su rango de edad es un error.
"""
from __future__ import annotations

from .objetivos import Objetivos, Perfil, Persona, calcular_objetivos, gasto_total, tmb_mifflin

DEFICIT_MAX = 0.20
PROTEINA_MIN_DEFICIT = 1.2   # g/kg
MAYORIA = 18


class PerfilNoPermitido(ValueError):
    """El perfil no es aplicable a esta persona (p. ej. control en un menor)."""


def objetivos_seguros(p: Persona, perfil: Perfil, ajuste_pct: float | None = None) -> Objetivos:
    """Objetivos del perfil con los suelos aplicados. `ajuste_pct` (opcional) sustituye al punto medio del perfil."""
    if perfil.edad and not (perfil.edad[0] <= p.edad <= perfil.edad[1]):
        raise PerfilNoPermitido(
            f"El perfil «{perfil.nombre}» es para {perfil.edad[0]}-{perfil.edad[1]} años; esta persona tiene {p.edad}.")
    menor = p.edad < MAYORIA
    if menor and perfil.ajuste_pct and perfil.ajuste_pct[0] < 0:
        raise PerfilNoPermitido("A un menor de 18 años no se le aplica un perfil con déficit energético.")

    avisos: list[str] = []
    get = gasto_total(p, perfil)
    if p.kcal_manual:
        pedido = float(p.kcal_manual)
    else:
        aj = ajuste_pct if ajuste_pct is not None else (
            (perfil.ajuste_pct[0] + perfil.ajuste_pct[1]) / 2 if perfil.ajuste_pct else 0.0)
        pedido = get * (1 + aj / 100)

    if menor:
        suelo, motivo = get, "un menor de 18 años no debe seguir un déficit energético"
    else:
        basal = tmb_mifflin(p)
        suelo = max(basal, get * (1 - DEFICIT_MAX))
        motivo = (f"el déficit máximo es del {DEFICIT_MAX:.0%} del gasto total ({get:.0f} kcal) y nunca por debajo "
                  f"del gasto basal ({basal:.0f} kcal)")
    kcal = pedido
    if pedido < suelo - 0.5:
        kcal = suelo
        avisos.append(f"Se pidieron {pedido:.0f} kcal; se usan {suelo:.0f} kcal porque {motivo}.")

    prot = perfil.proteina_gkg
    if kcal < get - 0.5 and prot[0] < PROTEINA_MIN_DEFICIT:
        prot = (PROTEINA_MIN_DEFICIT, max(prot[1], PROTEINA_MIN_DEFICIT))
        avisos.append(f"Con déficit energético la proteína mínima es {PROTEINA_MIN_DEFICIT} g/kg "
                      f"(se sube desde {perfil.proteina_gkg[0]} g/kg).")

    persona = Persona(**{**p.__dict__, "kcal_manual": kcal})
    obj = calcular_objetivos(persona, perfil.copia(proteina_gkg=prot))
    obj.avisos = avisos
    return obj
