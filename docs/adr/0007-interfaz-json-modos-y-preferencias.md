# 0007 · Interfaz para otros programas (JSON versionado + CLI), modos de uso y preferencias

- Fecha: 2026-10-30 · Estado: aceptada
- Contexto: aplicaciones externas y flujos de automatización necesitan consumir NutriUAX como librería/CLI/MCP; la app debe separar el modo clínico del modo familiar y reflejar las preferencias del hogar.
- Decisión:
  1. **Función pública** `nutriuax.api.generar_menu(entrada: dict) -> dict` y **CLI**
     `python -m nutriuax menu --entrada hogar.json --salida menu.json [--recetas RUTA]`. Mismo código.
  2. **Esquema JSON versionado** (`schema/entrada_v1.json`, `schema/salida_v1.json`, JSON Schema 2020-12) con
     `"version": "1"`. Entrada: modo, hogar (miembros, asistencia), perfiles (clave o perfil completo), semana
     (fecha de inicio, días, comidas), preferencias, ruta de recetas opcional. Salida: menú por día y comida con
     receta y ración por miembro, complementos por miembro, nutrientes por persona y día frente a objetivos,
     lista de la compra agregada (por sección `s` de la biblioteca), avisos (suelos, alergias, ±10 %).
     Cambios incompatibles → `version` 2 y esquema nuevo; los tests de contrato validan ejemplos de entrada y de
     salida contra el esquema. Validación con `jsonschema` (única dependencia nueva, MIT) o validador mínimo propio
     si se prefiere no añadirla.
  3. **Modos**: `estudio` (marca UAX, textos clínicos, perfiles de `ambito` estudio/clínico), `consulta` (interfaz
     neutra, textos clínicos, todos los perfiles), `hogar` (interfaz neutra, sin textos clínicos, solo perfiles de
     `ambito = hogar`, suelos de seguridad siempre activos). En la app, `NUTRIUAX_MODO` o `config/app.toml`.
     `estilo.py` se aplica solo en `estudio`; `consulta` y `hogar` usan un tema neutro.
  4. **Preferencias como pesos** (`[preferencias]` en la entrada, con valores por defecto documentados):
     valoraciones 1-5 por receta (las da el llamador; la biblioteca no las trae; ≤ 2 → penalización alta, casi
     nunca), batch del domingo (de lunes a viernes, platos con `nevera` ≥ días hasta su consumo o `congelable`),
     variedad (penaliza repetir receta y categoría), temporada (tabla `data/temporada.csv` de frutas y verduras
     por mes; peso 0 hasta que exista) y tiempo de cocina (`minutos` frente a un máximo por día laborable).
- Alternativas descartadas: API HTTP acoplada a un único cliente; varias apps separadas (duplicaría código).
- Consecuencias: el contrato JSON es la frontera pública estable; cambiarlo exige subir versión. Los datos de
  los miembros solo viven en memoria durante la llamada.
- Nota de implementación (T27, 30-10-2026): los esquemas usan **JSON Schema draft-07** (no 2020-12) para
  funcionar con `jsonschema` ≥ 3.2; se valida tanto la entrada como la salida. Ejemplo sintético en
  `docs/ejemplos/entrada_hogar_sintetico.json`. Los modos limitan los perfiles: hogar → solo `ambito = hogar`;
  consulta → todos; estudio → estudio y clínicos. Los suelos de seguridad se aplican en todos los modos del API.

