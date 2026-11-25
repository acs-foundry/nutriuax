"""Tests de conversión crudo ↔ cocinado, retención y doble cocción ERC (T16)."""
import pandas as pd
import pytest

from nutriuax import base_fdc, coccion, composicion, generador, objetivos


def test_crudo_cocinado_ida_y_vuelta():
    g_ck = coccion.crudo_a_cocinado(100.0, "arroz", "hervido")
    assert g_ck == pytest.approx(280.0, rel=0.02)
    assert coccion.cocinado_a_crudo(g_ck, "arroz", "hervido") == pytest.approx(100.0, rel=0.02)
    assert coccion.crudo_a_cocinado(150.0, "ave", "plancha") < 150.0


def test_enriquecer_menu_respeta_referencia_ya_cocinada():
    comp = composicion.cargar()
    p = objetivos.Persona(kcal_manual=2000)
    obj = objetivos.calcular_objetivos(p, objetivos.PERFILES["uax_mediterranea"])
    menu = generador.generar(comp, obj, dias=1, semilla=0, tiempo_max=15)
    enr = coccion.enriquecer_menu_coccion(menu.items, comp)
    assert {"gramos_crudo", "gramos_cocinado", "tecnica", "referencia_fdc"} <= set(enr.columns)

    # Si aparece arroz_blanco (ya cocido en FDC), crudo debe ser MENOR que cocinado
    arroz = enr[enr["id"] == "arroz_blanco"]
    if not arroz.empty:
        assert (arroz["gramos_crudo"] < arroz["gramos_cocinado"]).all()
    # Si aparece pollo_pechuga (ya a la plancha en FDC), crudo debe ser MAYOR que cocinado
    pollo = enr[enr["id"] == "pollo_pechuga"]
    if not pollo.empty:
        assert (pollo["gramos_crudo"] > pollo["gramos_cocinado"]).all()


def test_doble_coccion_erc_reduce_potasio():
    comp = composicion.cargar()
    df_norm = pd.DataFrame([{"id": "patata", "nombre": "Patata cocida", "gramos": 200.0, "estado": "cocinado", "tecnica": "hervido"}])
    df_erc = pd.DataFrame([{"id": "patata", "nombre": "Patata cocida", "gramos": 200.0, "estado": "cocinado", "tecnica": "doble_coccion_erc"}])
    r_norm = coccion.calcular_con_coccion(comp, df_norm)
    r_erc = coccion.calcular_con_coccion(comp, df_erc)
    assert r_erc["potasio"].iloc[0] < r_norm["potasio"].iloc[0] * 0.75


def test_control_crudo_por_rendimiento_frente_a_fdc_cocinado():
    """T16: crudo × rendimiento frente a FDC cocinado difiere de forma acotada en proteína y BCAA."""
    fdc = base_fdc.cargar_completa()
    if fdc is None:
        pytest.skip("sin data/fdc_completa.csv.gz")
    # Pares (grupo_coccion, tecnica, ndb_crudo, ndb_cocinado) de USDA SR Legacy
    pares = [
        ("arroz", "hervido", "20044", "20045"),
        ("pasta", "hervido", "20120", "20121"),
        ("legumbre", "hervido", "16069", "16070"),
        ("legumbre", "hervido", "16056", "16057"),
        ("ave", "plancha", "05062", "05064"),
        ("pescado", "horno", "15015", "15016"),
    ]
    for grp, tec, ndb_raw, ndb_ck in pares:
        if ndb_raw not in fdc.index or ndb_ck not in fdc.index:
            continue
        fac = coccion.obtener_factor(grp, tec)
        # 100 g crudo → 100 * rendimiento g cocinado
        raw_row = fdc.loc[ndb_raw]
        ck_row = fdc.loc[ndb_ck]
        prot_est = float(raw_row["proteina"]) * fac.retencion_proteina
        prot_fdc = float(ck_row["proteina"]) * fac.rendimiento_peso
        rel_diff_p = abs(prot_est - prot_fdc) / max(prot_fdc, 1e-6)
        assert rel_diff_p < 0.25, f"{grp}/{tec}: prot_est={prot_est:.1f} vs fdc={prot_fdc:.1f}"
        for aa in ("leu", "ile", "val"):
            if pd.notna(raw_row[aa]) and pd.notna(ck_row[aa]) and float(ck_row[aa]) > 0:
                aa_est = float(raw_row[aa]) * fac.retencion_proteina
                aa_fdc = float(ck_row[aa]) * fac.rendimiento_peso
                rel_diff_aa = abs(aa_est - aa_fdc) / max(aa_fdc, 1e-6)
                assert rel_diff_aa < 0.25, f"{grp}/{aa}: est={aa_est:.0f} vs fdc={aa_fdc:.0f}"
