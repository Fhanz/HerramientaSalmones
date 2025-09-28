import pandas as pd
from itertools import cycle

def _build_product_cycle(params: dict):
    # Si hay pesos_producto en el YAML, repetimos cada producto según su peso (enteros)
    pesos = params.get("pesos_producto")
    prods = list(params["formatos"])
    if pesos and isinstance(pesos, dict):
        pool = []
        for p in prods:
            w = int(pesos.get(p, 0))
            if w > 0:
                pool.extend([p] * w)
        if pool:
            return cycle(pool)
    # Fallback: round-robin simple
    return cycle(prods)

def solve_plan(inputs_df: pd.DataFrame, params: dict) -> dict:
    """
    Retorna plan_df con:
    linea | empaque | producto | formato_caja | calibre | cajas | piezas
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

    # Mapa opcional formato por producto (si no existe, se usa el primero de formatos_caja)
    formato_por_producto = params.get("formato_por_producto", {})
    formato_caja_default = params.get("formatos_caja", ["10lb"])[0]

    prod_cycle = _build_product_cycle(params)

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

            # Elegimos producto en round-robin hasta caer en uno que sea compatible con empaque
            # y definimos el empaque según preferencias y compatibilidad
            intentos = 0
            producto = None
            empaque = None
            while intentos < len(productos):
                candidato = next(prod_cycle)
                permitidas = set(compat_emp.get(candidato, areas_pref))
                elegido = next((a for a in areas_pref if a in permitidas), None)
                if elegido is not None:
                    producto = candidato
                    empaque = elegido
                    break
                intentos += 1
            if producto is None or empaque is None:
                continue

            formato_caja = formato_por_producto.get(producto, formato_caja_default)

            asignaciones.append((l, empaque, producto, formato_caja, calibre, asignable))
            uso_linea[l] += asignable
            empaque_usado += asignable

    cols = ["linea","empaque","producto","formato_caja","calibre","piezas"]
    plan_df = pd.DataFrame(asignaciones, columns=cols) if asignaciones else pd.DataFrame(columns=cols)

    if plan_df.empty:
        plan_df["cajas"] = []
        return {"plan_df": plan_df, "usage": {l: 0.0 for l in lineas}, "notes": ["Sin asignaciones"]}

    piezas_por_caja = params["piezas_por_caja"]
    plan_df["cajas"] = plan_df.apply(
        lambda r: max(0, r["piezas"] // max(1, piezas_por_caja.get(r["producto"], 1))),
        axis=1
    )

    uso_pct = {l: (100.0 * uso_linea[l] / max(1, cap_linea[l])) for l in lineas}
    plan_df = plan_df.sort_values(["linea","producto","calibre"]).reset_index(drop=True)

    return {"plan_df": plan_df, "usage": {l: round(v, 1) for l, v in uso_pct.items()}, "notes": []}
