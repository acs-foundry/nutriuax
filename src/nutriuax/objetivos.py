"""Perfiles dietéticos y cálculo de objetivos diarios para una persona.

Los perfiles viven en config/perfiles/*.toml (ADR-0004, perfiles.py); cada uno cita sus fuentes.
Los valores por defecto son puntos de partida editables en la app, no prescripciones. Fuentes:
- Requerimientos de aminoácidos indispensables: WHO/FAO/UNU 2007 (TRS 935): Leu 39, Ile 20,
  Val 26, Lys 30, Thr 15, Trp 4, His 10 mg/kg/día (adulto).
- ERC: KDOQI Clinical Practice Guideline for Nutrition in CKD, 2020 update (Ikizler et al.,
  Am J Kidney Dis 2020): ERC 3-5 sin diálisis metabólicamente estable 0,55-0,6 g/kg/día;
  hemodiálisis 1,0-1,2 g/kg/día; energía 25-35 kcal/kg/día; sodio < 2,3 g/día.
- Protocolo cruzado normoproteico/hiperproteico: mediterránea ≈1,0-1,2 g/kg; hiperproteica ≈2,0-2,2 g/kg
  y >30 % kcal. Umbrales de adherencia en config/adherencia.toml: manda g/kg; el % de energía se
  persigue como objetivo blando en el generador y es solo informativo en la adherencia.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, replace

WHO_AA_MG_KG = dict(leu=39.0, ile=20.0, val=26.0, lys=30.0, thr=15.0, trp=4.0, his=10.0)

COMIDAS = ["D", "MM", "C", "M", "X"]
NOMBRE_COMIDA = {"D": "Desayuno", "MM": "Media mañana", "C": "Comida", "M": "Merienda", "X": "Cena"}
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# Reparto de energía por comida (fracción mín, máx) y estructura (grupo de roles → nº mín, máx)
REPARTO = {"D": (0.18, 0.28), "MM": (0.05, 0.15), "C": (0.30, 0.40), "M": (0.05, 0.15), "X": (0.20, 0.30)}
GRUPOS = {
    "lacteo_o_supl": {"lacteo", "suplemento"},
    "cereal": {"cereal"},
    "proteina_animal_o_tofu": {"proteina"},
    "plato_proteico": {"proteina", "legumbre"},
    "hidrato": {"cereal", "legumbre"},
    "verdura": {"verdura"},
    "fruta": {"fruta"},
    "grasa": {"grasa"},
    "frutos_secos": {"frutos_secos"},
    "dulce": {"dulce"},
    "suplemento": {"suplemento"},
    "todo": None,  # cualquier rol
}
PLANTILLAS = {
    "D": {"lacteo_o_supl": (1, 2), "cereal": (1, 1), "fruta": (0, 1), "grasa": (0, 1),
          "frutos_secos": (0, 1), "dulce": (0, 1), "proteina_animal_o_tofu": (0, 1), "verdura": (0, 1),
          "todo": (2, 5)},
    "MM": {"fruta": (0, 1), "lacteo_o_supl": (0, 1), "frutos_secos": (0, 1), "cereal": (0, 1),
           "proteina_animal_o_tofu": (0, 1), "dulce": (0, 1), "todo": (1, 3)},
    "M": {"fruta": (0, 1), "lacteo_o_supl": (0, 1), "frutos_secos": (0, 1), "cereal": (0, 1),
          "proteina_animal_o_tofu": (0, 1), "dulce": (0, 1), "todo": (1, 3)},
    "C": {"plato_proteico": (1, 2), "proteina_animal_o_tofu": (0, 1), "hidrato": (1, 2), "verdura": (1, 2),
          "fruta": (0, 1), "lacteo_o_supl": (0, 1), "grasa": (1, 2), "todo": (4, 7)},
    "X": {"plato_proteico": (1, 2), "proteina_animal_o_tofu": (0, 1), "hidrato": (0, 2), "verdura": (1, 2),
          "fruta": (0, 1), "lacteo_o_supl": (0, 1), "grasa": (1, 2), "todo": (3, 6)},
}


@dataclass
class Persona:
    codigo: str = "P001"  # código seudonimizado, nunca nombre
    sexo: str = "M"       # "M" mujer, "H" hombre
    edad: int = 22
    peso: float = 70.0
    talla: float = 172.0
    factor_actividad: float = 1.6
    masa_magra: float | None = None  # kg (DXA/BIA), opcional
    kcal_manual: float | None = None


@dataclass
class Perfil:
    clave: str
    nombre: str
    descripcion: str
    proteina_gkg: tuple[float, float]
    proteina_pct_min: float | None = None
    grasa_pct: tuple[float, float] = (25, 40)
    hc_pct: tuple[float, float] = (35, 60)
    agsat_pct_max: float | None = 10
    fibra_min: float | None = 25
    sodio_max: float | None = 2300
    potasio_max: float | None = None
    fosforo_max: float | None = None
    kcal_por_kg: float | None = None  # si se fija, sustituye a Mifflin × actividad
    aa_min_mgkg: dict[str, float] = field(default_factory=lambda: dict(WHO_AA_MG_KG))
    aa_max_mgkg: dict[str, float] = field(default_factory=dict)
    aa_por_masa_magra: bool = False
    aove_min_g: float | None = None
    fruta_min_dia: int = 2
    verdura_min_dia: int = 2
    semanal_min: dict[str, int] = field(default_factory=dict)  # etiqueta → nº mín de tomas/semana
    semanal_max: dict[str, int] = field(default_factory=dict)  # etiqueta → nº máx de tomas/semana
    excluir_etiquetas: set[str] = field(default_factory=set)
    comidas: list[str] = field(default_factory=lambda: list(COMIDAS))
    # energía (ADR-0004 §1, §5): por defecto Mifflin × actividad, como en v0.1
    energia_modo: str = "mifflin"      # mifflin | eer_iom_2005 (menores de 19 años)
    ajuste_pct: tuple[float, float] | None = None   # p. ej. (-20, -10) déficit, (5, 15) superávit; se usa el punto medio
    edad: tuple[int, int] | None = None              # rango de edad (años) en que el perfil es aplicable
    # metadatos (ADR-0004): no intervienen en el cálculo de objetivos
    fuentes: tuple[str, ...] = ()
    ambito: str = "clinico"            # estudio | clinico | hogar
    orden: int = 100                   # posición en los desplegables

    def copia(self, **kw) -> "Perfil":
        return replace(self, **kw)


def _cargar_perfiles() -> dict[str, "Perfil"]:
    """Perfiles desde config/perfiles/*.toml (ADR-0004), ordenados por `orden` y clave."""
    from .perfiles import cargar_perfiles
    todos = cargar_perfiles()
    return dict(sorted(todos.items(), key=lambda kv: (kv[1].orden, kv[0])))


PERFILES: dict[str, Perfil] = _cargar_perfiles()


def tmb_mifflin(p: Persona) -> float:
    """Gasto energético basal, Mifflin-St Jeor (1990)."""
    return 10 * p.peso + 6.25 * p.talla - 5 * p.edad + (5 if p.sexo == "H" else -161)


def eer_iom_2005(p: Persona) -> float:
    """Requerimiento estimado de energía (IOM 2005) para 9-18 años, incluye 25 kcal/día de crecimiento.
    El nivel de actividad (PA) se toma del factor de actividad (PAL): < 1,4 sedentario, < 1,6 poco activo,
    < 1,9 activo, ≥ 1,9 muy activo."""
    niveles = (1.4, 1.6, 1.9)
    i = sum(p.factor_actividad >= x for x in niveles)
    h_m = p.talla / 100
    if p.sexo == "H":
        pa = (1.00, 1.13, 1.26, 1.42)[i]
        return 88.5 - 61.9 * p.edad + pa * (26.7 * p.peso + 903 * h_m) + 25
    pa = (1.00, 1.16, 1.31, 1.56)[i]
    return 135.3 - 30.8 * p.edad + pa * (10.0 * p.peso + 934 * h_m) + 25


def gasto_total(p: Persona, perfil: Perfil) -> float:
    """Gasto energético total sin ajuste de déficit/superávit."""
    if perfil.kcal_por_kg:
        return perfil.kcal_por_kg * p.peso
    if perfil.energia_modo == "eer_iom_2005":
        return eer_iom_2005(p)
    return tmb_mifflin(p) * p.factor_actividad


def kcal_objetivo(p: Persona, perfil: Perfil) -> float:
    if p.kcal_manual:
        return float(p.kcal_manual)
    get = gasto_total(p, perfil)
    if perfil.ajuste_pct:
        get *= 1 + (perfil.ajuste_pct[0] + perfil.ajuste_pct[1]) / 200
    return get


@dataclass
class Objetivos:
    kcal: float
    proteina: tuple[float, float]           # g/día
    proteina_pct_min: float | None
    grasa_pct: tuple[float, float]
    hc_pct: tuple[float, float]
    agsat_pct_max: float | None
    minimos: dict[str, float]               # nutriente → mínimo diario (g o mg)
    maximos: dict[str, float]               # nutriente → máximo diario
    kg_referencia: float                    # kg usados para mg/kg de AA
    perfil: Perfil
    peso: float = 70.0
    avisos: list[str] = field(default_factory=list)   # suelos de seguridad aplicados (seguridad.py)

    def como_dict(self) -> dict:
        d = asdict(self)
        d["perfil"] = self.perfil.clave
        return d


def avisos_coherencia(obj: "Objetivos") -> list[str]:
    """Detecta objetivos que no pueden cumplirse a la vez (p. ej. g/kg frente a % de energía)."""
    av = []
    if obj.proteina_pct_min:
        pct_max_posible = 400 * obj.proteina[1] / obj.kcal
        if pct_max_posible < obj.proteina_pct_min:
            kcal_lim = 400 * obj.proteina[1] / obj.proteina_pct_min
            av.append(
                f"Con {obj.proteina[1]:.0f} g de proteína (máximo del rango) y {obj.kcal:.0f} kcal, la proteína "
                f"aporta como mucho el {pct_max_posible:.1f} % de la energía; para llegar al "
                f"{obj.proteina_pct_min:.0f} % la energía tendría que ser ≤ {kcal_lim:.0f} kcal. "
                "Se prioriza el rango en g/kg.")
    lo_pct = 400 * obj.proteina[0] / obj.kcal
    if lo_pct + obj.grasa_pct[0] + obj.hc_pct[0] > 101:
        av.append("Los mínimos de proteína, grasa y HC suman más del 100 % de la energía.")
    return av


def calcular_objetivos(p: Persona, perfil: Perfil) -> Objetivos:
    kg_aa = p.masa_magra if (perfil.aa_por_masa_magra and p.masa_magra) else p.peso
    minimos = {a: v * kg_aa for a, v in perfil.aa_min_mgkg.items()}
    maximos = {a: v * kg_aa for a, v in perfil.aa_max_mgkg.items()}
    if perfil.fibra_min:
        minimos["fibra"] = perfil.fibra_min
    for n in ("sodio", "potasio", "fosforo"):
        v = getattr(perfil, f"{n}_max")
        if v:
            maximos[n] = v
    return Objetivos(
        kcal=kcal_objetivo(p, perfil),
        proteina=(perfil.proteina_gkg[0] * p.peso, perfil.proteina_gkg[1] * p.peso),
        proteina_pct_min=perfil.proteina_pct_min,
        grasa_pct=perfil.grasa_pct, hc_pct=perfil.hc_pct, agsat_pct_max=perfil.agsat_pct_max,
        minimos=minimos, maximos=maximos, kg_referencia=kg_aa, perfil=perfil, peso=p.peso)
