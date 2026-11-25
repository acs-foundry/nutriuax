"""Página del modo hogar (ADR-0007 §3, T28, T31, T32): interfaz neutra, sin cabecera clínica.

- Hogares guardados en local (`hogares.py`): el último guardado se carga por defecto al abrir (p. ej. «Familia Ejemplo»).
- Intercambio con el dashboard Menú Familiar por JSON (`dashboard.py`): importar miembros y valoraciones; exportar
  la semana (comida y cena) para pegarla en «Importar del planificador» del dashboard.
Solo perfiles de `ambito = hogar`; los suelos de seguridad siempre se aplican.
"""
from __future__ import annotations

import datetime as dt
import json
import os

import pandas as pd

from . import composicion, dashboard, hogar as h, hogares, recetas as rc
from .equivalencias import ALERGENOS_UE
from .objetivos import NOMBRE_COMIDA, PERFILES

EJEMPLO = pd.DataFrame([
    dict(id="persona1", nombre="", sexo="H", edad=40, peso=78.0, talla=178.0, actividad=1.55, perfil="mantenimiento",
         alergias=""),
    dict(id="persona2", nombre="", sexo="M", edad=38, peso=62.0, talla=165.0, actividad=1.45, perfil="mantenimiento",
         alergias=""),
])


def ruta_recetas():
    return os.environ.get("NUTRIUAX_RECETAS") or None


def _lunes_siguiente(hoy: dt.date) -> dt.date:
    return hoy + dt.timedelta(days=(7 - hoy.weekday()) % 7 or 7)


def _miembros_base(st) -> pd.DataFrame:
    if "h_tabla" not in st.session_state:
        nombre = hogares.por_defecto()
        st.session_state.h_tabla = hogares.cargar(nombre) if nombre else EJEMPLO.copy()
        st.session_state.h_nombre = nombre or ""
    return st.session_state.h_tabla


def _seccion_hogar(st, perfiles: list[str]) -> pd.DataFrame:
    guardados = hogares.listar()
    c1, c2 = st.columns([3, 1])
    if guardados:
        actual = st.session_state.get("h_nombre") or guardados[0]
        elegido = c1.selectbox("Hogar guardado", guardados,
                               index=guardados.index(actual) if actual in guardados else 0, key="h_sel")
        if c2.button("Cargar", key="h_cargar"):
            st.session_state.h_tabla = hogares.cargar(elegido)
            st.session_state.h_nombre = elegido
            st.session_state.pop("h_miembros", None)
            st.rerun()
    st.subheader("Quién come en casa")
    miembros = st.data_editor(
        _miembros_base(st), num_rows="dynamic", width="stretch", key="h_miembros",
        column_config={
            "id": st.column_config.TextColumn("Id (como en el dashboard)"),
            "nombre": st.column_config.TextColumn("Nombre (solo en este equipo)"),
            "sexo": st.column_config.SelectboxColumn("Sexo", options=["H", "M"]),
            "edad": st.column_config.NumberColumn("Edad", min_value=2, max_value=110, step=1),
            "peso": st.column_config.NumberColumn("Peso (kg)", min_value=10.0, max_value=250.0),
            "talla": st.column_config.NumberColumn("Talla (cm)", min_value=60.0, max_value=230.0),
            "actividad": st.column_config.NumberColumn("Actividad (1,2-1,9)", min_value=1.0, max_value=2.5),
            "perfil": st.column_config.SelectboxColumn("Objetivo", options=perfiles),
            "alergias": st.column_config.TextColumn("Alergias (separadas por «;»)", help="; ".join(ALERGENOS_UE)),
        })
    g1, g2 = st.columns([3, 1])
    nombre = g1.text_input("Guardar como (queda en este equipo y se carga por defecto)",
                           value=st.session_state.get("h_nombre", ""), key="h_guardar_nombre",
                           placeholder="p. ej. Familia Ejemplo")
    if g2.button("Guardar hogar", key="h_guardar"):
        try:
            hogares.guardar(nombre, miembros)
            st.session_state.h_nombre = nombre
            st.session_state.h_tabla = miembros
            st.success(f"Hogar «{nombre}» guardado en este equipo (fuera del repo) y marcado por defecto.")
        except ValueError as e:
            st.error(str(e))
    with st.expander("Traer miembros y valoraciones del dashboard Menú Familiar"):
        st.caption("En el dashboard: Semana → «Exportar al planificador» → Copiar. Pega aquí el texto. Peso, talla y "
                   "actividad se conservan de este hogar; del dashboard se toman nombre, objetivo y alergias.")
        texto = st.text_area("JSON del dashboard", key="h_import_txt", height=120)
        if st.button("Importar", key="h_importar") and texto.strip():
            try:
                nuevos, vals = dashboard.importar(json.loads(texto), miembros)
                st.session_state.h_tabla = nuevos
                st.session_state.h_valoraciones = vals
                st.session_state.pop("h_miembros", None)
                st.success(f"{len(nuevos)} miembros y {len(vals)} valoraciones importados. Completa peso y talla "
                           "si falta alguno y pulsa «Guardar hogar».")
                st.rerun()
            except (json.JSONDecodeError, dashboard.FormatoInvalido) as e:
                st.error(f"No se pudo importar: {e}")
    return miembros


def pagina(st) -> None:
    st.title("Menú de la semana")
    st.caption("Planificador de menús familiares. Los datos de las personas solo se guardan en este equipo si pulsas "
               "«Guardar hogar». Los perfiles son puntos de partida orientativos, no una prescripción.")
    perfiles = [k for k, p in PERFILES.items() if p.ambito == "hogar"]
    with st.sidebar:
        st.header("Semana")
        inicio = st.date_input("Empieza el lunes", value=_lunes_siguiente(dt.date.today()), key="h_inicio")
        inicio = inicio - dt.timedelta(days=inicio.weekday())
        dias = st.slider("Días", 1, 7, 7, key="h_dias")
        batch = st.checkbox("Cocino el domingo para lunes-viernes", value=False, key="h_batch")
        minutos = st.slider("Minutos máximos de cocina entre semana", 15, 120, 45, 5, key="h_min")
    miembros = _seccion_hogar(st, perfiles)
    if st.button("Generar menú", type="primary", key="h_generar"):
        try:
            lista = []
            for r in miembros.dropna(subset=["id"]).itertuples():
                if any(pd.isna(getattr(r, c)) or getattr(r, c) in ("", None) for c in ("sexo", "edad", "peso", "talla")):
                    raise ValueError(f"{r.id}: faltan sexo, edad, peso o talla")
                alg = {a.strip() for a in str(r.alergias or "").split(";") if a.strip()}
                desconocidas = alg - set(ALERGENOS_UE)
                if desconocidas:
                    raise ValueError(f"{r.id}: alergias desconocidas {sorted(desconocidas)}")
                lista.append(h.Miembro(str(r.id), r.sexo, int(r.edad), float(r.peso), float(r.talla),
                                       float(r.actividad or 1.55), r.perfil, alg))
            recs = rc.cargar_recetas(ruta_recetas())
            with st.spinner("Eligiendo platos y raciones…"):
                st.session_state.menu_hogar = h.generar_hogar(
                    h.Hogar(lista), recs, composicion.cargar(),
                    h.Opciones(dias=dias, mes=inicio.month, batch=batch, minutos_max_laborable=minutos,
                               valoraciones=st.session_state.get("h_valoraciones", {})),
                    rc.cobertura_minima())
                st.session_state.menu_inicio = inicio
        except (ValueError, FileNotFoundError, RuntimeError, KeyError) as e:
            st.error(str(e))
            return
    if "menu_hogar" not in st.session_state:
        return
    menu: h.MenuHogar = st.session_state.menu_hogar
    for a in menu.avisos:
        st.warning(a)
    t_menu, t_raciones, t_nutr, t_dash = st.tabs(["Menú", "Raciones por persona", "Energía y proteína",
                                                  "Enviar al dashboard"])
    with t_menu:
        p = menu.platos.assign(comida=menu.platos.comida.map(NOMBRE_COMIDA))
        st.dataframe(p[["dia", "comida", "rol", "nombre"]], width="stretch", hide_index=True)
    with t_raciones:
        r = menu.raciones.assign(comida=menu.raciones.comida.map(NOMBRE_COMIDA))
        st.dataframe(r[["miembro", "n_dia", "comida", "nombre", "k", "gramos_crudo"]], width="stretch", hide_index=True)
        st.caption("k = veces la ración de un adulto; gramos en crudo.")
        if len(menu.complementos):
            st.dataframe(menu.complementos.assign(comida=menu.complementos.comida.map(NOMBRE_COMIDA)),
                         width="stretch", hide_index=True)
    with t_nutr:
        st.dataframe(menu.resumen[["miembro", "n_dia", "kcal_obj", "kcal", "kcal_desv", "prot_obj", "proteina", "fibra"]],
                     width="stretch", hide_index=True)
    with t_dash:
        envio = json.dumps(dashboard.exportar(menu, st.session_state.get("menu_inicio", inicio)), ensure_ascii=False)
        st.caption("Copia este texto y, en el dashboard Menú Familiar, pulsa «Importar del planificador» y pégalo. Se "
                   "escriben la comida y la cena de esos días; el desayuno y la merienda no se tocan.")
        st.code(envio, language="json")
        st.download_button("Descargar (JSON)", envio, file_name="nutriuax_para_dashboard.json",
                           mime="application/json", key="h_descarga")
