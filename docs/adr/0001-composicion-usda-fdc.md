# ADR-0001 · Composición de alimentos: USDA FoodData Central SR Legacy

- Estado: aceptado (2026-10-30)

## Contexto
Hace falta Leu/Ile/Val y resto de aminoácidos indispensables por alimento con licencia que permita
redistribuir la tabla en el repo. BEDCA y las tablas de Moreiras no tienen aminoácidos completos ni
licencia abierta clara; Odimet y DIAL no exportan o no son libres.

## Decisión
USDA FoodData Central, conjunto SR Legacy (CC0, con perfil de aminoácidos en la mayoría de alimentos),
descargado una vez e importado con `nutriuax.importar_fdc` mediante un mapeo versionado alimento español
→ código NDB (`data/alimentos.csv`). Frida (DTU) como respaldo para alimentos sin equivalente.
Mientras no se importe, una tabla semilla con aminoácidos estimados por patrón permite desarrollar;
la app y el Excel lo señalan.

## Consecuencias
- Alimentos típicamente españoles (jamón curado, queso manchego, merluza) se aproximan con el
  equivalente FDC más cercano: revisión por dietista en `revision_fdc.csv`.
- La validación frente a Odimet (< 10 % en Leu/Ile/Val, 20 registros) sigue siendo el criterio de éxito.
- La descarga del ZIP oficial de USDA se realiza en local y se importa con `python -m nutriuax.importar_fdc`.
