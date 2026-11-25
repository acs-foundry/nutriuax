"""Vademécum clínico de interacciones fármaco-nutriente (paridad DietoPro / práctica clínica).

Evalúa la medicación declarada del paciente frente al menú generado o su resumen diario, generando
alertas trazables con severidad (`alta` | `media` | `baja`), mecanismo fisiológico, alimentos o
umbrales nutricionales disparados (potasio, fósforo, calcio, sodio, proteína/BCAA, vitamina K,
tiramina, pomelo, separación horaria) y recomendaciones prácticas para consulta.

Aviso: herramienta de apoyo a la decisión dietética; no sustituye la revisión médica/farmacéutica.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .generador import Menu


@dataclass(frozen=True)
class ReglaFarmaco:
    clave: str
    nombre: str
    clase: str
    severidad_base: str  # "alta" | "media" | "baja"
    nutrientes_clave: tuple[str, ...]
    alimentos_vigilar: tuple[str, ...]
    mecanismo: str
    recomendacion: str
    referencia: str


VADEMECUM: dict[str, ReglaFarmaco] = {
    "acenocumarol_warfarina": ReglaFarmaco(
        clave="acenocumarol_warfarina",
        nombre="Acenocumarol / Warfarina (Sintrom®)",
        clase="Anticoagulantes antagonistas de vitamina K",
        severidad_base="alta",
        nutrientes_clave=("vitamina_k",),
        alimentos_vigilar=("espinacas", "brocoli", "coliflor", "lechuga", "judias_verdes"),
        mecanismo="Fluctuaciones bruscas en la ingesta de vitamina K antagonizan el efecto anticoagulante (desestabilizan el INR).",
        recomendacion="Mantener constante el consumo diario de verdura de hoja verde (espinacas, brócoli, lechuga); no eliminar ni doblar bruscamente.",
        referencia="Holbrook et al., Chest 2012 (ACCP Antithrombotic Guidelines).",
    ),
    "levotiroxina": ReglaFarmaco(
        clave="levotiroxina",
        nombre="Levotiroxina (Eutirox®)",
        clase="Hormona tiroidea",
        severidad_base="alta",
        nutrientes_clave=("calcio", "fibra", "soja"),
        alimentos_vigilar=("leche_entera", "leche_semi", "yogur_natural", "yogur_griego", "queso_fresco", "tofu", "avena", "pan_integral"),
        mecanismo="Calcio, fibra soluble, soja, café y suplementos de hierro reducen significativamente la absorción intestinal de levotiroxina.",
        recomendacion="Tomar en ayunas con agua al menos 30–60 min antes del desayuno; separar ≥ 4 h de suplementos de calcio/hierro o grandes raciones de soja.",
        referencia="Jonklaas et al., Thyroid 2014 (ATA Guidelines).",
    ),
    "ieca_ara2": ReglaFarmaco(
        clave="ieca_ara2",
        nombre="IECA / ARA-II (Enalapril, Ramipril, Losartán)",
        clase="Antihipertensivos / Nefroprotectores",
        severidad_base="alta",
        nutrientes_clave=("potasio", "sodio"),
        alimentos_vigilar=("platano", "espinacas", "patata", "boniato", "alubias", "aguacate", "almendras", "nueces"),
        mecanismo="Inhibición del eje SRAA reduce la excreción renal de potasio (riesgo de hiperpotasemia, especialmente en ERC) y el exceso de sodio atenúa el efecto antihipertensivo.",
        recomendacion="Vigilar potasio total si hay ERC (aplicar doble cocción y evitar sustitutos de sal con KCl) y mantener sodio < 2.000–2.300 mg/día.",
        referencia="KDIGO 2024 CKD Guideline; ESC Hypertension Guidelines.",
    ),
    "espironolactona": ReglaFarmaco(
        clave="espironolactona",
        nombre="Espironolactona / Eplerenona / Finerenona",
        clase="Antagonistas del receptor mineralocorticoide",
        severidad_base="alta",
        nutrientes_clave=("potasio", "sodio"),
        alimentos_vigilar=("platano", "espinacas", "alubias", "patata", "boniato", "aguacate", "chocolate_negro"),
        mecanismo="Diuréticos ahorradores de potasio: riesgo elevado de hiperpotasemia grave con dietas ricas en potasio o sales potásicas.",
        recomendacion="Monitorizar potasio sérico y evitar cargas altas (> 3.000 mg/día en riesgo renal); prohibir sales bajas en sodio enriquecidas con potasio.",
        referencia="KDIGO 2024; ESC Heart Failure Guidelines.",
    ),
    "furosemida": ReglaFarmaco(
        clave="furosemida",
        nombre="Furosemida / Torasemida",
        clase="Diuréticos de asa",
        severidad_base="media",
        nutrientes_clave=("potasio", "sodio", "calcio", "magnesio"),
        alimentos_vigilar=("jamon_serrano", "queso_curado", "aceitunas", "atun_lata"),
        mecanismo="Aumentan la excreción urinaria de potasio, magnesio, calcio y tiamina; el exceso de sodio reduce su eficacia descongestiva.",
        recomendacion="Asegurar aporte adecuado de potasio (salvo hiperpotasemia), magnesio y calcio; limitar sodio < 2.000 mg/día.",
        referencia="ESC Heart Failure Guidelines; Boullata & Hudson, Nutr Clin Pract 2012.",
    ),
    "tiazidas": ReglaFarmaco(
        clave="tiazidas",
        nombre="Hidroclorotiazida / Clortalidona / Indapamida",
        clase="Diuréticos tiazídicos",
        severidad_base="media",
        nutrientes_clave=("potasio", "sodio", "calcio"),
        alimentos_vigilar=("jamon_serrano", "queso_curado", "aceitunas"),
        mecanismo="Pérdida urinaria de potasio y magnesio con reducción de calciuria (riesgo de hipopotasemia e hiponatremia).",
        recomendacion="Mantener dieta rica en frutas/verduras (potasio), controlar sodio y vigilar suplementos altos de calcio.",
        referencia="ESC Hypertension Guidelines 2024.",
    ),
    "estatinas": ReglaFarmaco(
        clave="estatinas",
        nombre="Estatinas (Simvastatina, Atorvastatina, Lovastatina)",
        clase="Hipolipemiantes",
        severidad_base="media",
        nutrientes_clave=("agsat", "fibra"),
        alimentos_vigilar=("queso_curado", "jamon_serrano", "chocolate_negro"),
        mecanismo="Las furanocumarinas del pomelo inhiben CYP3A4 intestinal y multiplican la exposición plasmática a simvastatina/atorvastatina (riesgo de miopatía).",
        recomendacion="Evitar pomelo y zumo de pomelo; potenciar fibra soluble (avena, legumbres) y limitar grasas saturadas (< 7–10 % kcal).",
        referencia="FDA Drug Safety Communication; ESC/EAS Dyslipidaemia Guidelines.",
    ),
    "levodopa": ReglaFarmaco(
        clave="levodopa",
        nombre="Levodopa / Carbidopa",
        clase="Antiparkinsoniano",
        severidad_base="alta",
        nutrientes_clave=("proteina", "leu", "ile", "val", "phe"),
        alimentos_vigilar=("pollo_pechuga", "pavo_pechuga", "ternera_magra", "proteina_suero", "queso_curado", "salmon"),
        mecanismo="Los aminoácidos neutros grandes (LNAA: Leu, Ile, Val, Phe, Tyr, Trp) compiten con levodopa en el transportador LAT1 intestinal y hematoencefálico.",
        recomendacion="Tomar levodopa 30–60 min antes de las comidas; considerar dieta de redistribución proteica (concentrar la mayor parte de la proteína en la cena).",
        referencia="Virmani et al., Mov Disord Clin Pract 2016; ESPEN Clinical Nutrition in Neurology.",
    ),
    "metformina": ReglaFarmaco(
        clave="metformina",
        nombre="Metformina",
        clase="Antidiabético oral (biguanida)",
        severidad_base="media",
        nutrientes_clave=("vitamina_b12", "fibra"),
        alimentos_vigilar=(),
        mecanismo="El uso crónico altera la absorción dependiente de calcio del complejo factor intrínseco–vitamina B12 en íleon terminal.",
        recomendacion="Tomar con las comidas para mejorar tolerancia digestiva; asegurar fuentes animales/fortificadas de B12 y monitorizar B12 sérica anual.",
        referencia="ADA Standards of Care in Diabetes 2025.",
    ),
    "bifosfonatos": ReglaFarmaco(
        clave="bifosfonatos",
        nombre="Alendronato / Risedronato / Ibandronato",
        clase="Bifosfonatos orales",
        severidad_base="alta",
        nutrientes_clave=("calcio",),
        alimentos_vigilar=("leche_entera", "leche_semi", "yogur_natural", "queso_fresco", "queso_curado", "almendras"),
        mecanismo="Los cationes divalentes (calcio, magnesio, hierro) quelan el bifosfonato y bloquean casi por completo su biodisponibilidad (< 1 %).",
        recomendacion="Tomar en ayunas solo con agua del grifo/mineral baja en calcio; esperar ≥ 30–60 min antes de ingerir cualquier alimento o lácteo.",
        referencia="NOGG / SEIOMM Osteoporosis Guidelines.",
    ),
    "quelantes_fosforo": ReglaFarmaco(
        clave="quelantes_fosforo",
        nombre="Quelantes de fósforo (Sevelámero, Carbonato cálcico, Sucroferrico)",
        clase="Nefrología / Control de hiperfosfatemia",
        severidad_base="alta",
        nutrientes_clave=("fosforo", "calcio", "proteina"),
        alimentos_vigilar=("queso_curado", "almendras", "avena", "sardinas", "nueces", "cacahuetes", "proteina_suero"),
        mecanismo="Deben coincidir en la luz intestinal con el fósforo dietético para formar complejos insolubles no absorbibles; además sevelámero puede reducir absorción de vitaminas liposolubles.",
        recomendacion="Administrar SIEMPRE en el momento de las comidas principales proporcionalmente al fósforo del plato; priorizar relación P/proteína < 12–14 mg/g y evitar aditivos fosfóricos.",
        referencia="KDOQI Clinical Practice Guideline for Nutrition in CKD 2020.",
    ),
    "ibp": ReglaFarmaco(
        clave="ibp",
        nombre="Inhibidores de la bomba de protones (Omeprazol, Pantoprazol)",
        clase="Antiulceroso / Antisecretor",
        severidad_base="baja",
        nutrientes_clave=("calcio", "vitamina_b12", "magnesio", "hierro"),
        alimentos_vigilar=(),
        mecanismo="La hipoclorhidria sostenida reduce la liberación de B12 proteica y la absorción de hierro no hemo, magnesio y carbonato cálcico.",
        recomendacion="En tratamientos prolongados asegurar ingesta adecuada de calcio (1.000–1.200 mg/día), magnesio, hierro con vitamina C y controlar B12/Mg.",
        referencia="Freedberg et al., Gastroenterology 2017 (AGA Clinical Practice Update).",
    ),
    "corticoides": ReglaFarmaco(
        clave="corticoides",
        nombre="Corticoides sistémicos (Prednisona, Dexametasona)",
        clase="Antiinflamatorio / Inmunosupresor",
        severidad_base="media",
        nutrientes_clave=("sodio", "calcio", "proteina", "hc"),
        alimentos_vigilar=("miel", "mermelada", "jamon_serrano", "queso_curado", "pan_blanco"),
        mecanismo="Inducen catabolismo proteico muscular, hiperglucemia, retención hidrosalina y pérdida ósea (menor absorción intestinal de calcio).",
        recomendacion="Asegurar proteína ≥ 1,2 g/kg/día (si función renal lo permite), calcio ≥ 1.000–1.200 mg/día + vit D, sodio < 2.000 mg/día y HC de bajo índice glucémico.",
        referencia="ACR Glucocorticoid-Induced Osteoporosis Guideline 2022.",
    ),
    "litio": ReglaFarmaco(
        clave="litio",
        nombre="Carbonato de litio",
        clase="Estabilizador del ánimo",
        severidad_base="alta",
        nutrientes_clave=("sodio",),
        alimentos_vigilar=("jamon_serrano", "queso_curado", "aceitunas"),
        mecanismo="El litio compite con el sodio en la reabsorción tubular renal: una restricción brusca de sodio o deshidratación eleva la litemia a rango tóxico.",
        recomendacion="Mantener ingesta diaria de sodio ESTABLE (evitar dietas hiposódicas estrictas repentinas) e hidratación constante (2–2,5 L/día).",
        referencia="NICE Bipolar Disorder Guidelines; Boullata & Armenti Handbook of Drug-Nutrient Interactions.",
    ),
    "imao": ReglaFarmaco(
        clave="imao",
        nombre="IMAO clásicos (Tranilcipromina, Fenelzina, Linezolid)",
        clase="Antidepresivo / Antibiótico oxazolidinona",
        severidad_base="alta",
        nutrientes_clave=("tiramina",),
        alimentos_vigilar=("queso_curado", "jamon_serrano", "aguacate", "chocolate_negro", "tofu"),
        mecanismo="Inhibición de MAO-A impide degradar tiramina dietética, pudiendo desencadenar crisis hipertensiva severa («efecto queso»).",
        recomendacion="Evitar quesos curados, embutidos curados, fermentados de soja, pescados ahumados/en escabeche y alimentos sobremaduros.",
        referencia="Flockhart / FDA Prescribing Information for MAOIs & Linezolid.",
    ),
    "tetraciclinas_quinolonas": ReglaFarmaco(
        clave="tetraciclinas_quinolonas",
        nombre="Tetraciclinas y Fluoroquinolonas (Doxiciclina, Ciprofloxacino)",
        clase="Antibióticos",
        severidad_base="media",
        nutrientes_clave=("calcio", "hierro", "magnesio"),
        alimentos_vigilar=("leche_entera", "leche_semi", "yogur_natural", "yogur_griego", "queso_fresco", "queso_curado"),
        mecanismo="Forman quelatos insolubles con calcio, magnesio, zinc y hierro, reduciendo la absorción antibiótica hasta un 50–80 %.",
        recomendacion="Separar la toma ≥ 2 h antes o después de lácteos, bebidas vegetales fortificadas con calcio o suplementos minerales.",
        referencia="Sanford Guide; Lexicomp Drug-Food Interactions.",
    ),
    "digoxina": ReglaFarmaco(
        clave="digoxina",
        nombre="Digoxina",
        clase="Glucósido cardíaco",
        severidad_base="media",
        nutrientes_clave=("fibra", "potasio"),
        alimentos_vigilar=("avena", "pan_integral", "lentejas", "garbanzos"),
        mecanismo="La fibra dietética alta en la misma toma puede adsorber digoxina; la hipopotasemia predispone a toxicidad digitálica grave.",
        recomendacion="Tomar separada de comidas muy ricas en fibra de salvado/avena y mantener potasio sérico en rango normal.",
        referencia="ESC Heart Failure Guidelines; Boullata & Hudson 2012.",
    ),
    "ciclosporina_tacrolimus": ReglaFarmaco(
        clave="ciclosporina_tacrolimus",
        nombre="Tacrolimus / Ciclosporina (Inhibidores de calcineurina)",
        clase="Inmunosupresor (trasplante)",
        severidad_base="alta",
        nutrientes_clave=("potasio", "magnesio", "sodio"),
        alimentos_vigilar=("platano", "espinacas", "patata", "aguacate"),
        mecanismo="Inhibición de CYP3A4/P-gp por pomelo o hipérico altera niveles plasmáticos; producen hiperpotasemia, hipomagnesemia e hipertensión.",
        recomendacion="Evitar estrictamente pomelo, granada en exceso e hipérico; tomar siempre en igual relación con las comidas y vigilar potasio/magnesio/higiene alimentaria.",
        referencia="KDIGO Kidney Transplant Guideline.",
    ),
    "metotrexato": ReglaFarmaco(
        clave="metotrexato",
        nombre="Metotrexato",
        clase="FAME / Antimetabolito antifolato",
        severidad_base="media",
        nutrientes_clave=("folato",),
        alimentos_vigilar=("espinacas", "brocoli", "lentejas", "garbanzos"),
        mecanismo="Antagoniza la dihidrofolato reductasa produciendo depleción de folatos y riesgo de toxicidad mucosa/hematológica.",
        recomendacion="Mantener consumo regular de verduras ricas en folato, coordinar suplemento prescrito de ácido fólico (en días distintos a la toma) y evitar alcohol.",
        referencia="EULAR Recommendations for Rheumatoid Arthritis.",
    ),
    "insulina_sulfonilureas": ReglaFarmaco(
        clave="insulina_sulfonilureas",
        nombre="Insulina / Sulfonilureas (Gliclazida, Glimepirida)",
        clase="Antidiabéticos con riesgo de hipoglucemia",
        severidad_base="alta",
        nutrientes_clave=("hc", "fibra"),
        alimentos_vigilar=("miel", "mermelada", "pan_blanco", "arroz_blanco"),
        mecanismo="Desajuste entre dosis de insulina/secretagogo y carga de hidratos de carbono por toma provoca hipoglucemia o picos postprandiales.",
        recomendacion="Repartir hidratos de carbono complejos de forma regular en cada comida usando el sistema de intercambios (1 intercambio = 20 g HC) y priorizar fibra ≥ 25–30 g/día.",
        referencia="ADA Standards of Care in Diabetes 2025.",
    ),
    "sglt2": ReglaFarmaco(
        clave="sglt2",
        nombre="Inhibidores SGLT2 (Empagliflozina, Dapagliflozina)",
        clase="Antidiabético / Cardiorrenal",
        severidad_base="media",
        nutrientes_clave=("hc",),
        alimentos_vigilar=(),
        mecanismo="Dietas cetogénicas muy bajas en HC (< 50–100 g/día) o ayunos prolongados aumentan el riesgo de cetoacidosis diabética euglucémica.",
        recomendacion="Evitar dietas cetogénicas estrictas o ayunos prolongados; asegurar aporte mínimo moderado de hidratos de carbono e hidratación.",
        referencia="ADA/KDIGO Consensus Report on Diabetes Management in CKD 2022.",
    ),
    "glp1": ReglaFarmaco(
        clave="glp1",
        nombre="Agonistas GLP-1 / GIP (Semaglutida, Tirzepatida, Liraglutida)",
        clase="Incretinomimético",
        severidad_base="media",
        nutrientes_clave=("proteina", "leu", "fibra", "grasa"),
        alimentos_vigilar=("queso_curado", "aceitunas", "chocolate_negro"),
        mecanismo="El enlentecimiento del vaciado gástrico y el déficit calórico marcado elevan el riesgo de pérdida de masa magra y síntomas digestivos con comidas grasas.",
        recomendacion="Priorizar densidad proteica (≥ 1,2–1,5 g/kg peso ajustado y ≥ 2,5 g leucina/toma principal), raciones pequeñas, baja grasa saturada e hidratación/fibra.",
        referencia="Mozaffarian et al., Obesity / Am J Clin Nutr 2025 (Nutritional Priorities with GLP-1).",
    ),
    "alopurinol": ReglaFarmaco(
        clave="alopurinol",
        nombre="Alopurinol / Febuxostat (Hiperuricemia / Gota)",
        clase="Hipouricemiante",
        severidad_base="baja",
        nutrientes_clave=("purinas", "proteina"),
        alimentos_vigilar=("sardinas", "mejillones", "gambas", "ternera_magra", "lomo_cerdo", "atun_lata"),
        mecanismo="Exceso de purinas de origen animal (vísceras, pescado azul pequeño, mariscos, carne roja) y fructosa añadida aumentan la producción de ácido úrico.",
        recomendacion="Moderar marisco, sardinas y carne roja; priorizar lácteos desnatados/semi, huevos y proteínas vegetales (legumbres no aumentan brotes de gota) e hidratación alta.",
        referencia="ACR Guideline for the Management of Gout 2020.",
    ),
    "hierro_oral": ReglaFarmaco(
        clave="hierro_oral",
        nombre="Hierro oral (Sulfato ferroso, Ferroglicina)",
        clase="Suplemento antianémico",
        severidad_base="media",
        nutrientes_clave=("calcio", "fibra"),
        alimentos_vigilar=("leche_entera", "leche_semi", "yogur_natural", "queso_fresco", "avena", "pan_integral"),
        mecanismo="Calcio, fitatos (cereales integrales/legumbres) y polifenoles (té/café) inhiben la absorción de hierro no hemo; la vitamina C la potencia.",
        recomendacion="Tomar preferiblemente con fruta rica en vitamina C (naranja, kiwi, fresas) y separado ≥ 2 h de lácteos, café o té.",
        referencia="WHO / British Society of Gastroenterology Iron Deficiency Guidelines.",
    ),
}


def listar_farmacos() -> list[dict[str, Any]]:
    """Lista todo el vademécum disponible con sus metadatos clínicos."""
    return [asdict(r) for r in VADEMECUM.values()]


def evaluar_interacciones(
    medicamentos: list[str],
    menu: Menu | None = None,
    resumen_diario: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Evalúa alertas fármaco-nutriente para una lista de claves del vademécum y un menú o resumen.

    Detecta automáticamente alimentos presentes en el menú que requieren vigilancia y verifica
    umbrales cuantitativos (potasio, sodio, fósforo, calcio, proteína, HC, leucina).
    """
    alimentos_presentes: dict[str, str] = {}
    medias: dict[str, float] = dict(resumen_diario or {})

    if menu is not None:
        for r in menu.items[["id", "nombre"]].drop_duplicates().itertuples(index=False):
            alimentos_presentes[str(r.id)] = str(r.nombre)
        for col in ("kcal", "proteina", "proteina_gkg", "grasa", "agsat", "hc", "fibra",
                    "sodio", "potasio", "fosforo", "calcio", "leu"):
            if col in menu.resumen.columns and col not in medias:
                medias[col] = float(menu.resumen[col].mean())

    alertas: list[dict[str, Any]] = []
    desconocidos: list[str] = []

    for med in medicamentos:
        clave = med.strip().lower()
        if clave not in VADEMECUM:
            desconocidos.append(med)
            continue
        regla = VADEMECUM[clave]
        disparadores: list[str] = []
        encontrados = [alimentos_presentes[a] for a in regla.alimentos_vigilar if a in alimentos_presentes]
        if encontrados:
            disparadores.append("Alimentos presentes a vigilar: " + ", ".join(encontrados))

        k_mg = medias.get("potasio")
        na_mg = medias.get("sodio")
        p_mg = medias.get("fosforo")
        ca_mg = medias.get("calcio")
        hc_g = medias.get("hc")
        prot_gkg = medias.get("proteina_gkg")
        kcal = medias.get("kcal")
        agsat = medias.get("agsat")

        if clave in ("ieca_ara2", "espironolactona", "ciclosporina_tacrolimus") and k_mg and k_mg > 3000:
            disparadores.append(f"Potasio medio elevado ({k_mg:.0f} mg/día > 3.000 mg/día): revisar función renal y técnica de cocción.")
        if clave in ("ieca_ara2", "espironolactona", "furosemida", "tiazidas", "corticoides") and na_mg and na_mg > 2300:
            disparadores.append(f"Sodio medio ({na_mg:.0f} mg/día) supera 2.300 mg/día.")
        if clave == "litio" and na_mg is not None and na_mg < 1500:
            disparadores.append(f"Sodio bajo ({na_mg:.0f} mg/día < 1.500 mg/día): riesgo de elevación de litemia si es cambio brusco.")
        if clave == "quelantes_fosforo" and p_mg and p_mg > 1000:
            disparadores.append(f"Fósforo medio ({p_mg:.0f} mg/día > 1.000 mg/día): ajustar pauta de quelante con las comidas.")
        if clave == "levodopa" and prot_gkg and prot_gkg >= 1.0:
            disparadores.append(f"Proteína media {prot_gkg:.2f} g/kg/día: aplicar separación horaria o redistribución proteica vespertina.")
        if clave == "sglt2" and hc_g is not None and hc_g < 100:
            disparadores.append(f"HC bajos ({hc_g:.0f} g/día < 100 g/día): precaución por riesgo de cetoacidosis euglucémica.")
        if clave == "glp1" and prot_gkg is not None and prot_gkg < 1.2:
            disparadores.append(f"Proteína media ({prot_gkg:.2f} g/kg/día < 1,2 g/kg): reforzar proteína/leucina para preservar masa magra.")
        if clave == "corticoides" and ca_mg is not None and ca_mg < 1000:
            disparadores.append(f"Calcio dietético ({ca_mg:.0f} mg/día < 1.000 mg/día): valorar lácteos/fuentes de calcio o suplementación.")
        if clave == "estatinas" and kcal and agsat and (900.0 * agsat / kcal) > 10.0:
            disparadores.append(f"Grasa saturada ({900.0 * agsat / kcal:.1f} % kcal > 10 %): reforzar patrón hipolipemiante.")

        severidad = regla.severidad_base
        if disparadores and severidad == "baja":
            severidad = "media"

        alertas.append(
            {
                "clave": regla.clave,
                "farmaco": regla.nombre,
                "clase": regla.clase,
                "severidad": severidad,
                "mecanismo": regla.mecanismo,
                "recomendacion": regla.recomendacion,
                "disparadores": disparadores,
                "alimentos_detectados": encontrados,
                "referencia": regla.referencia,
            }
        )

    orden_sev = {"alta": 0, "media": 1, "baja": 2}
    alertas.sort(key=lambda a: (orden_sev.get(a["severidad"], 9), a["farmaco"]))

    return {
        "total_alertas": len(alertas),
        "altas": sum(1 for a in alertas if a["severidad"] == "alta"),
        "medias": sum(1 for a in alertas if a["severidad"] == "media"),
        "bajas": sum(1 for a in alertas if a["severidad"] == "baja"),
        "alertas": alertas,
        "desconocidos": desconocidos,
    }
