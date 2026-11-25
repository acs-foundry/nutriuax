# NutriUAX

**Open-source clinical nutrition engine, BCAA & renal MILP diet optimizer, dietary survey analyzer, food exchange & drug-nutrient interaction platform, and Anything-Craft compatible CLI/MCP server.**

[![License: MIT](https://img.shields.io/badge/License-MIT-0F6B5E.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-164E63.svg)](pyproject.toml)
[![100% Local](https://img.shields.io/badge/Privacy-100%25%20Local%20Offline-0F6B5E.svg)](#privacy--clinical-disclaimer)

NutriUAX runs **100 % locally** with zero cloud telemetry, zero patient data leaving the machine, and open CC0 food composition data (**USDA FoodData Central SR Legacy**, ~7,800 foods with 18 amino acids).

---

## Why NutriUAX? Comparison vs Commercial & Open-Source Alternatives

| Capability | **NutriUAX v1.0 (MIT)** | EasyDiet (Commercial) | DietoPro (Commercial) | Nutrium (Commercial) | Cronometer (Freemium) | Wger (AGPL) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **License & Privacy** | **MIT · 100% offline local** | Proprietary SaaS | Proprietary SaaS | Proprietary SaaS | Cloud Freemium | AGPL-3.0 |
| **MILP Diet Optimizer (HiGHS)** | **Yes (exact math optimization)** | Manual / templates | Manual / templates | Manual / AI draft | No | No |
| **BCAA Control (Leu/Ile/Val mg/kg & LBM)** | **Yes (hard/soft solver + Leu trigger)** | No | No | No | Tracking only | No |
| **WHO 2007 AAS & Limiting Amino Acid** | **Yes** | No | No | No | Partial | No |
| **CKD / Renal Control (Na, K, P, PRAL, Double-boil)** | **Yes (KDOQI 2020 + PRAL)** | Partial | Partial | Partial | Tracking only | No |
| **Spanish Food Exchange System** | **Yes (automatic + patient guide)** | Yes (flagship) | Yes | Partial | No | No |
| **Drug–Nutrient Vademecum** | **Yes (24 clinical drugs/classes)** | No | Yes | No | No | No |
| **Dietary Surveys (3-day, FFQ, MEDAS-14, Maroni 24h)** | **Yes** | Partial | Partial | Partial | Diary only | No |
| **Anthropometry, 5 TMB/EER & MUST / MNA-SF** | **Yes** | Yes | Yes | Yes | Basic | Basic |
| **Multi-Member Household Shared-Dish Solver** | **Yes (UE-14 allergens + batch)** | No | No | No | No | No |
| **Raw ↔ Cooked Yield & Retention** | **Yes (USDA RF6 + Bognár 2002)** | Yes | Yes | Partial | Partial | No |
| **Headless CLI + JSON Schema + MCP Server** | **Yes (`anything-craft` / `craft_box`)** | No | No | No | No | REST only |
| **Office Dossier Export (XLSX, HTML, MD, DOCX/PDF)** | **Yes (+ optional `wordcraft-cli`)** | PDF | PDF | PDF / App | CSV | No |

---

## Key Features

- **MILP Diet Generator (`PuLP` + `HiGHS`)**: Optimizes 1–7 day menus with soft/hard constraints on energy, protein (g/kg and %), fat, saturated fat, carbohydrates, fiber, **Leucine / Isoleucine / Valine** (mg/kg body weight or DXA/BIA lean body mass), sodium, potassium, phosphorus, meal templates, and weekly food frequencies.
- **9 Auditable TOML Profiles**: Clinical (`uax_mediterranea`, `uax_hiperproteica`, `erc_nd`, `erc_hd`, `bcaa_intervencion`) and household (`mantenimiento`, `control`, `volumen`, `crecimiento_adolescente`) with enforced clinical safety floors (`seguridad.py`).
- **Raw ↔ Cooked Yields & Renal Double-Boiling**: Translates raw shopping weights to cooked plate portions (`data/coccion.csv`, USDA RF6 & Bognár 2002) without double-converting already-cooked USDA entries, including CKD potassium leaching (`doble_coccion_erc`).
- **Spanish Food Exchange System (`intercambios.py`)**: Automatic daily/meal exchange breakdown and printable 1-exchange gram equivalents guide for patient autonomy.
- **24-Drug Clinical Interaction Vademecum (`farmacos.py`)**: Checks anticoagulants (vitamin K), levothyroxine, ACEi/ARB, spironolactone, diuretics, statins, levodopa (LNAA competition), metformin, bisphosphonates, phosphate binders, corticosteroids, lithium, MAOIs, GLP-1, SGLT2, and more directly against the generated menu.
- **Clinical Anthropometry & Screening (`clinica.py`)**: WHO BMI, WHtR/WHR, Devine IBW, Adjusted BW, Boer LBM, **5 TMB/EER equations** (Mifflin-St Jeor, Harris-Benedict 1984, Owen, Cunningham, IOM 2005 EER), **MUST** & **MNA-SF** screening, **PRAL** renal acid load (Remer & Manz 1995), and **WHO 2007 AAS** + per-meal Leucine anabolic trigger (`>= 2.5 g`).
- **Dietary Surveys & Adherence (`encuestas.py`)**: N-day food diary, 9-category PREDIMED-Plus FFQ, **MEDAS-14** score, **Maroni (1985)** 24 h urinary urea nitrogen protein estimation, and combined adherence classification (`config/adherencia.toml`).
- **Multi-Member Household Planner (`hogar.py` + `data/recetas_base.json`)**: 33 built-in MIT Spanish/Mediterranean recipes, shared main dishes with per-member portion scaling `k`, hard EU-14 allergen exclusion, seasonal weights, and batch cooking.
- **Anything-Craft Compatible CLI & Hardened MCP Server**: Standalone CLI (`nutriuax-cli`) and JSON-RPC 2.0 STDIO MCP server (`nutriuax-cli mcp`) with `--automation-read-root` / `--automation-write-root` symlink-safe sandboxing and 8 MiB line limits — ready for AI agents and `craft_box.py`, with optional ArtCraft Office bridge (`wordcraft-cli`) for `.docx`/`.pdf` dossiers.

---

## Installation

```bash
git clone https://github.com/acs-foundry/nutriuax.git
cd nutriuax
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Verify installation:

```bash
nutriuax-cli doctor
```

---

## Quick Start

### 1. Studio GUI (Local Streamlit App)

```bash
# Clinical / study mode
nutriuax --modo estudio

# Dietitian consultation mode (all profiles, neutral header)
nutriuax --modo consulta

# Family household meal planner mode
nutriuax --modo hogar
```

### 2. Anything-Craft CLI (`nutriuax-cli`)

```bash
# Inspect all 12 symmetrical CLI/MCP commands
nutriuax-cli commands
nutriuax-cli describe diet.generate

# Headless command execution (`id={json}`)
nutriuax-cli run --cmd 'clinical.anthropometry={"sexo":"H","edad":45,"peso":82,"talla":178,"cintura_cm":94}'
nutriuax-cli run --cmd 'drugs.check={"medicamentos":["ieca_ara2","levodopa"],"resumen_diario":{"potasio":3400,"proteina_gkg":1.3}}'

# Ergonomic clinical subcommands
nutriuax-cli buscar "garbanzos cocidos"
nutriuax-cli dieta --perfil erc_nd --peso 72 --dias 3 --farmaco ieca_ara2 --farmaco quelantes_fosforo
nutriuax-cli intercambios --grupo cereales_legumbres
nutriuax-cli exportar --perfil uax_mediterranea --dias 3 --salida-dir ./dossier_out

# Household JSON v1 menu (uses built-in 33 MIT recipes by default)
nutriuax-cli menu --entrada docs/ejemplos/entrada_hogar_sintetico.json --salida menu.json
```

### 3. Hardened MCP Server (STDIO JSON-RPC 2.0)

Compatible with Claude Desktop, Cursor, Antigravity, and `craft_box.py`:

```bash
nutriuax-cli mcp \
  --automation-read-root /path/to/workspace \
  --automation-write-root /path/to/output
```

Exposes 12 sandboxed MCP tools: `nutriuax_doctor`, `nutriuax_profiles_list`, `nutriuax_foods_search`, `nutriuax_clinical_anthropometry`, `nutriuax_diet_generate`, `nutriuax_household_generate`, `nutriuax_exchanges_guide`, `nutriuax_drugs_check`, `nutriuax_survey_diary`, `nutriuax_survey_ffq`, `nutriuax_survey_adherence`, and `nutriuax_report_export`.

---

## Running Tests

```bash
pytest -q
```

Includes unit tests, clinical regression lock (`tests/test_regresion_uax.py`), household safety floors, cooking yield validation, survey & adherence tests, exchange/drug/clinical index tests, and MCP sandbox/security tests.

---

## Privacy & Clinical Disclaimer

- **Privacy**: NutriUAX performs zero external network calls at runtime. Local household profiles saved in `hogar` mode are stored exclusively outside the repository in `~/.config/nutriuax/hogares/` with `0600` permissions. Always use pseudonymized participant codes (`P001`), never real names.
- **Clinical Disclaimer**: NutriUAX is an open-source research and clinical decision-support tool. Generated menus, nutrient estimates, and drug-nutrient alerts must always be reviewed and adapted by a qualified dietitian or physician before clinical prescription.

## Licenses & Data Attribution

- **Source code, recipes (`data/recetas_base.json`), and SVG assets**: [MIT License](LICENSE).
- **Food composition data (`data/composicion_fdc.csv`, `data/fdc_completa.csv.gz`)**: U.S. Department of Agriculture, Agricultural Research Service — FoodData Central SR Legacy (**CC0 1.0 Public Domain**).
- **Optimization solver**: HiGHS (MIT) via PuLP (MIT).
