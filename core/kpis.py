def build_kpis_text(outputs: dict, params: dict) -> str:
    usage = outputs.get("usage", {})
    plan_df = outputs.get("plan_df")

    prom_uso = sum(usage.values()) / max(1, len(usage))
    total_piezas = int(plan_df["piezas"].sum()) if plan_df is not None and not plan_df.empty else 0
    total_cajas = int(plan_df["cajas"].sum()) if plan_df is not None and not plan_df.empty else 0

    txt = []
    txt.append(f"Total piezas planificadas: {total_piezas}")
    txt.append(f"Total cajas planificadas: {total_cajas}")
    txt.append(f"Uso promedio de líneas: {prom_uso:.1f}%")
    for l, u in usage.items():
        txt.append(f"- {l}: {u:.1f}%")

    return "\n".join(txt)
