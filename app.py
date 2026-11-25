"""NutriUAX Studio · Planificador clínico, control de BCAA, intercambios, fármacos y encuestas.

Arranque:  streamlit run app.py   (o `nutriuax`; se abre en http://127.0.0.1:8501, 100 % local)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from nutriuax import (  # noqa: E402
    base_fdc as bf,
    clinica,
    coccion,
    composicion as c,
    encuestas,
    estilo,
    exportar,
    farmacos,
    generador as g,
    intercambios,
    objetivos as o,
    office,
)

# Modo de uso (ADR-0007 §3): estudio (cabecera clínica) · consulta (neutro, todos los perfiles) · hogar
MODO = os.environ.get("NUTRIUAX_MODO", "estudio").strip().lower()
if MODO not in ("estudio", "consulta", "hogar"):
    MODO = "estudio"
if MODO == "estudio":
    st.set_page_config(page_title="NutriUAX Studio", layout="wide",
                       page_icon=str(estilo.FAVICON) if estilo.FAVICON.exists() else None)
    estilo.aplicar(st)
else:
    st.set_page_config(page_title="Planificador de menús", layout="wide")
if MODO == "hogar":
    from nutriuax import ui_hogar  # noqa: E402
    ui_hogar.pagina(st)
    st.stop()


@st.cache_resource
def comp_cargada():
    return c.cargar()


@st.cache_resource
def base_completa():
    return bf.cargar_completa()


comp_cat = comp_cargada()            # catálogo curado: lo usa el generador
base_fdc = base_completa()           # base completa FDC (o None si no se ha generado)
extra = st.session_state.setdefault("fdc_extra", [])
comp = comp_cat.anadir([bf.fila_composicion(n, base=base_fdc) for n in extra]) if extra and base_fdc is not None \
    else comp_cat                    # + alimentos FDC añadidos a mano en esta sesión
tab = comp.tabla
nombre_a_id = {tab.at[i, "nombre"]: i for i in tab.index}
nombres_catalogo = sorted(comp_cat.tabla["nombre"])

# ---------------- barra lateral: persona y perfil
with st.sidebar:
    st.header("Persona")
    codigo = st.text_input("Código (seudónimo, nunca el nombre)", "P001")
    c1, c2 = st.columns(2)
    sexo = c1.selectbox("Sexo", ["M", "H"], format_func=lambda s: "Mujer" if s == "M" else "Hombre")
    edad = c2.number_input("Edad", 16, 100, 22)
    peso = c1.number_input("Peso (kg)", 30.0, 200.0, 70.0, 0.5)
    talla = c2.number_input("Talla (cm)", 120.0, 220.0, 172.0, 0.5)
    actividad = st.select_slider("Actividad (factor)", [1.2, 1.375, 1.55, 1.6, 1.725, 1.9], 1.55)
    mm = st.number_input("Masa magra (kg, opcional)", 0.0, 150.0, 0.0, 0.5)
    kcal_man = st.number_input("Energía fijada a mano (kcal, 0 = calcular)", 0, 6000, 0, 50)
    persona = o.Persona(codigo, sexo, int(edad), float(peso), float(talla), float(actividad),
                        float(mm) or None, float(kcal_man) or None)

    st.header("Perfil")
    # perfiles de hogar: solo en modo hogar/consulta con suelos de seguridad (T28)
    claves_app = [k for k, pf in o.PERFILES.items() if MODO == "consulta" or pf.ambito != "hogar"]
    clave = st.selectbox("Dieta", claves_app, format_func=lambda k: o.PERFILES[k].nombre)
    base = o.PERFILES[clave]
    st.caption(base.descripcion)

    with st.expander("Ajustar objetivos", expanded=False):
        pg = st.slider("Proteína (g/kg/día)", 0.3, 3.0, base.proteina_gkg, 0.05)
        gp = st.slider("Grasa (% energía)", 10, 55, base.grasa_pct)
        hp = st.slider("HC (% energía)", 20, 70, base.hc_pct)
        por_mm = st.checkbox("Aminoácidos por kg de masa magra", base.aa_por_masa_magra,
                             disabled=not persona.masa_magra)
        aa_min, aa_max = dict(base.aa_min_mgkg), dict(base.aa_max_mgkg)
        for a, etq in (("leu", "Leucina"), ("ile", "Isoleucina"), ("val", "Valina")):
            cc1, cc2 = st.columns(2)
            aa_min[a] = cc1.number_input(f"{etq} mín. (mg/kg)", 0.0, 400.0, float(aa_min.get(a, 0)), 1.0)
            vmax = cc2.number_input(f"{etq} máx. (mg/kg, 0 = sin)", 0.0, 400.0, float(aa_max.get(a, 0)), 1.0)
            if vmax:
                aa_max[a] = vmax
            else:
                aa_max.pop(a, None)
        na = st.number_input("Sodio máx. (mg)", 0, 6000, int(base.sodio_max or 0), 100)
        k = st.number_input("Potasio máx. (mg, 0 = sin)", 0, 8000, int(base.potasio_max or 0), 100)
        p_ = st.number_input("Fósforo máx. (mg, 0 = sin)", 0, 3000, int(base.fosforo_max or 0), 50)
    perfil = base.copia(proteina_gkg=tuple(pg), grasa_pct=tuple(gp), hc_pct=tuple(hp), aa_min_mgkg=aa_min,
                        aa_max_mgkg=aa_max, aa_por_masa_magra=por_mm, sodio_max=na or None,
                        potasio_max=k or None, fosforo_max=p_ or None)

    st.header("Clínica y medicación")
    meds_sel = st.multiselect(
        "Medicación (interacciones)",
        list(farmacos.VADEMECUM.keys()),
        format_func=lambda m: farmacos.VADEMECUM[m].nombre,
    )
    erc_doble = st.checkbox("Doble cocción ERC (reducir potasio)", value=clave in ("erc_nd", "erc_hd"))

    st.header("Menú")
    n_com = st.radio("Comidas al día", [5, 4, 3], horizontal=True)
    perfil.comidas = {5: ["D", "MM", "C", "M", "X"], 4: ["D", "C", "M", "X"], 3: ["D", "C", "X"]}[n_com]
    vetos = st.multiselect("Alimentos excluidos (alergias, gustos)", nombres_catalogo)
    semilla = st.number_input("Variante (cambia para otro menú)", 0, 9999, 0)
    # IMPORTANTE: mantener `Días` como último slider de la barra lateral (contrato test_app.py)
    dias = st.slider("Días", 1, 7, 7)

if perfil.ambito == "hogar":                  # perfiles domésticos: siempre con suelos de seguridad
    from nutriuax.seguridad import PerfilNoPermitido, objetivos_seguros  # noqa: E402
    try:
        obj = objetivos_seguros(persona, perfil)
    except PerfilNoPermitido as e:
        st.error(str(e))
        st.stop()
    for av in obj.avisos:
        st.warning(av)
else:
    obj = o.calcular_objetivos(persona, perfil)

# ---------------- cabecera
if MODO == "estudio":
    estilo.cabecera(st, perfil.nombre, comp.fuente)
else:
    st.title("Planificador de menús")
    st.caption(f"Perfil: {perfil.nombre}")
if comp.fuente != "fdc":
    st.error("Tabla de composición SEMILLA: los aminoácidos se estiman por patrón de grupo. Sirve para "
             "probar la herramienta, no para resultados de estudio. Importa USDA FDC (ver README).")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Energía objetivo", f"{obj.kcal:.0f} kcal")
m2.metric("Proteína", f"{obj.proteina[0]:.0f}–{obj.proteina[1]:.0f} g")
m3.metric("Leu mín.", f"{obj.minimos.get('leu', 0)/1000:.2f} g")
m4.metric("BCAA mín.", f"{sum(obj.minimos.get(a, 0) for a in ('leu', 'ile', 'val'))/1000:.2f} g")
for av in o.avisos_coherencia(obj):
    st.warning(av)

if st.button("Generar menú", type="primary", icon=":material/restaurant_menu:"):
    with st.spinner("Optimizando el menú (hasta ~30 s)…"):
        try:
            st.session_state.menu = g.generar(comp_cat, obj, dias=dias, semilla=int(semilla),
                                              vetados={nombre_a_id[n] for n in vetos})
            st.session_state.persona = persona
        except RuntimeError as e:
            st.error(str(e))

menu: g.Menu | None = st.session_state.get("menu")
if menu is None:
    st.info("Ajusta persona y perfil en la barra lateral y pulsa **Generar menú**.", icon=":material/tune:")
    if MODO == "estudio":
        estilo.pie(st)
    st.stop()

enr_coc = coccion.enriquecer_menu_coccion(menu.items, comp, erc_doble_coccion=erc_doble)
inter_res = intercambios.intercambios_de_menu(menu, comp)
cal_prot = clinica.calidad_proteica_menu(menu, edad=persona.edad)
meds_res = farmacos.evaluar_interacciones(meds_sel, menu=menu)
antro = clinica.evaluar_antropometria(persona)

(
    t_menu,
    t_inter,
    t_edit,
    t_nutr,
    t_farm,
    t_enc,
    t_antro,
    t_compra,
    t_alim,
) = st.tabs(
    [
        ":material/calendar_month: Menú (Crudo/Cocinado)",
        ":material/swap_horiz: Intercambios",
        ":material/edit_note: Editar a mano",
        ":material/monitoring: Nutrientes, BCAA y PRAL",
        ":material/medication: Fármaco-Nutriente",
        ":material/assignment: Encuestas y Adherencia",
        ":material/straighten: Antropometría y Cribado",
        ":material/shopping_cart: Lista de la compra",
        ":material/nutrition: Tabla de alimentos",
    ]
)

with t_menu:
    vista_peso = st.radio(
        "Mostrar pesos en",
        ["Ambos (crudo → cocinado)", "Cocinado (plato)", "Crudo (compra)"],
        horizontal=True,
        key="vista_peso_menu",
    )
    if vista_peso == "Cocinado (plato)":
        etiqueta = enr_coc["nombre"] + " (" + enr_coc["gramos_cocinado"].round().astype(int).astype(str) + " g coc.)"
    elif vista_peso == "Crudo (compra)":
        etiqueta = enr_coc["nombre"] + " (" + enr_coc["gramos_crudo"].round().astype(int).astype(str) + " g crudo)"
    else:
        etiqueta = (
            enr_coc["nombre"]
            + " ("
            + enr_coc["gramos_crudo"].round().astype(int).astype(str)
            + "→"
            + enr_coc["gramos_cocinado"].round().astype(int).astype(str)
            + " g)"
        )
    it = enr_coc.assign(linea=etiqueta)
    orden = [o.NOMBRE_COMIDA[m] for m in o.COMIDAS]
    piv = (it.groupby(["comida", "n_dia"])["linea"].apply("\n".join).unstack("n_dia")
           .reindex([x for x in orden if x in set(it["comida"])]))
    piv.columns = [o.DIAS[(d - 1) % 7] for d in piv.columns]
    st.dataframe(piv, width="stretch", height=520)
    st.caption(f"Estado del optimizador: {menu.estado} · fuente: {menu.fuente} · crudo→cocinado según USDA RF6 / Bognár 2002.")

with t_inter:
    st.subheader("Intercambios diarios medios (Sistema Español)")
    cols_i = st.columns(4)
    for idx_g, (gk, val) in enumerate(inter_res["media_diaria"].items()):
        cols_i[idx_g % 4].metric(inter_res["definiciones"][gk]["nombre"], f"{val:.1f} / día")
    st.subheader("Intercambios por día")
    st.dataframe(inter_res["por_dia"], width="stretch", hide_index=True)
    with st.expander("Guía de equivalencias para el paciente (1 intercambio = X g)"):
        st.dataframe(intercambios.guia_intercambios(comp), width="stretch", hide_index=True)

with t_edit:
    st.write("Cambia alimentos o gramos y pulsa **Recalcular**. Las comprobaciones se rehacen con tus cambios.")
    with st.expander("Añadir un alimento de la base completa USDA (≈ 7.800 alimentos)"):
        if base_fdc is None:
            st.info("Falta la base completa: ejecuta `python -m nutriuax.importar_fdc ZIP` (ver README).")
        else:
            q = st.text_input("Buscar (en español o en inglés; p. ej. «garbanzos cocidos», «pechuga de pavo»)",
                              key="q_fdc")
            res = bf.buscar(q, n=20, base=base_fdc) if q else None
            if res is not None and res.empty:
                st.warning("Sin resultados: prueba con otra palabra o en inglés.")
            elif res is not None:
                desc = dict(zip(res["ndb"], res["descripcion"]))
                aa = dict(zip(res["ndb"], res["tiene_aa"]))
                elegido = st.selectbox("Resultado", list(res["ndb"]),
                                       format_func=lambda n: f"{desc[n]} [FDC {n}]" + ("" if aa[n] else " · AA estimados"))
                a1, a2, a3, a4 = st.columns(4)
                d_add = a1.number_input("Día", 1, int(menu.items["n_dia"].max()), 1, key="d_fdc")
                m_add = a2.selectbox("Comida", list(o.NOMBRE_COMIDA), format_func=o.NOMBRE_COMIDA.get, key="m_fdc")
                gr_add = a3.number_input("Gramos", 1, 2000, 100, 5, key="g_fdc")
                if a4.button("Añadir al menú"):
                    if elegido not in extra:
                        extra.append(elegido)
                    comp_n = comp_cat.anadir([bf.fila_composicion(n, base=base_fdc) for n in extra])
                    fila = bf.fila_composicion(elegido, base=base_fdc)
                    nueva = pd.DataFrame([dict(dia=o.DIAS[(d_add - 1) % 7], n_dia=int(d_add), comida=o.NOMBRE_COMIDA[m_add],
                                               cod_comida=m_add, id=fila.name, nombre=fila["nombre"], gramos=float(gr_add))])
                    base_items = menu.items[["dia", "n_dia", "comida", "cod_comida", "id", "nombre", "gramos"]]
                    st.session_state.menu = g.evaluar(comp_n, obj, pd.concat([base_items, nueva], ignore_index=True),
                                                      "editado a mano")
                    st.rerun()
    ed = st.data_editor(
        menu.items[["n_dia", "dia", "cod_comida", "comida", "nombre", "gramos"]],
        column_config={"nombre": st.column_config.SelectboxColumn("Alimento", options=sorted(nombre_a_id)),
                       "gramos": st.column_config.NumberColumn("g", min_value=0, step=5)},
        num_rows="dynamic", width="stretch", key="editor")
    if st.button("Recalcular"):
        ed = ed.dropna(subset=["nombre", "gramos"]).copy()
        ed["n_dia"] = ed["n_dia"].fillna(1).astype(int)
        ed["dia"] = ed["n_dia"].map(lambda d: o.DIAS[(d - 1) % 7])
        ed["cod_comida"] = ed["cod_comida"].fillna("C")
        ed["comida"] = ed["cod_comida"].map(o.NOMBRE_COMIDA)
        ed["id"] = ed["nombre"].map(nombre_a_id)
        st.session_state.menu = g.evaluar(comp, obj, ed.reset_index(drop=True), "editado a mano")
        st.rerun()

with t_nutr:
    ch = g.comprobar(menu)
    n_fuera = int((~ch.ok).sum())
    (st.success if n_fuera == 0 else st.warning)(f"{len(ch) - n_fuera} de {len(ch)} criterios dentro de rango.")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("AAS (WHO 2007)", f"{cal_prot['aas_global_pct']} %", f"Limitante: {cal_prot['aminoacido_limitante']}")
    k2.metric("PRAL renal medio", f"{cal_prot['pral_medio_meq_dia']} mEq/d")
    k3.metric("Tomas ≥ umbral Leu", f"{cal_prot['tomas_principales_con_umbral_leu']}/{cal_prot['tomas_principales_totales']}",
              f"Umbral ≥ {cal_prot['umbral_leucina_toma_g']} g")
    k4.metric("Proteína animal / vegetal", f"{cal_prot['proteina_animal_pct']:.0f}% / {cal_prot['proteina_vegetal_pct']:.0f}%")

    r = menu.resumen.copy()
    r["pral_meq"] = cal_prot["pral_por_dia"]
    cols = ["dia", "kcal", "proteina", "proteina_gkg", "pct_proteina", "pct_grasa", "pct_hc", "fibra",
            "proteina_animal", "proteina_vegetal", "leu", "ile", "val", "bcaa_mg", "leu_mgkg", "ile_mgkg",
            "val_mgkg", "sodio", "potasio", "fosforo", "pral_meq"]
    st.dataframe(r[cols].round(1), width="stretch", hide_index=True)
    st.subheader("Leu / Ile / Val (mg/kg/día) frente al mínimo")
    graf = r.set_index("dia")[["leu_mgkg", "ile_mgkg", "val_mgkg"]]
    graf.columns = ["Leucina", "Isoleucina", "Valina"]
    st.bar_chart(graf)
    st.caption("Mínimos: " + ", ".join(f"{a} {v/obj.kg_referencia:.0f} mg/kg" for a, v in obj.minimos.items()
                                        if a in ("leu", "ile", "val")))
    st.subheader("Comprobación por día")
    solo_fuera = st.checkbox("Mostrar solo lo que está fuera de rango", n_fuera > 0)
    vista = ch.assign(estado=ch["ok"].map({True: "✅ en rango", False: "❌ fuera"})).drop(columns="ok")
    st.dataframe(vista[~ch["ok"]] if solo_fuera else vista, width="stretch", hide_index=True)

with t_farm:
    if not meds_sel:
        st.info("Selecciona uno o más fármacos en «Clínica y medicación» en la barra lateral para evaluar interacciones con este menú.")
    else:
        st.write(f"**Alertas activas:** {meds_res['total_alertas']} (Altas: {meds_res['altas']} · Medias: {meds_res['medias']} · Bajas: {meds_res['bajas']})")
        for al in meds_res["alertas"]:
            fn = st.error if al["severidad"] == "alta" else (st.warning if al["severidad"] == "media" else st.info)
            detalle = f"**[{al['severidad'].upper()}] {al['farmaco']}** ({al['clase']})\n\n"
            detalle += f"- **Mecanismo:** {al['mecanismo']}\n"
            detalle += f"- **Recomendación:** {al['recomendacion']}\n"
            for tr in al["disparadores"]:
                detalle += f"- **Menú actual:** {tr}\n"
            detalle += f"\n*{al['referencia']}*"
            fn(detalle)

with t_enc:
    st.subheader("MEDAS-14 y Adherencia por NUU 24 h (Maroni)")
    e1, e2 = st.columns(2)
    with e1:
        aove_p = st.checkbox("Usa AOVE como grasa principal", True, key="med_1")
        aove_c = st.number_input("Cucharadas AOVE/día", 0.0, 12.0, 4.0, 0.5, key="med_2")
        verd_d = st.number_input("Raciones verdura/día", 0.0, 10.0, 2.0, 0.5, key="med_3")
        frut_d = st.number_input("Piezas fruta/día", 0.0, 10.0, 3.0, 0.5, key="med_4")
        cr_d = st.number_input("Raciones carne roja/día", 0.0, 5.0, 0.3, 0.1, key="med_5")
        mant_d = st.number_input("Raciones mantequilla/día", 0.0, 5.0, 0.0, 0.5, key="med_6")
        beb_d = st.number_input("Bebidas azucaradas/día", 0.0, 10.0, 0.0, 0.5, key="med_7")
    with e2:
        vino_s = st.number_input("Copas vino/semana", 0.0, 30.0, 0.0, 1.0, key="med_8")
        leg_s = st.number_input("Legumbres/semana", 0.0, 14.0, 3.0, 0.5, key="med_9")
        pes_s = st.number_input("Pescado/marisco/semana", 0.0, 14.0, 3.0, 0.5, key="med_10")
        bol_s = st.number_input("Bollería comercial/semana", 0.0, 21.0, 1.0, 0.5, key="med_11")
        fs_s = st.number_input("Frutos secos/semana", 0.0, 14.0, 3.0, 0.5, key="med_12")
        ave_p = st.checkbox("Prefiere ave/conejo a carne roja", True, key="med_13")
        sof_s = st.number_input("Sofrito/semana", 0.0, 14.0, 2.0, 0.5, key="med_14")
    med_res = encuestas.calcular_medas14({
        "aove_grasa_principal": aove_p, "aove_cucharadas_dia": aove_c, "verdura_raciones_dia": verd_d,
        "fruta_raciones_dia": frut_d, "carne_roja_raciones_dia": cr_d, "mantequilla_raciones_dia": mant_d,
        "bebidas_azucaradas_dia": beb_d, "vino_copas_semana": vino_s, "legumbres_raciones_semana": leg_s,
        "pescado_marisco_semana": pes_s, "bolleria_comercial_semana": bol_s, "frutos_secos_semana": fs_s,
        "prefiere_ave_sobre_roja": ave_p, "sofrito_semana": sof_s,
    })
    nuu = st.number_input("Nitrógeno ureico urinario 24 h (g/día, 0 = sin NUU)", 0.0, 40.0, 0.0, 0.5, key="enc_nuu")
    st.metric("Puntuación MEDAS-14", f"{med_res.puntuacion} / 14", med_res.categoria)
    if nuu > 0:
        p_mar = encuestas.proteina_maroni(nuu, persona.peso)
        st.metric("Proteína estimada por Maroni (1985)", f"{p_mar:.1f} g/día", f"{p_mar / persona.peso:.2f} g/kg")

with t_antro:
    st.subheader("Antropometría y 5 ecuaciones de gasto energético")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("IMC (OMS)", f"{antro['imc']} kg/m²", antro["clasificacion_oms"])
    a2.metric("Peso ideal (Devine)", f"{antro['peso_ideal_devine_kg']} kg")
    a3.metric("Peso ajustado", f"{antro['peso_ajustado_kg']} kg")
    a4.metric("Masa magra", f"{antro['masa_magra_kg']} kg", antro["masa_magra_origen"])
    eq_df = pd.DataFrame(
        [{"Ecuación": k, "TMB (kcal/d)": v["tmb_kcal"], "GET (kcal/d)": v["get_kcal"]}
         for k, v in antro["ecuaciones_energeticas"].items()]
    )
    st.dataframe(eq_df, width="stretch", hide_index=True)
    with st.expander("Cribado de desnutrición MUST (BAPEN)"):
        perd = st.number_input("Pérdida de peso involuntaria últimos 3–6 meses (%)", 0.0, 40.0, 0.0, 0.5, key="must_p")
        aguda = st.checkbox("Enfermedad aguda sin ingesta > 5 días", False, key="must_a")
        m_res = clinica.cribado_must(antro["imc"], perd, aguda)
        st.info(f"**MUST = {m_res['puntuacion']} (Riesgo {m_res['riesgo']})** · {m_res['plan_accion']}")

with t_compra:
    compra = (
        enr_coc.groupby("nombre", as_index=False)[["gramos_crudo", "gramos_cocinado"]]
        .sum()
        .sort_values("nombre")
        .rename(columns={"gramos_crudo": "Comprar en crudo (g)", "gramos_cocinado": "Equivalente cocinado (g)"})
    )
    st.dataframe(compra.round(0), width="stretch", hide_index=True)

with t_alim:
    mostrar = ["nombre", "grupo", "rol", "origen", "kcal", "proteina", "grasa", "hc", "fibra", "leu", "ile",
               "val", "sodio", "potasio", "fosforo", "leu_estimado"]
    st.dataframe(comp_cat.tabla[mostrar].round(1), width="stretch")
    st.caption("Por 100 g de porción comestible. leu_estimado = aminoácido estimado por patrón (sin dato FDC).")

p_actual = st.session_state.get("persona", persona)
d1, d2, d3, d4 = st.columns(4)
d1.download_button(
    "Descargar Excel",
    exportar.a_excel(menu, p_actual),
    file_name=f"menu_{p_actual.codigo}_{clave}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
    icon=":material/download:",
)
d2.download_button(
    "Excel Clínico (8 hojas)",
    office.exportar_excel_clinico(menu, p_actual, comp, meds_sel, erc_doble),
    file_name=f"dossier_{p_actual.codigo}_{clave}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    icon=":material/table_chart:",
)
d3.download_button(
    "Informe HTML",
    office.generar_informe_html(menu, p_actual, comp, meds_sel, erc_doble),
    file_name=f"dossier_{p_actual.codigo}_{clave}.html",
    mime="text/html",
    icon=":material/description:",
)
d4.download_button(
    "Informe Markdown",
    office.generar_informe_markdown(menu, p_actual, comp, meds_sel, erc_doble),
    file_name=f"dossier_{p_actual.codigo}_{clave}.md",
    mime="text/markdown",
    icon=":material/markdown:",
)
if MODO == "estudio":
    estilo.pie(st)
