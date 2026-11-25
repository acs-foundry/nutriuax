# 0003 · Alimentos cocinados: estado de pesada, técnica culinaria y recetas

- Fecha: 2026-10-30 · Estado: aceptada (DEC del 30-10-2026, ampliación NutriUAX)
- Contexto: en el registro de 3 días y al editar menús se pesa unas veces en crudo y otras en cocinado
  (80 g de arroz crudo ≈ 240 g cocido), la técnica cambia agua y grasa (plancha frente a frito) y mucha comida
  española son platos (lentejas con chorizo, tortilla de patata). Con una fila por alimento «tal como se come»
  (v0.1) el error en proteína y Leu/Ile/Val puede superar el 10 % del criterio frente a Odimet.
- Decisión:
  1. **Alimento base en crudo.** Cada alimento de la base apunta a su código FDC crudo (o «tal cual» si no se
     cocina: fruta, pan, lácteos). Las versiones cocinadas no son filas nuevas: se derivan.
  2. **Estado de pesada** (`crudo` | `cocinado`) en cada línea del menú y del registro. Si es `cocinado`, los
     gramos se pasan a equivalente crudo con el **factor de rendimiento** de la técnica:
     `g_crudo = g_cocinado / rendimiento` (p. ej. arroz hervido 2,8; pechuga a la plancha 0,75).
  3. **Técnica culinaria** (`crudo`, `hervido`, `plancha`, `horno`, `frito`, `guisado`, `vapor`, `microondas`)
     en `data/coccion.csv` por grupo de alimento (y excepciones por alimento): rendimiento en peso, factores de
     retención de nutrientes y **aceite absorbido** (g por 100 g cocinado) que se añade como AOVE.
     Proteína y aminoácidos: retención ≈ 1 salvo hervido largo con caldo desechado (factor del grupo).
  4. **Recetas** en `data/recetas.csv`: plato → ingredientes en crudo (g por ración) + técnica + rendimiento
     del plato. Una ración de plato se descompone en sus ingredientes; el resultado es el mismo motor.
  5. Si FDC tiene el alimento ya cocinado con aminoácidos (p. ej. legumbre hervida), se puede usar como
     **control**: el test compara crudo × rendimiento frente al código cocinado (tolerancia 10 %).
- Fuentes de factores: USDA *Table of Cooking Yields for Meat and Poultry* (2014) y *Table of Nutrient Retention
  Factors, Release 6* (2007; incluido en el zip SR Legacy como `retention_factor.csv`); Bognár A. (2002) *Tables
  on weight yield of food and retention factors of food constituents for the calculation of nutrient composition
  of cooked foods (dishes)*, BFE, para técnicas y aceite de fritura. Cada fila de `coccion.csv` lleva su fuente.
- Alternativas descartadas:
  - Una fila por alimento × técnica (crudo, hervido, frito…): multiplica la base por 5 y los aminoácidos de los
    cocinados faltan en FDC con frecuencia.
  - Pedir siempre peso crudo: no se puede en el registro de 3 días (el participante pesa lo que come).
- Consecuencias: la base crece en alimentos, no en variantes; las recetas son CSV editables por la dietista.
  El generador sigue optimizando en crudo y muestra a la vez g crudo y g cocinado. Coste: mantener `coccion.csv`
  y `recetas.csv` revisados. Revertir: basta con tratar toda línea como `crudo` (rendimiento 1).
