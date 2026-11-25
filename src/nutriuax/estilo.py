"""Identidad visual abierta de NutriUAX (licencia MIT; sin recursos externos ni marcas propietarias).

Paleta clínica propia (verde salvia #0F6B5E y azul petróleo #164E63). Todos los textos interpolados
en HTML se escapan con `html.escape` para evitar XSS.
"""
from __future__ import annotations

import html
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / "assets"
LOGO = ASSETS / "nutriuax_logo.svg"
MARCA = ASSETS / "nutriuax_icon.svg"
FAVICON = ASSETS / "nutriuax_icon.svg"

PRIMARIO = "#0F6B5E"
PRIMARIO_OSCURO = "#164E63"
PRIMARIO_CLARO = "#E6F4F1"
TINTA = "#1E293B"
GRIS = "#5B6573"
BORDE = "#E2E8F0"

# Alias retrocompatibles
AZUL = PRIMARIO
AZUL_OSCURO = PRIMARIO_OSCURO
AZUL_CLARO = PRIMARIO_CLARO

CSS = f"""
<style>
:root {{ --nuax-primario:{PRIMARIO}; --nuax-oscuro:{PRIMARIO_OSCURO}; --nuax-claro:{PRIMARIO_CLARO};
         --nuax-tinta:{TINTA}; --nuax-gris:{GRIS}; --nuax-borde:{BORDE}; }}
html, body, [class*="css"] {{ font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1440px; }}
#MainMenu, footer {{ visibility: hidden; }}

/* cabecera */
.nuax-hero {{ background: linear-gradient(120deg, var(--nuax-primario) 0%, var(--nuax-oscuro) 100%);
  color: #fff; border-radius: 16px; padding: 22px 28px; margin-bottom: 18px;
  display: flex; align-items: center; justify-content: space-between; gap: 24px;
  box-shadow: 0 6px 18px rgba(15, 107, 94, .18); }}
.nuax-hero h1 {{ color: #fff; font-size: 1.9rem; font-weight: 750; letter-spacing: -.02em; margin: 0; padding: 0; }}
.nuax-hero h1 span {{ font-weight: 400; opacity: .88; }}
.nuax-hero p {{ margin: 4px 0 0; opacity: .92; font-size: .95rem; }}
.nuax-chip {{ display: inline-block; background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.35);
  border-radius: 999px; padding: 4px 12px; font-size: .78rem; font-weight: 600; white-space: nowrap; }}
.nuax-chip.aviso {{ background: #FFF4E5; color: #8A4B00; border-color: #FFD8A8; }}

/* tarjetas de objetivos */
[data-testid="stMetric"] {{ background: #fff; border: 1px solid var(--nuax-borde); border-left: 4px solid var(--nuax-primario);
  border-radius: 12px; padding: 14px 18px; box-shadow: 0 1px 2px rgba(16,24,40,.05); }}
[data-testid="stMetricLabel"] p {{ color: var(--nuax-gris); font-weight: 600; text-transform: uppercase;
  font-size: .72rem; letter-spacing: .06em; }}
[data-testid="stMetricValue"] {{ color: var(--nuax-tinta); font-weight: 700; }}

/* pestañas */
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; border-bottom: 1px solid var(--nuax-borde); flex-wrap: wrap; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; padding: 8px 14px; border-radius: 10px 10px 0 0; }}
.stTabs [aria-selected="true"] {{ color: var(--nuax-primario); background: var(--nuax-claro); }}

/* barra lateral */
[data-testid="stSidebar"] {{ background: #F5FAF8; border-right: 1px solid var(--nuax-borde); }}
[data-testid="stSidebar"] h2 {{ font-size: .8rem; text-transform: uppercase; letter-spacing: .08em;
  color: var(--nuax-primario); margin-top: .6rem; }}

/* botones, tablas y avisos */
.stButton > button, .stDownloadButton > button {{ border-radius: 10px; font-weight: 600; }}
.stButton > button[kind="primary"] {{ box-shadow: 0 4px 12px rgba(15, 107, 94, .22); }}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{ border: 1px solid var(--nuax-borde); border-radius: 12px; overflow: hidden; }}
[data-testid="stExpander"] details {{ border-radius: 12px; border-color: var(--nuax-borde); }}
[data-testid="stAlert"] {{ border-radius: 12px; }}

/* pie */
.nuax-pie {{ margin-top: 36px; padding-top: 14px; border-top: 1px solid var(--nuax-borde);
  color: var(--nuax-gris); font-size: .8rem; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }}
</style>
"""


def aplicar(st) -> None:
    """Aplica estilos y logotipo vectorial MIT de NutriUAX."""
    st.markdown(CSS, unsafe_allow_html=True)
    if LOGO.exists():
        st.logo(str(LOGO), size="large", icon_image=str(MARCA) if MARCA.exists() else None)


def cabecera(st, perfil: str, fuente: str) -> None:
    perfil_seguro = html.escape(str(perfil), quote=True)
    chip = ('<span class="nuax-chip">USDA FoodData Central</span>' if fuente == "fdc"
            else '<span class="nuax-chip aviso">Tabla semilla · AA estimados</span>')
    st.markdown(
        f"""<div class="nuax-hero"><div><h1>NutriUAX <span>· nutrición clínica y control de BCAA</span></h1>
        <p>Perfil: <b>{perfil_seguro}</b> · leucina, isoleucina y valina por kg de peso o de masa magra</p></div>
        <div>{chip}</div></div>""",
        unsafe_allow_html=True)


def pie(st) -> None:
    st.markdown(
        """<div class="nuax-pie"><span>NutriUAX · Software abierto de nutrición clínica e investigación (MIT)</span>
        <span>Composición: USDA FoodData Central SR Legacy (CC0) · ejecución 100 % local</span></div>""",
        unsafe_allow_html=True)
