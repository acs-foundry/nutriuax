# SPEC · NutriUAX (v1.0)

## Problema
Ningún software libre calcula aminoácidos ramificados (Leu/Ile/Val) y esenciales con base abierta exportable, ni genera dietas optimizadas por programación lineal con dosis objetivo de BCAA, control renal (ERC), sistema español de intercambios, interacciones fármaco-nutriente, encuestas dietéticas y automatización headless CLI/MCP.

## Módulos Implementados (v1.0)
1. **Generador de dietas clínico (MILP PuLP + HiGHS)** (`generador.py`, `objetivos.py`, `perfiles.py`):
   - 9 perfiles en TOML (`uax_mediterranea`, `uax_hiperproteica`, `erc_nd`, `erc_hd`, `bcaa_intervencion`, `mantenimiento`, `control`, `volumen`, `crecimiento_adolescente`), suelos clínicos de seguridad (`seguridad.py`) y regresión exacta (`tests/test_regresion_uax.py`).
2. **Generador familiar multi-miembro** (`hogar.py`, `recetas.py`, `equivalencias.py`, `api.py`):
   - Platos compartidos + ración óptima `k` y complementos por miembro, alérgenos UE-14 duros, biblioteca MIT integrada de 33 recetas mediterráneas (`data/recetas_base.json`), batch cooking y temporalidad.
3. **Cocción crudo ↔ cocinado y retención** (`coccion.py`, `data/coccion.csv`):
   - Factores USDA RF6 / Bognár 2002, detección automática de estado en FDC y doble cocción ERC para reducción de potasio.
4. **Encuestas y adherencia clínica** (`encuestas.py`, `config/adherencia.toml`):
   - Registro dietético de N días (3 días estándar), FFQ PREDIMED-Plus (9 categorías), MEDAS-14, fórmula de Maroni (NUU 24 h) y clasificación combinada de adherencia.
5. **Clínica avanzada, intercambios y fármacos** (`intercambios.py`, `farmacos.py`, `clinica.py`):
   - Sistema español de intercambios (tipo EasyDiet), vademécum de 24 fármacos/clases (tipo DietoPro), antropometría + 5 ecuaciones TMB/EER, cribado MUST / MNA-SF, PRAL renal y calidad proteica WHO 2007 AAS + umbral anabólico de leucina por toma.
6. **Ecosistema Anything-Craft y Dossiers** (`cli.py`, `commands.py`, `mcp.py`, `sandbox.py`, `office.py`):
   - CLI `nutriuax-cli` (`doctor`, `commands`, `describe`, `run --cmd`, `mcp`, `menu`, `dieta`, `buscar`, `antropometria`, `intercambios`, `farmacos`, `encuesta`, `adherencia`, `exportar`), servidor MCP JSON-RPC 2.0 STDIO con aislamiento de rutas (`--automation-read-root` / `--automation-write-root`) y puente opcional a `wordcraft-cli` / `deckcraft-cli`.
