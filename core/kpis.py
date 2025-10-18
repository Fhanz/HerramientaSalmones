import pandas as pd

def build_kpis_text(outputs: dict, params: dict) -> str:
    """
    Genera un resumen de KPIs alineado con el modelo matemático:
      - Total de piezas planificadas
      - Estimación de salmones utilizados
      - Masa enviada a Congelado (kg)
      - Uso promedio y por línea (%)
    """
    plan_df: pd.DataFrame = outputs.get("plan_df")
    usage = outputs.get("usage", {}) or {}

    # ---------------------------
    # Si no hay resultados
    # ---------------------------
    if plan_df is None or plan_df.empty:
        return "Sin resultados válidos (todas las variables en cero)."

    # ---------------------------
    # Datos base
    # ---------------------------
    ukc = params.get("ukc", {})
    sp = params.get("sp", {})
    yp = params.get("yp", {})
    wc = params.get("wc", {})
    mj = params.get("mj", {})
    C_map = params.get("C_map", {})
    C_inv = {v: k for k, v in C_map.items()}

    # ---------------------------
    # Totales globales
    # ---------------------------
    total_piezas = plan_df["piezas"].sum()
    total_cajas = plan_df["cajas"].sum()

    # Estimar salmones utilizados: sum (ukc * cajas / (sp * yp))
    salmones_total = 0.0
    for _, row in plan_df.iterrows():
        p, k, c_label = row["producto"], row["formato_caja"], row["calibre"]
        c_idx = C_inv.get(str(c_label), None)
        if c_idx is None:
            continue
        piezas_por_caja = ukc.get(str(k), {}).get(int(c_idx), 0)
        salmones_total += (piezas_por_caja * row["cajas"]) / max(1e-9, sp.get(str(p), 1.0) * yp.get(str(p), 1.0))

    # Estimar masa total a Congelado (kg)
    masa_congelado = 0.0
    if "Congelado" in plan_df["empaque"].unique():
        df_cong = plan_df[plan_df["empaque"] == "Congelado"]
        for _, row in df_cong.iterrows():
            p, k, c_label = row["producto"], row["formato_caja"], row["calibre"]
            c_idx = C_inv.get(str(c_label), None)
            if c_idx is None:
                continue
            piezas_por_caja = ukc.get(str(k), {}).get(int(c_idx), 0)
            masa_congelado += (
                (piezas_por_caja * row["cajas"] / max(1e-9, sp.get(str(p), 1.0)))
                * wc.get(int(c_idx), 0.0) * yp.get(str(p), 1.0)
            ) / 2.20462  # lb -> kg

    # ---------------------------
    # Uso de líneas (%)
    # ---------------------------
    if not usage:
        usage = {}
        for linea, cap in mj.items():
            piezas_linea = plan_df.loc[plan_df["linea"] == str(linea), "piezas"].sum()
            uso_pct = 100 * piezas_linea / max(1e-9, cap)
            usage[str(linea)] = uso_pct

    prom_uso = sum(usage.values()) / max(1, len(usage))

    # ---------------------------
    # Construcción del texto
    # ---------------------------
    txt = []
    txt.append(f"KPIs (Key Performance Indicators) del plan:")
    txt.append(f"Total de piezas planificadas: {int(total_piezas):,}")
    txt.append(f"Total de cajas planificadas: {int(total_cajas):,}")
    txt.append(f"Estimación de salmones utilizados: {salmones_total:,.0f}")
    txt.append(f"Masa total enviada a Congelado: {masa_congelado:,.1f} kg")
    txt.append(f"Uso promedio de líneas: {prom_uso:.1f}%")
    for l, u in usage.items():
        txt.append(f"- Línea {l}: {u:.1f}%")
    return "\n".join(txt)
