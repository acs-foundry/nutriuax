# 0006 · Recetas de una biblioteca externa y tabla curada de equivalencias ingrediente → alimento

- Fecha: 2026-10-30 · Estado: aceptada. Completa ADR-0003 para recetas.
- Contexto: el Menú Familiar tiene 1.057 recetas (`biblioteca_completa_v2.json`) con 7.109 ingredientes y 1.800
  nombres distintos, en g (48 %), ud (31 %) y ml (21 %), por ración de adulto y en crudo. `base_fdc.buscar()`
  falla con ingredientes reales («huevo» → berenjena, «vino blanco» → vinagre, «arroz» → fideos de arroz).
- Decisión:
  1. **La biblioteca no se copia**: se lee de la ruta de `config/fuentes.toml` (`recetas.biblioteca`) o de
     `--recetas`. El repo solo trae una mini-biblioteca sintética del mismo formato para tests.
  2. **Equivalencias curadas** en `data/equivalencias_ingredientes.csv`: `patron` (nombre normalizado o regex
     anclada) → `alimento` canónico (≈ 250, cada uno con NDB **crudo** o `nulo` para sal, agua, especias),
     `g_por_ud`, `g_por_ml` (densidad), `confianza` (alta/media/baja) y `revisar` (sí/no, para la dietista).
     Se genera con ayuda (reglas + Claude) y se revisa a mano; el programa nunca empareja por búsqueda libre al
     calcular: si un ingrediente no está en la tabla, la receta lleva aviso y su % de gramos sin mapear.
  3. **Normalizador** previo: minúsculas, sin tildes, sin cantidades, sin paréntesis ni preparaciones
     («picado», «en dados», «a temperatura ambiente»), singular.
  4. **Informe de cobertura** (`scripts/cobertura_equivalencias.py`): % de gramos de la biblioteca mapeados
     (objetivo ≥ 95 %), top ingredientes sin mapear y lista de dudosas.
  5. Nutrientes de una receta = suma de ingredientes en crudo (ADR-0003: los gramos de la biblioteca ya son
     crudos y el aceite de fritura viene como ingrediente). El peso cocinado y la retención (T16) solo afectan a
     mostrar «g en el plato»; no cambian proteína ni aminoácidos.
  6. **Alérgenos**: los de la receta normalizados a los 14 de la UE (lacteos→leche, gluten→cereales con gluten,
     frutos_cascara→frutos de cáscara…; altramuces no viene en la biblioteca) **más** los deducidos de sus
     ingredientes por la tabla de equivalencias (columna `alergenos`); se usa la unión.
- Alternativas descartadas: emparejar en tiempo de cálculo con `buscar()` (errores silenciosos); duplicar una
  biblioteca externa privada en el repo; crear un alimento FDC por cada uno de los 1.800
  nombres (inmantenible; la mayoría son variantes del mismo alimento).
- Consecuencias: la calidad nutricional depende de la tabla; por eso es un CSV revisable con informe. Una receta
  nueva en la biblioteca solo necesita filas nuevas si trae ingredientes nuevos.
- Nota de implementación (T22, 30-10-2026): la tabla se partió en dos ficheros: `data/alimentos_canonicos.csv`
  (206 alimentos: NDB, descripción FDC, g/ud, g/ml, alérgenos; generado desde `scripts/canonicos_fuente.csv`) y
  `data/equivalencias_ingredientes.csv` (≈ 240 reglas en orden; si no encaja, se reintenta quitando «lomos de»,
  «filetes de», «rodajas de»…). Cobertura con la biblioteca v2: **98,3 % de los gramos**; 88 % de las recetas con
  ≥ 95 % de sus gramos (informe en `data/cobertura_equivalencias.md`; dudosas en `data/equivalencias_revisar.csv`).

