# 0004 · Perfiles dietéticos como datos (TOML con herencia y suelos de seguridad)

- Fecha: 2026-10-30 · Estado: aceptada (SM, 30-10-2026)
- Contexto: los 5 perfiles clínicos (UAX mediterránea e hiperproteica, ERC-ND, ERC-HD, intervención BCAA) están
  escritos en `objetivos.py`. Para uso doméstico, consulta de dietista y nuevos estudios hacen falta más perfiles,
  editables sin tocar código, y unos límites de seguridad que no dependan de quien edite el perfil.
- Decisión:
  1. Un fichero por perfil en `config/perfiles/<clave>.toml`. Campos = los de `Perfil` actual + `fuentes` (lista,
     obligatoria), `parte_de` (clave de otro perfil: hereda y sobrescribe campo a campo; los diccionarios
     `semanal_min/max` y `aa_*` se fusionan), `ambito` (`estudio` | `clinico` | `hogar`), `edad` (rango) y
     `energia` (`modo = "mifflin" | "kcal_por_kg" | "eer_iom_2005"`, `ajuste_pct = [min, max]`).
  2. Cargador con validación estricta: campo desconocido, rango invertido, `parte_de` inexistente o ciclo,
     perfil sin fuentes → error con el nombre del fichero. `objetivos.PERFILES` se construye desde los TOML;
     la API de Python (`Perfil`, `calcular_objetivos`) no cambia.
  3. **Suelos de seguridad en código, no en TOML** (`seguridad.py`), aplicados después de leer el perfil y de los
     ajustes de la app/CLI, y no desactivables en modo hogar: energía ≥ gasto basal (Mifflin), déficit ≤ 20 % del
     gasto total, proteína ≥ 1,2 g/kg en perfiles con déficit, < 18 años → nunca déficit ni perfil de control.
     Si una petición los viola, se recorta al suelo y se devuelve un aviso visible (app) o en `avisos[]` (JSON).
  4. Perfiles domésticos nuevos (`ambito = "hogar"`): `mantenimiento` (AESAN 2022: legumbre ≥ 4/sem,
     pescado ≥ 3, carne ≤ 3, huevo ≤ 4), `control` (parte de mantenimiento; −10 a −20 %, proteína 1,2-1,6 g/kg),
     `volumen` (parte de mantenimiento; +5 a +15 %, proteína 1,6-2,2 g/kg), `crecimiento_adolescente`
     (12-18 años; energía EER IOM 2005 con crecimiento, sin ajuste negativo).
  5. Energía de menores de 18 años: ecuaciones EER del IOM (2005), que incluyen el coste de crecimiento; Mifflin
     no está validada en adolescentes.
- Alternativas descartadas: YAML (dependencia extra; `tomllib` va en la biblioteca estándar); JSON (sin
  comentarios para las fuentes); suelos dentro del TOML (cualquiera podría editarlos).
- Consecuencias: los 5 perfiles clínicos deben quedar **idénticos** (test de instantánea campo a campo y menú
  UAX de referencia, T19). Añadir un perfil = añadir un fichero. Revertir: volver a leer el diccionario en código.
- Fuentes: AESAN (2022) *Recomendaciones dietéticas saludables y sostenibles complementadas con recomendaciones de
  actividad física para la población española*; IOM (2005) *Dietary Reference Intakes for Energy…* (EER);
  Mifflin MD et al. (1990) *Am J Clin Nutr* 51:241-7; ISSN position stand protein and exercise (Jäger 2017,
  *JISSN* 14:20) para 1,6-2,2 g/kg; Helms ER et al. (2014) *JISSN* 11:20 para déficit con proteína alta.
