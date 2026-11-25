# ADR-0002 · Generador de dietas: motor propio con programación lineal entera (PuLP + HiGHS)

- Estado: aceptado (2026-10-30)

## Contexto
Se requiere una herramienta clínica abierta tipo EasyDiet para investigación nutricional, pacientes con ERC y
protocolos de intervención con dosis de BCAA. Ninguna herramienta libre revisada genera menús con restricciones de
aminoácidos: wger (AGPL-3.0, Django) tiene planes de nutrición pero ni aminoácidos ni optimización y
obligaría a publicar los cambios bajo AGPL; Tandoor/Mealie son gestores de recetas.

## Decisión
- Modelo MILP semanal: gramos continuos + elección binaria por alimento/comida/día; estructura de
  plato por plantillas (grupos de roles con mín./máx.), raciones mín./máx. y preferencia por la ración
  habitual, veces por semana y frecuencias por etiqueta (pescado, legumbre, carne roja…).
- Objetivos nutricionales como restricciones **blandas** con holgura penalizada (siempre hay menú y la
  app muestra qué queda fuera de rango); margen interno de 1,5 % para absorber el redondeo a 5 g.
- Solver HiGHS (MIT) vía PuLP (MIT), límite 25 s y gap 2 %. Variedad con coste aleatorio sembrado.
- Interfaz Streamlit local (Apache-2.0): sin servidor externo ni datos fuera del equipo.

## Consecuencias
- Añadir un criterio nuevo (p. ej. MEDAS-14 completo, líquidos en HD) = una restricción más.
- Las plantillas de plato son genéricas (no recetas); recetas compuestas quedan para una versión futura.
- Objetivos contradictorios (2,2 g/kg y > 30 % kcal con > 2200 kcal) se detectan y se avisa.
