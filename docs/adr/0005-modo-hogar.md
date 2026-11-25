# 0005 · Modo hogar: platos compartidos, raciones por miembro, optimización en dos etapas

- Fecha: 2026-10-30 · Estado: aceptada (SM, 30-10-2026)
- Contexto: un hogar de N miembros come el mismo plato principal pero cada uno necesita una cantidad distinta y
  algún complemento propio; hay alergias por miembro y no todos comen siempre en casa. Un único MILP con
  N miembros × 7 días × 4 comidas × 1.057 recetas × catálogo no cabe en 60 s.
- Decisión:
  1. **Datos**: `Hogar` = miembros (seudónimo, sexo, edad, peso, talla, actividad, perfil, alergias UE-14,
     intolerancias, gustos vetados) + asistencia (día × comida → miembros presentes) + preferencias (ADR-0007).
     Nunca se persisten en el repo; entran por la app (sesión) o por JSON.
  2. **Estructura de comidas** (por defecto, configurable): desayuno y merienda = solo complementos individuales del
     catálogo; comida = 1 plato principal compartido + guarnición/ensalada compartida opcional; cena = 1 plato
     principal compartido. Las recetas `salsa_base`, `bebida` y `aperitivo` no se eligen como plato.
  3. **Etapa 1 · platos (MILP pequeño, compartido)**: binaria z[día, comida, receta] sobre las candidatas
     preseleccionadas (top-K por comida según preferencia, ver 5). Restricciones: 1 principal por comida con
     alguien presente; ninguna receta con alérgenos de algún presente (dura); frecuencias semanales del hogar
     (legumbre ≥ 4, pescado ≥ 3, carne ≤ 3, huevo ≤ 4 si todos los perfiles lo piden); sin repetir receta salvo
     batch; nevera/congelable para lunes-viernes. Objetivo: preferencias ponderadas + ajuste de proteína/energía
     del plato a la necesidad media de los presentes.
  4. **Etapa 2 · raciones (un MILP por miembro, platos fijos)**: multiplicador k ∈ [0,5; 2,0] (configurable) de
     la ración de adulto de cada plato compartido + complementos del catálogo (pan, fruta, lácteo, frutos secos,
     proteína; binaria + gramos como hoy) filtrados por sus alergias. Objetivos blandos de su perfil como en el
     generador actual; energía ±10 % del objetivo. Es el generador v0.1 con platos fijos como «alimentos» extra:
     se reutiliza su código.
  5. **Preselección**: por comida, las K = 40 recetas con mejor preferencia (valoración, temporada, tiempo) que no
     violen alergias de nadie del hogar; el resto no entra al MILP. Documentar K y tiempos en el benchmark (T26).
  6. Determinismo: semilla fija; en etapa 1 se desempata por id de receta; tests con instancias que llegan al
     óptimo (no cortadas por tiempo).
- Alternativas descartadas: MILP único (mejor en teoría; estimación para 5 × 7 × 4 con K = 40 y ≈ 45 complementos
  elegibles por comida: ≈ 16.000 variables, ≈ 6.500 binarias, cuando el generador actual ya tarda ≈ 28 s con
  del orden de 10³ binarias para una persona; se medirá en T26 y, si cabe en 60 s, se puede revisar esta decisión); un menú por persona sin compartir (no es un menú familiar); productos binaria×continua sin
  linealizar (no lineal).
- Consecuencias: el plato elegido en la etapa 1 puede obligar a un miembro a compensar con complementos; si alguno
  queda fuera de ±10 %, se informa y se reintenta la etapa 1 una vez penalizando ese plato. El generador UAX
  (una persona, alimentos sueltos) no cambia: el modo hogar es un módulo nuevo (`hogar.py`).
- Medición (T26, 30-10-2026, `scripts/benchmark_hogar.py`): hogar sintético de 5 (2 mantenimiento, 1 control con
  alergia, 1 volumen, 1 adolescente), 7 días × 4 comidas, biblioteca real (979 recetas calculables), K = 40:
  **34 s** de mediana en el sandbox de Cowork (Python 3.10; pendiente de medir en omarchy); peor desvío de energía
  4 %. Se mantiene la decisión de dos etapas; si omarchy supera 60 s, bajar K o `tiempo_etapa2`.

