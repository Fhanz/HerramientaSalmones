import pandas as pd

def solve_plan(inputs_df: pd.DataFrame, params: dict) -> dict:
    """
    Devuelve plan_df con columnas:
    linea | empaque | producto | formato_caja | calibre | cajas | piezas
    y 'usage' con % de uso por línea (para KPIs).
    """
    lineas = list(params["lineas"].keys())
    productos = params["formatos"]
    compat_linea = params["compatibilidad"]
    compat_emp = params.get("compatibilidad_empaque", {})
    areas_pref = params.get("areas_empaque", ["Área 4", "Fresco", "Congelado"])
    h_tot = params["turnos"] * params["horas_por_turno"]

    cap_linea = {l: params["lineas"][l]["capacidad_piezas_h"] * h_tot for l in lineas}
    min_pzs_por_caja = max(1, min(params["piezas_por_caja"].values()))
    cap_empaque_piezas = params["capacidad_empaque_cajas_h"] * h_tot * min_pzs_por_caja

    formato_caja_def = params.get("formatos_caja", ["10lb"])[0]

    asignaciones = []
    uso_linea = {l: 0 for l in lineas}
    empaque_usado = 0

    for _, row in inputs_df.iterrows():
        calibre = str(row["calibre"])
        piezas = int(row["piezas"])
        if piezas <= 0:
            continue

        compatibles = [l for l in lineas if calibre in compat_linea.get(l, [])]
        if not compatibles:
            continue

        libres = {l: max(0, cap_linea[l] - uso_linea[l]) for l in compatibles}
        total_libre = sum(libres.values())
        if total_libre <= 0:
            continue

        for l in compatibles:
            cuota = int(piezas * (libres[l] / total_libre)) if total_libre > 0 else 0
            if cuota <= 0:
                continue

            libre_empaque = max(0, cap_empaque_piezas - empaque_usado)
            asignable = min(cuota, libres[l], libre_empaque)
            if asignable <= 0:
                continue

            producto = productos[0]  # MVP: primer producto; luego podrás decidir producto por regla
            # Elegir área de empaque compatible según prioridad de areas_pref
            allowed = set(compat_emp.get(producto, areas_pref))
            empaque = next((a for a in areas_pref if a in allowed), None)
            if empaque is None:
                # Si no hay área compatible, saltamos esta asignación
                continue

            asignaciones.append((l, empaque, producto, formato_caja_def, calibre, asignable))
            uso_linea[l] += asignable
            empaque_usado += asignable

    cols = ["linea","empaque","producto","formato_caja","calibre","piezas"]
    plan_df = pd.DataFrame(asignaciones, columns=cols) if asignaciones else pd.DataFrame(columns=cols)

    if plan_df.empty:
        plan_df["cajas"] = []
        return {
            "plan_df": plan_df,
            "usage": {l: 0.0 for l in lineas},
            "notes": ["Sin asignaciones"]
        }

    piezas_por_caja = params["piezas_por_caja"]

    def calc_cajas(r):
        pxc = piezas_por_caja.get(r["producto"])
        if not pxc or pxc <= 0:
            raise ValueError(f"piezas_por_caja inválido para producto '{r['producto']}'.")
        return max(0, r["piezas"] // pxc)

    plan_df["cajas"] = plan_df.apply(calc_cajas, axis=1)

    uso_pct = {l: (100.0 * uso_linea[l] / max(1, cap_linea[l])) for l in lineas}
    plan_df = plan_df.sort_values(["linea","producto","calibre"]).reset_index(drop=True)

    return {
        "plan_df": plan_df,
        "usage": {l: round(v, 1) for l, v in uso_pct.items()},
        "notes": []
    }
