"""T14 · propuesta de catálogo curado (≈ 200 alimentos) para que la revise la dietista.

Uso: python scripts/proponer_catalogo.py .   → REPO/data/catalogo_propuesto.csv y REPO/data/catalogo_revision.csv
Los alimentos actuales (alimentos.csv) se conservan; se añaden los nuevos con su NDB elegido en la base
FDC completa y macros/minerales tomados de FDC. `estado_ref` dice si el código FDC es crudo, cocinado o
tal cual (se consume sin cocinar): lo usará T16 para convertir crudo ↔ cocinado.
"""
import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(sys.argv[1])
sys.path.insert(0, str(REPO / "src"))
from nutriuax import base_fdc as b  # noqa: E402

P = {  # plantilla: grupo, rol, origen, patron_aa, comidas, min_g, max_g, porcion_g, max_semana, etiquetas
    "lac": ("lacteos", "lacteo", "animal", "lacteo", "D;MM;M;X", 100, 250, 125, 14, "lacteo"),
    "queso": ("lacteos", "lacteo", "animal", "lacteo", "D;M;X", 20, 80, 40, 5, "lacteo"),
    "huevo": ("huevos", "proteina", "animal", "huevo", "D;C;X", 50, 150, 60, 7, "huevo"),
    "carne_b": ("carnes", "proteina", "animal", "carne", "C;X", 80, 220, 120, 3, "carne_blanca"),
    "carne_r": ("carnes", "proteina", "animal", "carne", "C;X", 80, 200, 120, 2, "carne_roja"),
    "embutido": ("carnes", "proteina", "animal", "carne", "D;MM;M", 15, 50, 30, 2, "carne_roja;procesada;alto_sodio"),
    "pesc": ("pescados", "proteina", "animal", "pescado", "C;X", 100, 250, 150, 2, "pescado"),
    "azul": ("pescados", "proteina", "animal", "pescado", "C;X", 100, 220, 130, 2, "pescado;pescado_azul"),
    "marisco": ("pescados", "proteina", "animal", "pescado", "C;X", 80, 200, 120, 2, "pescado;marisco"),
    "leg": ("legumbres", "legumbre", "vegetal", "legumbre", "C;X", 120, 300, 200, 3, "legumbre"),
    "soja": ("legumbres", "proteina", "vegetal", "soja", "C;X", 80, 200, 120, 3, "legumbre;soja"),
    "cer": ("cereales", "cereal", "vegetal", "trigo", "C;X", 100, 300, 180, 4, "cereal"),
    "cer_d": ("cereales", "cereal", "vegetal", "trigo", "D;MM;M", 20, 80, 40, 7, "cereal"),
    "pan": ("cereales", "cereal", "vegetal", "trigo", "D;MM;C;M;X", 30, 120, 60, 14, "cereal;pan"),
    "tub": ("tuberculos", "cereal", "vegetal", "patata", "C;X", 100, 300, 200, 4, "tuberculo"),
    "verd": ("verduras", "verdura", "vegetal", "verdura", "C;X", 100, 250, 150, 3, "verdura"),
    "ensal": ("verduras", "verdura", "vegetal", "verdura", "C;X", 30, 150, 80, 14, "verdura"),
    "fruta": ("frutas", "fruta", "vegetal", "fruta", "D;MM;C;M;X", 100, 250, 150, 5, "fruta"),
    "f_seca": ("frutas", "fruta", "vegetal", "fruta", "D;MM;M", 15, 50, 30, 3, "fruta;azucar"),
    "fsecos": ("frutos_secos", "frutos_secos", "vegetal", "frutos_secos", "D;MM;M", 15, 40, 30, 7, "frutos_secos"),
    "grasa": ("grasas", "grasa", "vegetal", "ninguno", "D;C;X", 5, 30, 10, 7, ""),
    "dulce": ("azucares", "dulce", "vegetal", "trigo", "D;MM;M", 20, 80, 40, 2, "azucar"),
    "dulce_l": ("azucares", "dulce", "animal", "lacteo", "MM;M;C;X", 80, 150, 125, 2, "azucar;lacteo"),
    "supl": ("suplementos", "suplemento", "vegetal", "soja", "D;MM;M", 20, 40, 30, 14, "suplemento"),
}

# plantilla, id, nombre, consulta (inglés) o NDB, estado_ref, etiquetas extra, cambios
N = [
    # lácteos
    ("lac", "leche_desnatada", "Leche desnatada", "01085", "tal_cual", "", {}),
    ("lac", "yogur_desnatado", "Yogur natural desnatado", "01118", "tal_cual", "", {}),
    ("lac", "kefir", "Kéfir natural", "kefir plain", "tal_cual", "", {}),
    ("lac", "bebida_soja", "Bebida de soja", "soymilk original unfortified", "tal_cual", "soja",
     dict(origen="vegetal", patron_aa="soja")),
    ("lac", "batido_cacao", "Batido de cacao (leche con cacao)", "01104", "tal_cual", "azucar", dict(max_semana=3)),
    ("queso", "queso_semicurado", "Queso semicurado (tipo cheddar)", "01009", "tal_cual", "alto_sodio", {}),
    ("queso", "queso_mozzarella", "Queso mozzarella", "01026", "tal_cual", "", {}),
    ("queso", "queso_parmesano", "Queso parmesano", "01033", "tal_cual", "alto_sodio", dict(min_g=5, max_g=30, porcion_g=15)),
    ("queso", "queso_cabra", "Queso de cabra", "cheese goat semisoft", "tal_cual", "", {}),
    ("queso", "queso_untar", "Queso para untar", "cheese cream", "tal_cual", "", dict(min_g=15, max_g=40, porcion_g=25)),
    # huevos
    ("huevo", "huevo_frito", "Huevo frito", "01128", "cocinado", "", {}),
    ("huevo", "tortilla_francesa", "Tortilla francesa", "01130", "cocinado", "", {}),
    ("huevo", "huevo_poche", "Huevo escalfado", "01131", "cocinado", "", {}),
    # carnes blancas
    ("carne_b", "pollo_muslo", "Muslo de pollo asado (sin piel)", "chicken broilers thigh meat only cooked roasted", "cocinado", "", {}),
    ("carne_b", "pollo_asado", "Pollo asado (carne, sin piel)", "chicken broilers meat only cooked roasted", "cocinado", "", {}),
    ("carne_b", "pavo_muslo", "Muslo de pavo asado", "turkey dark meat cooked roasted", "cocinado", "", {}),
    ("carne_b", "pato", "Pato asado (sin piel)", "duck domesticated meat only cooked roasted", "cocinado", "", dict(max_semana=1)),
    ("carne_b", "conejo_asado", "Conejo asado", "rabbit domesticated composite cooked roasted", "cocinado", "", {}),
    # carnes rojas
    ("carne_r", "ternera_filete", "Filete de ternera a la plancha", "beef top sirloin steak lean cooked broiled", "cocinado", "", {}),
    ("carne_r", "ternera_picada", "Carne picada de ternera (cocinada)", "beef ground 90% lean cooked pan-browned", "cocinado", "", {}),
    ("carne_r", "hamburguesa_ternera", "Hamburguesa de ternera a la plancha", "beef ground 85% lean patty cooked broiled", "cocinado", "procesada", {}),
    ("carne_r", "solomillo_cerdo", "Solomillo de cerdo asado", "pork fresh loin tenderloin lean cooked roasted", "cocinado", "", {}),
    ("carne_r", "chuleta_cerdo", "Chuleta de cerdo a la plancha", "pork fresh loin chops lean cooked broiled", "cocinado", "", {}),
    ("carne_r", "cordero_pierna", "Pierna de cordero asada", "lamb leg whole lean cooked roasted", "cocinado", "", {}),
    ("carne_r", "higado_ternera", "Hígado de ternera a la plancha", "beef variety meats liver cooked pan-fried", "cocinado", "", dict(max_semana=1)),
    ("carne_r", "ternera_guisada", "Ternera para guisar (cocinada)", "beef chuck lean cooked braised", "cocinado", "", {}),
    # embutidos y fiambres
    ("embutido", "jamon_cocido", "Jamón cocido (york)", "07029", "tal_cual", "", {}),
    ("embutido", "pavo_fiambre", "Fiambre de pechuga de pavo", "07046", "tal_cual", "", dict(etiquetas="carne_blanca;procesada;alto_sodio")),
    ("embutido", "chorizo", "Chorizo", "pepperoni beef and pork sliced", "tal_cual", "", {}),
    ("embutido", "salchichon", "Salchichón / salami", "salami dry or hard pork", "tal_cual", "", {}),
    ("embutido", "lomo_embuchado", "Lomo embuchado", "canadian bacon", "tal_cual", "", {}),
    ("embutido", "mortadela", "Mortadela", "bologna pork", "tal_cual", "", {}),
    ("embutido", "salchicha", "Salchicha tipo Frankfurt", "frankfurter pork", "tal_cual", "", dict(comidas="C;X", min_g=40, max_g=120, porcion_g=80)),
    ("embutido", "bacon", "Bacon / panceta (frito)", "10860", "cocinado", "", dict(max_g=40, porcion_g=20)),
    ("embutido", "morcilla", "Morcilla", "blood sausage", "tal_cual", "", dict(comidas="C;X")),
    # pescados blancos
    ("pesc", "lubina", "Lubina al horno", "fish sea bass mixed species cooked dry heat", "cocinado", "", {}),
    ("pesc", "dorada", "Dorada al horno", "fish scup cooked dry heat|fish porgy", "cocinado", "", {}),
    ("pesc", "lenguado", "Lenguado a la plancha", "fish flatfish flounder sole cooked dry heat", "cocinado", "", {}),
    ("pesc", "rape", "Rape", "fish monkfish cooked dry heat", "cocinado", "", {}),
    ("pesc", "mero", "Mero", "fish grouper mixed species cooked dry heat", "cocinado", "", {}),
    ("pesc", "abadejo", "Abadejo / eglefino", "15034", "cocinado", "", {}),
    ("pesc", "bacalao_salado", "Bacalao desalado", "fish cod atlantic dried and salted", "tal_cual", "alto_sodio", dict(max_semana=1)),
    # pescados azules
    ("azul", "caballa", "Caballa", "fish mackerel atlantic cooked dry heat", "cocinado", "", {}),
    ("azul", "trucha", "Trucha", "fish trout rainbow farmed cooked dry heat", "cocinado", "", {}),
    ("azul", "boqueron", "Boquerones", "fish anchovy european raw", "crudo", "", {}),
    ("azul", "anchoas_lata", "Anchoas en aceite (lata)", "fish anchovy european canned in oil", "tal_cual", "alto_sodio",
     dict(min_g=10, max_g=30, porcion_g=15, comidas="MM;M;C;X")),
    ("azul", "atun_fresco", "Atún fresco a la plancha", "fish tuna fresh yellowfin cooked dry heat", "cocinado", "", {}),
    ("azul", "bonito", "Bonito del norte", "fish tuna skipjack fresh cooked dry heat", "cocinado", "", {}),
    ("azul", "pez_espada", "Pez espada / emperador", "fish swordfish cooked dry heat", "cocinado", "", dict(max_semana=1)),
    ("azul", "salmon_ahumado", "Salmón ahumado", "fish salmon chinook smoked", "tal_cual", "alto_sodio",
     dict(min_g=30, max_g=80, porcion_g=50, comidas="D;MM;C;X")),
    ("azul", "atun_aceite", "Atún en aceite (lata, escurrido)", "15124", "tal_cual", "", dict(min_g=50, max_g=120, porcion_g=80, comidas="C;X;M")),
    # mariscos y cefalópodos
    ("marisco", "calamar", "Calamar", "mollusks squid mixed species raw", "crudo", "", {}),
    ("marisco", "pulpo", "Pulpo cocido", "mollusks octopus common cooked moist heat", "cocinado", "", {}),
    ("marisco", "sepia", "Sepia a la plancha", "mollusks cuttlefish mixed species cooked moist heat", "cocinado", "", {}),
    ("marisco", "almejas", "Almejas", "mollusks clam mixed species cooked moist heat", "cocinado", "", {}),
    ("marisco", "langostinos", "Langostinos cocidos", "crustaceans shrimp mixed species cooked moist heat", "cocinado", "", {}),
    ("marisco", "surimi", "Surimi (palitos de cangrejo)", "crustaceans crab imitation surimi", "tal_cual", "procesada", {}),
    # legumbres y soja
    ("leg", "alubia_roja", "Alubias rojas cocidas", "beans kidney red mature seeds cooked boiled without salt", "cocinado", "", {}),
    ("leg", "habas", "Habas cocidas", "broadbeans fava mature seeds cooked boiled without salt", "cocinado", "", {}),
    ("leg", "guisantes", "Guisantes cocidos", "peas green cooked boiled drained without salt", "cocinado", "", {}),
    ("leg", "lentejas_rojas", "Lentejas rojas cocidas", "lentils pink or red raw", "crudo", "", dict(min_g=40, max_g=100, porcion_g=60)),
    ("leg", "hummus", "Hummus", "hummus commercial", "tal_cual", "", dict(comidas="MM;M;C;X", min_g=30, max_g=100, porcion_g=50)),
    ("soja", "edamame", "Edamame", "edamame frozen prepared", "cocinado", "", {}),
    ("soja", "soja_cocida", "Soja en grano cocida", "soybeans mature seeds cooked boiled without salt", "cocinado", "", {}),
    ("soja", "tempeh", "Tempeh", "tempeh", "tal_cual", "", {}),
    ("soja", "soja_texturizada", "Soja texturizada (seca)", "soy protein concentrate", "crudo", "", dict(min_g=20, max_g=60, porcion_g=40)),
    # cereales
    ("cer", "fideos", "Fideos cocidos", "noodles egg cooked enriched", "cocinado", "", {}),
    ("cer", "arroz_basmati", "Arroz vaporizado cocido", "rice white long-grain parboiled enriched cooked", "cocinado", "", {}),
    ("cer", "bulgur", "Bulgur cocido", "bulgur cooked", "cocinado", "integral", {}),
    ("cer", "maiz_dulce", "Maíz dulce", "corn sweet yellow cooked boiled drained without salt", "cocinado", "", dict(min_g=50, max_g=150, porcion_g=80)),
    ("cer", "trigo_sarraceno", "Trigo sarraceno cocido", "buckwheat groats roasted cooked", "cocinado", "integral", dict(max_semana=2)),
    ("pan", "pan_molde", "Pan de molde blanco", "18069", "tal_cual", "", {}),
    ("pan", "pan_molde_integral", "Pan de molde integral", "18075", "tal_cual", "integral", {}),
    ("pan", "pan_centeno", "Pan de centeno", "bread rye", "tal_cual", "integral", {}),
    ("pan", "pan_tostado", "Pan tostado / biscotes", "toast melba plain", "tal_cual", "", dict(min_g=15, max_g=60, porcion_g=30)),
    ("pan", "tortitas_arroz", "Tortitas de arroz", "snacks rice cakes brown rice plain", "tal_cual", "",
     dict(patron_aa="arroz", min_g=10, max_g=40, porcion_g=20)),
    ("cer_d", "copos_maiz", "Copos de maíz", "cereals ready-to-eat corn flakes", "tal_cual", "", {}),
    ("cer_d", "muesli", "Granola / muesli casero", "08037", "tal_cual", "", dict(patron_aa="avena")),
    ("cer_d", "salvado_avena", "Salvado de avena", "oat bran raw", "crudo", "integral", dict(patron_aa="avena", min_g=10, max_g=40, porcion_g=20)),
    # tubérculos
    ("tub", "patata_asada", "Patata asada", "potatoes baked flesh without salt", "cocinado", "", {}),
    ("tub", "patatas_fritas", "Patatas fritas caseras", "potatoes french fried home-prepared", "cocinado", "", dict(max_semana=1, min_g=80, max_g=200, porcion_g=120)),
    ("tub", "pure_patata", "Puré de patata", "potatoes mashed home-prepared whole milk", "cocinado", "", {}),
    # verduras cocinadas
    ("verd", "acelgas", "Acelgas cocidas", "chard swiss cooked boiled drained without salt", "cocinado", "alto_potasio", {}),
    ("verd", "alcachofa", "Alcachofas cocidas", "artichokes globe cooked boiled drained without salt", "cocinado", "", {}),
    ("verd", "esparragos", "Espárragos trigueros", "asparagus cooked boiled drained", "cocinado", "", {}),
    ("verd", "puerro", "Puerro cocido", "leeks bulb and lower leaf-portion cooked boiled", "cocinado", "", {}),
    ("verd", "repollo", "Repollo / col cocida", "cabbage common cooked boiled drained without salt", "cocinado", "", {}),
    ("verd", "coles_bruselas", "Coles de Bruselas", "brussels sprouts cooked boiled drained without salt", "cocinado", "", {}),
    ("verd", "calabaza", "Calabaza asada", "pumpkin cooked boiled drained without salt", "cocinado", "", {}),
    ("verd", "remolacha", "Remolacha cocida", "beets cooked boiled drained", "cocinado", "", {}),
    ("verd", "pimiento_verde", "Pimiento verde", "peppers sweet green raw", "crudo", "", dict(min_g=50, max_g=200, porcion_g=100, max_semana=5)),
    ("verd", "setas", "Setas (champiñón, gírgola) salteadas", "mushrooms oyster raw", "crudo", "", {}),
    ("verd", "tomate_triturado", "Tomate triturado / frito casero", "tomatoes red ripe canned packed in tomato juice", "tal_cual", "",
     dict(min_g=30, max_g=150, porcion_g=60, max_semana=7)),
    ("verd", "nabo", "Nabo cocido", "turnips cooked boiled drained without salt", "cocinado", "", dict(max_semana=2)),
    ("verd", "verduras_menestra", "Menestra de verduras (congelada)", "vegetables mixed frozen cooked boiled drained without salt", "cocinado", "", {}),
    # verduras de ensalada
    ("ensal", "pepino", "Pepino", "cucumber with peel raw", "crudo", "", {}),
    ("ensal", "rucula", "Rúcula", "arugula raw", "crudo", "", dict(min_g=20, max_g=80, porcion_g=40)),
    ("ensal", "canonigos", "Canónigos / brotes tiernos", "lettuce green leaf raw", "crudo", "", dict(min_g=20, max_g=80, porcion_g=40)),
    ("ensal", "endibia", "Endibia", "chicory witloof raw", "crudo", "", {}),
    ("ensal", "lombarda", "Lombarda", "cabbage red raw", "crudo", "", {}),
    ("ensal", "apio", "Apio", "celery raw", "crudo", "", {}),
    ("ensal", "zanahoria_rallada", "Zanahoria rallada", "carrots raw", "crudo", "", {}),
    ("ensal", "ajo", "Ajo", "garlic raw", "crudo", "", dict(min_g=2, max_g=10, porcion_g=5)),
    ("ensal", "rabanos", "Rábanos", "radishes raw", "crudo", "", {}),
    # frutas
    ("fruta", "mandarina", "Mandarina", "tangerines mandarin oranges raw", "crudo", "", {}),
    ("fruta", "melon", "Melón", "melons honeydew raw", "crudo", "", dict(min_g=150, max_g=350, porcion_g=250)),
    ("fruta", "cerezas", "Cerezas", "cherries sweet raw", "crudo", "", {}),
    ("fruta", "albaricoque", "Albaricoques", "apricots raw", "crudo", "", {}),
    ("fruta", "ciruela", "Ciruelas", "plums raw", "crudo", "", {}),
    ("fruta", "nectarina", "Nectarina", "nectarines raw", "crudo", "", {}),
    ("fruta", "mango", "Mango", "mangos raw", "crudo", "", {}),
    ("fruta", "higos", "Higos frescos", "figs raw", "crudo", "", {}),
    ("fruta", "granada", "Granada", "pomegranates raw", "crudo", "", {}),
    ("fruta", "arandanos", "Arándanos", "blueberries raw", "crudo", "", dict(min_g=50, max_g=150, porcion_g=80)),
    ("fruta", "frambuesas", "Frambuesas", "raspberries raw", "crudo", "", dict(min_g=50, max_g=150, porcion_g=80)),
    ("fruta", "caqui", "Caqui", "persimmons japanese raw", "crudo", "", {}),
    ("fruta", "chirimoya", "Chirimoya", "cherimoya raw", "crudo", "", {}),
    ("fruta", "papaya", "Papaya", "papayas raw", "crudo", "", {}),
    ("fruta", "limon", "Limón (zumo)", "lemon juice raw", "crudo", "", dict(min_g=5, max_g=30, porcion_g=10)),
    ("fruta", "zumo_naranja", "Zumo de naranja natural", "orange juice raw", "tal_cual", "azucar", dict(min_g=150, max_g=250, porcion_g=200, max_semana=3)),
    ("fruta", "compota_manzana", "Compota de manzana sin azúcar", "applesauce canned unsweetened", "tal_cual", "", {}),
    ("f_seca", "pasas", "Uvas pasas", "09298", "tal_cual", "", {}),
    ("f_seca", "datiles", "Dátiles", "dates medjool", "tal_cual", "", {}),
    ("f_seca", "orejones", "Orejones de albaricoque", "apricots dried sulfured uncooked", "tal_cual", "", {}),
    ("f_seca", "ciruelas_pasas", "Ciruelas pasas", "plums dried prunes uncooked", "tal_cual", "", {}),
    ("f_seca", "higos_secos", "Higos secos", "figs dried uncooked", "tal_cual", "", {}),
    # frutos secos y semillas
    ("fsecos", "avellanas", "Avellanas", "nuts hazelnuts or filberts", "tal_cual", "", {}),
    ("fsecos", "pistachos", "Pistachos", "nuts pistachio nuts dry roasted without salt", "tal_cual", "", {}),
    ("fsecos", "anacardos", "Anacardos", "nuts cashew nuts dry roasted without salt", "tal_cual", "", {}),
    ("fsecos", "pinones", "Piñones", "nuts pine nuts dried", "tal_cual", "", dict(min_g=5, max_g=25, porcion_g=15)),
    ("fsecos", "pipas_girasol", "Pipas de girasol peladas", "seeds sunflower seed kernels dried", "tal_cual", "", {}),
    ("fsecos", "pipas_calabaza", "Pipas de calabaza", "seeds pumpkin and squash seed kernels dried", "tal_cual", "", {}),
    ("fsecos", "chia", "Semillas de chía", "seeds chia seeds dried", "tal_cual", "", dict(min_g=5, max_g=25, porcion_g=15)),
    ("fsecos", "lino", "Semillas de lino", "seeds flaxseed", "tal_cual", "", dict(min_g=5, max_g=25, porcion_g=10)),
    ("fsecos", "sesamo", "Sésamo", "seeds sesame seeds whole dried", "tal_cual", "", dict(min_g=5, max_g=20, porcion_g=10)),
    ("fsecos", "crema_cacahuete", "Crema de cacahuete", "peanut butter smooth style without salt", "tal_cual", "", dict(min_g=10, max_g=30, porcion_g=20)),
    ("fsecos", "almendras_tostadas", "Almendras tostadas", "nuts almonds dry roasted without salt", "tal_cual", "", {}),
    # grasas
    ("grasa", "aceite_girasol", "Aceite de girasol", "oil sunflower linoleic", "tal_cual", "", {}),
    ("grasa", "mantequilla", "Mantequilla", "butter without salt", "tal_cual", "", dict(origen="animal", min_g=5, max_g=20, porcion_g=10, max_semana=3)),
    ("grasa", "margarina", "Margarina", "margarine regular 80% fat composite stick without salt", "tal_cual", "", dict(min_g=5, max_g=20, porcion_g=10, max_semana=3)),
    ("grasa", "mayonesa", "Mayonesa", "salad dressing mayonnaise regular", "tal_cual", "", dict(origen="animal", patron_aa="huevo", min_g=10, max_g=30, porcion_g=15, max_semana=2)),
    ("grasa", "nata_cocinar", "Nata para cocinar", "cream fluid light whipping", "tal_cual", "lacteo",
     dict(origen="animal", patron_aa="lacteo", comidas="C;X", min_g=20, max_g=60, porcion_g=30, max_semana=2)),
    # dulces
    ("dulce", "azucar_blanco", "Azúcar", "sugars granulated", "tal_cual", "", dict(patron_aa="ninguno", min_g=5, max_g=20, porcion_g=8, max_semana=7)),
    ("dulce", "galletas_maria", "Galletas tipo María", "cookies vanilla wafers lower fat", "tal_cual", "", {}),
    ("dulce", "galletas_integrales", "Galletas integrales", "crackers whole-wheat", "tal_cual", "integral", {}),
    ("dulce", "magdalena", "Magdalena", "muffins plain prepared from recipe made with low fat 2% milk", "tal_cual", "", dict(min_g=30, max_g=80, porcion_g=40)),
    ("dulce", "croissant", "Croissant", "croissants butter", "tal_cual", "", dict(min_g=40, max_g=80, porcion_g=55, max_semana=1)),
    ("dulce", "bizcocho", "Bizcocho casero", "cake pound commercially prepared butter", "tal_cual", "", dict(min_g=40, max_g=80, porcion_g=50, max_semana=1)),
    ("dulce", "donut", "Donut / rosquilla", "doughnuts cake-type plain", "tal_cual", "", dict(min_g=40, max_g=80, porcion_g=50, max_semana=1)),
    ("dulce", "chocolate_leche", "Chocolate con leche", "candies milk chocolate", "tal_cual", "",
     dict(origen="animal", patron_aa="lacteo", min_g=10, max_g=30, porcion_g=20)),
    ("dulce", "cacao_soluble", "Cacao soluble", "cocoa mix powder", "tal_cual", "", dict(min_g=5, max_g=20, porcion_g=10, max_semana=7)),
    ("dulce_l", "natillas", "Natillas", "puddings vanilla ready-to-eat", "tal_cual", "", {}),
    ("dulce_l", "flan", "Flan de huevo", "desserts flan caramel custard prepared-from-recipe", "tal_cual", "", dict(patron_aa="huevo")),
    ("dulce_l", "helado", "Helado de vainilla", "ice creams vanilla", "tal_cual", "", dict(min_g=50, max_g=120, porcion_g=80)),
    ("dulce_l", "arroz_leche", "Arroz con leche", "puddings rice ready-to-eat", "tal_cual", "", {}),
    # suplementos
    ("supl", "proteina_soja", "Proteína de soja aislada", "soy protein isolate", "tal_cual", "", {}),
    ("supl", "gelatina", "Gelatina (colágeno) en polvo", "gelatins dry powder unsweetened", "tal_cual", "",
     dict(origen="animal", patron_aa="ninguno", min_g=5, max_g=20, porcion_g=10)),
]


def main() -> None:
    data = REPO / "data"
    base = b.cargar_completa(data)
    alim = pd.read_csv(data / "alimentos.csv", dtype={"ndb": str})
    g = base.set_index("ndb")
    # estado_ref de los 69 actuales, deducido de la descripción FDC de su NDB
    def estado(ndb):
        d = str(g.at[ndb, "descripcion"]).lower() if ndb in g.index else ""
        if re.search(r"cooked|roasted|boiled|baked|grilled|broiled|fried|canned|hard-boiled", d):
            return "cocinado"
        return "crudo" if "raw" in d else "tal_cual"
    alim["estado_ref"] = alim["ndb"].map(estado)
    alim["fuente_catalogo"] = "v0.1"

    filas, rev = [], []
    for plant, id_, nombre, q, est, etq, cambios in N:
        assert id_ not in set(alim["id"]), id_
        if re.fullmatch(r"\d{5}", q):
            ndb, pts, alt = q, None, ""
        else:
            res = pd.concat([b.buscar(qq, n=3, base=base, data_dir=REPO / "__sin_glosario"  # consultas en inglés: sin traducir) for qq in q.split("|")]).sort_values(
                "puntuacion", ascending=False)
            if res.empty:
                raise SystemExit(f"sin resultado: {id_} ← {q}")
            ndb, pts = res["ndb"].iloc[0], round(float(res["puntuacion"].iloc[0]), 2)
            alt = " | ".join(f"{n} {d[:60]}" for n, d in zip(res["ndb"].iloc[1:3], res["descripcion"].iloc[1:3]))
        gr, rol, org, pat, com, lo, hi, por, ms, etq0 = P[plant]
        f = dict(id=id_, nombre=nombre, grupo=gr, rol=rol, origen=org, patron_aa=pat, comidas=com, min_g=lo,
                 max_g=hi, porcion_g=por, max_semana=ms, etiquetas=";".join(x for x in (etq0, etq) if x),
                 ndb=ndb, busqueda_fdc=q.split("|")[0], estado_ref=est, fuente_catalogo="propuesta T14")
        f.update(cambios)
        r = g.loc[ndb]
        for n in ("kcal", "proteina", "grasa", "agsat", "hc", "fibra", "sodio", "potasio", "fosforo", "calcio"):
            f[n] = round(float(r[n]), 2) if pd.notna(r[n]) else 0.0
        filas.append(f)
        rev.append(dict(id=id_, nombre=nombre, grupo=gr, consulta=q, ndb=ndb, descripcion_fdc=r["descripcion"],
                        estado_ref=est, tiene_aa=bool(pd.notna(r["leu"])), puntuacion=pts, alternativas=alt))
    nuevo = pd.concat([alim, pd.DataFrame(filas)], ignore_index=True)[list(alim.columns)]
    nuevo.to_csv(data / "catalogo_propuesto.csv", index=False)
    pd.DataFrame(rev).to_csv(data / "catalogo_revision.csv", index=False)
    print(f"catálogo propuesto: {len(nuevo)} alimentos ({len(filas)} nuevos); sin AA en FDC: "
          f"{sum(not x['tiene_aa'] for x in rev)}")


if __name__ == "__main__":
    main()
