# core/optimizer.py
import gurobipy as gp
from gurobipy import GRB
import pandas as pd
from pathlib import Path
from datetime import datetime
import traceback


def solve_plan(inputs_df: pd.DataFrame, params: dict) -> dict:
    """
    Optimiza el plan de producción/empacado de salmones conforme al Modelo Matemático.
    Alineado con:
      - Variable: x[p,j,e,k,c] ∈ Z_+ (cajas)
      - Objetivo: max sum_{p,j,e,k,c} q_p * r_{p,k} * x
      - Restricciones:
          R1  Disponibilidad por calibre (en salmones): sum ( ukc * x / (s_p * y_p) ) <= a_c
          R2  Compat. calibre–línea (implementada por filtrado de VARS con bcj=1)
          R3  Capacidad de línea (piezas/turno): sum ( ukc * x ) <= m_j
          R4  Compat. producto–empaque (filtrado de VARS con fpe=1)
          R5  Capacidad de empaque (piezas/turno): sum ( ukc * x ) <= n_e
          R6  Demanda por (p,k,c): sum_{j,e} x <= d_{p,k,c}
          R7  Límite total de Congelado (kg/turno): sum ( (ukc*x/s_p) * w_c * y_p / 2.20462 ) <= 22500
    """
    notes = []
    log_text = ""

    try:
        # ---------------------------
        # Sets / Conjuntos
        # ---------------------------
        # P = Productos (EXCLUSIVO). No usar 'formatos' para P.
        P = list(params.get("productos") or [])
        if not P:
            raise ValueError("Parámetro 'productos' vacío en YAML (el conjunto P debe ser Productos).")

        J = list(params.get("lineas", {}).keys())
        if not J:
            raise ValueError("Parámetro 'lineas' vacío en YAML.")

        E = list(params.get("areas_empaque") or [])
        if not E:
            raise ValueError("Parámetro 'areas_empaque' vacío en YAML.")

        K = list(params.get("formatos_caja") or [])
        if not K:
            raise ValueError("Parámetro 'formatos_caja' vacío en YAML.")

        C_map = params.get("C_map")
        if not isinstance(C_map, dict):
            C_map = {
                0: "1-2", 1: "2-3", 2: "3-4", 3: "4-5", 4: "5-6",
                5: "6-7", 6: "7-8", 7: "8-9", 8: "9-10", 9: "10-11",
                10: "11-12", 11: "12-13", 12: "13-14", 13: "14+"
            }
        C = list(sorted(int(i) for i in C_map.keys()))
        C_inv = {v: int(k) for k, v in C_map.items()}

        # ---------------------------
        # Parámetros técnicos (nombres y unidades del modelo)
        # ---------------------------
        # ukc[k][c] = piezas por caja k para calibre c  (piezas/caja)
        ukc = params.get("ukc")
        if not isinstance(ukc, dict):
            raise ValueError("Falta 'ukc' en YAML.")
        ukc = {str(k): {int(ci): int(val) for ci, val in v.items()} for k, v in ukc.items()}

        # wc[c] = peso promedio (lb/salmón) del calibre c
        wc = {int(k): float(v) for k, v in params.get("wc", {}).items()}

        # sp[p] = piezas por salmón del producto p  (piezas/salmón)
        sp = {str(k): float(v) for k, v in params.get("sp", {}).items()}

        # yp[p] = rendimiento del producto p (fracción 0..1)
        yp = {str(k): float(v) for k, v in params.get("yp", {}).items()}

        # qp[p] = prioridad del producto p (coef. del objetivo)
        qp = {str(k): float(v) for k, v in params.get("qp", {}).items()}

        # rpk[p][k] = precio por caja del producto p en formato k
        rpk = params.get("rpk")
        if not (isinstance(rpk, dict) and all(isinstance(v, dict) for v in rpk.values())):
            raise ValueError("Falta 'rpk' en YAML o formato inválido.")
        rpk = {str(p): {str(k): float(val) for k, val in kv.items()} for p, kv in rpk.items()}

        # m_j = capacidad de línea j (piezas/turno)
        mj = params.get("mj")
        if not isinstance(mj, dict) or not mj:
            raise ValueError("Falta 'mj' (capacidad de líneas) en YAML.")
        mj = {str(j): float(v) for j, v in mj.items()}

        # n_e = capacidad de empaque e (piezas/turno)
        ne = params.get("ne")
        if not isinstance(ne, dict) or not ne:
            raise ValueError("Falta 'ne' (capacidad de empaque por área) en YAML.")
        ne = {str(e): float(v) for e, v in ne.items()}

        # Compatibilidad calibre–línea: bcj[(c,j)] ∈ {0,1}
        bcj_map = {}
        if "bcj" in params and isinstance(params["bcj"], dict):
            for key, val in params["bcj"].items():
                if isinstance(key, (list, tuple)) and len(key) == 2:
                    c, j = key
                elif isinstance(key, str) and "," in key:
                    c_str, j = key.split(",", 1)
                    c = int(c_str)
                else:
                    continue
                bcj_map[(int(c), str(j))] = int(val)
        elif "compatibilidad_indices" in params and isinstance(params["compatibilidad_indices"], dict):
            for j, c_list in params["compatibilidad_indices"].items():
                for c in c_list:
                    bcj_map[(int(c), str(j))] = 1
        elif "compatibilidad" in params and isinstance(params["compatibilidad"], dict):
            # compatibilidad por etiquetas de calibre (p.ej., "10-11")
            for j, labels in params["compatibilidad"].items():
                for lab in labels:
                    if lab in C_inv:
                        bcj_map[(int(C_inv[lab]), str(j))] = 1
        else:
            raise ValueError("Falta compatibilidad de líneas (bcj / compatibilidad_indices / compatibilidad).")

        # Compatibilidad producto–empaque: fpe[(p,e)] ∈ {0,1}
        compat_empaque = params.get("compatibilidad_empaque", {})
        fpe = {(p, e): (1 if e in set(compat_empaque.get(p, [])) else 0) for p in P for e in E}

        # ---------------------------
        # Disponibilidad por calibre a_c (salmones)
        # ---------------------------
        # Por defecto, desde YAML (en salmones):
        ac_yaml = {int(c): int(v) for c, v in params.get("ac", {}).items()} if "ac" in params else {c: 0 for c in C}
        ac = dict(ac_yaml)

        # Override opcional SOLO si inputs_df trae columna 'salmones'. Si trae 'piezas', se ignora para mantener unidades del modelo.
        if inputs_df is not None and not inputs_df.empty:
            cols = [c.strip().lower() for c in inputs_df.columns]
            if "calibre" in cols and "salmones" in cols:
                df = inputs_df.copy()
                df.columns = cols
                df["calibre"] = df["calibre"].astype(str).str.strip()
                df["salmones"] = pd.to_numeric(df["salmones"], errors="coerce").fillna(0).astype(int)
                agg = df.groupby("calibre", as_index=False)["salmones"].sum()
                C_inv_local = {str(v): int(k) for k, v in C_map.items()}
                for _, row in agg.iterrows():
                    lab = str(row["calibre"])
                    if lab in C_inv_local:
                        ac[C_inv_local[lab]] = int(row["salmones"])
            elif "calibre" in cols and "piezas" in cols:
                notes.append("Advertencia: 'inputs_df' trae 'piezas' pero 'ac' (disponibilidad) es en salmones; se ignora el override para mantener unidades del modelo.")

        # ---------------------------
        # Demanda detallada d_{p,k,c} (opcional)
        # ---------------------------
        dpkc = None
        if "dpkc" in params and isinstance(params["dpkc"], dict):
            dpkc = {}
            for key, val in params["dpkc"].items():
                if isinstance(key, (list, tuple)) and len(key) == 3:
                    p, k, c = key
                    dpkc[(str(p), str(k), int(c))] = float(val)
                elif isinstance(key, str):
                    parts = key.replace(",", "|").split("|")
                    if len(parts) == 3:
                        p, k, c = parts[0].strip(), parts[1].strip(), int(parts[2])
                        dpkc[(p, k, c)] = float(val)

        # ---------------------------
        # Modelo
        # ---------------------------
        m = gp.Model("salmon_planner")
        m.Params.OutputFlag = 0
        m.Params.LogToConsole = 0
        m.Params.LogFile = ""

        # Pre-filtrado de combinaciones (equivalente a Big-M/N del modelo para bcj y fpe)
        VARS = []
        for p in P:
            for j in J:
                for e in E:
                    if fpe.get((p, e), 0) != 1:
                        continue  # incompatibilidad producto–empaque (R4) como filtro duro
                    for k in K:
                        kstr = str(k)
                        if kstr not in ukc:
                            continue
                        for c in C:
                            if ukc[kstr].get(c, 0) <= 0:
                                continue
                            if bcj_map.get((c, str(j)), 0) != 1:
                                continue  # incompatibilidad calibre–línea (R2) como filtro duro
                            VARS.append((p, j, e, k, c))

        x = m.addVars(VARS, vtype=GRB.INTEGER, lb=0, name="x")

        # Objetivo: max sum qp[p]*rpk[p,k]*x[p,j,e,k,c]
        m.setObjective(
            gp.quicksum(
                qp.get(p, 1.0) * rpk.get(p, {}).get(str(k), 0.0) * x[p, j, e, k, c]
                for (p, j, e, k, c) in VARS
            ),
            GRB.MAXIMIZE
        )

        # R1: Disponibilidad por calibre (salmones) -> sum ( ukc * x / (sp[p] * yp[p]) ) <= ac[c]
        for c in C:
            m.addConstr(
                gp.quicksum(
                    ukc[str(k)].get(c, 0) * x[p, j, e, k, c] / max(1e-9, sp.get(p, 1.0) * yp.get(p, 1.0))
                    for (p, j, e, k, cc) in VARS if cc == c
                ) <= ac.get(c, 0),
                name=f"salmones_disp_{c}"
            )

        # R3: Capacidad de línea (piezas/turno) -> sum ( ukc * x ) <= m_j
        for j in J:
            m.addConstr(
                gp.quicksum(
                    ukc[str(k)].get(c, 0) * x[p, j2, e, k, c]
                    for (p, j2, e, k, c) in VARS if j2 == j
                ) <= float(mj[str(j)]),
                name=f"cap_linea_{j}"
            )

        # R5: Capacidad de empaque (piezas/turno) -> sum ( ukc * x ) <= n_e
        for e in E:
            m.addConstr(
                gp.quicksum(
                    ukc[str(k)].get(c, 0) * x[p, j, e2, k, c]
                    for (p, j, e2, k, c) in VARS if e2 == e
                ) <= float(ne[str(e)]),
                name=f"cap_empaque_{e}"
            )

        # R6: Demanda por (p,k,c), agregada en j,e  ->  sum x <= d_{p,k,c}
        if dpkc:
            for p in P:
                for k in K:
                    for c in C:
                        has_var = any(1 for (pp, jj, ee, kk, cc) in VARS if pp == p and kk == k and cc == c)
                        if not has_var:
                            continue
                        dem = float(dpkc.get((p, str(k), int(c)), 0.0))
                        m.addConstr(
                            gp.quicksum(
                                x[pp, jj, ee, kk, cc]
                                for (pp, jj, ee, kk, cc) in VARS
                                if pp == p and kk == k and cc == c
                            ) <= dem,
                            name=f"demanda_{p}_{k}_{c}"
                        )

        # R7: Límite de peso total en Congelado (kg/turno)
        # Masa (kg) = sum_{Vars en e=Congelado} (ukc*x / sp[p]) * wc[c] * yp[p] / 2.20462
        if "Congelado" in E:
            e_cong = "Congelado"
            has_cong = any(1 for (_, _, e, _, _) in VARS if e == e_cong)
            if has_cong:
                m.addConstr(
                    gp.quicksum(
                        (ukc[str(k)].get(c, 0) * x[p, j, e, k, c] / max(1e-9, sp.get(p, 1.0)))
                        * wc.get(c, 0.0) * yp.get(p, 1.0)
                        for (p, j, e, k, c) in VARS if e == e_cong
                    ) / 2.20462 <= 22500.0,
                    name="cap_total_congelado"
                )
                notes.append("R7 aplicada: límite Congelado 22,500 kg con conversión (ukc/sp)*wc*yp/2.20462.")

        # R_extra: HON solo se puede procesar en Emparrillado
        for (p, j, e, k, c) in VARS:
            if p == "HON" and str(j) != "Emparrillado":
                m.addConstr(x[p,j,e,k,c] == 0, name=f"no_fileteo_{p}_{j}_{k}_{c}")


        # Optimizar
        m.optimize()
        if m.Status not in [GRB.OPTIMAL, GRB.TIME_LIMIT]:
            notes.append(f"Modelo no convergió (status {m.Status}).")
            raise RuntimeError(f"Gurobi terminó con estado {m.Status}")

        # Resultados
        rows = []
        for (p, j, e, k, c) in VARS:
            val = x[p, j, e, k, c].X
            if val > 1e-9:
                piezas = ukc[str(k)].get(c, 0) * val
                rows.append({
                    "linea": str(j),
                    "empaque": str(e),
                    "producto": str(p),
                    "formato_caja": str(k),
                    "calibre": C_map.get(int(c), str(c)),
                    "cajas": float(val),
                    "piezas": float(piezas),
                })

        plan_df = pd.DataFrame(rows, columns=["linea", "empaque", "producto", "formato_caja", "calibre", "cajas", "piezas"])
        if plan_df.empty:
            notes.append("Sin resultados válidos (todas las variables en cero).")
            return {"plan_df": plan_df, "notes": notes}

        notes.append(f"Optimización finalizada. Valor objetivo = {m.ObjVal:,.2f}")
        return {"plan_df": plan_df, "notes": notes}

    except Exception as e:
        log_text += f"\n[ERROR] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        log_text += traceback.format_exc()
        log_dir = Path("logs"); log_dir.mkdir(exist_ok=True)
        log_path = log_dir / f"error_gurobi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(log_text)
        notes.append(f"Ocurrió un error durante la optimización. Se guardó log en {log_path.name}.")
        return {
            "plan_df": pd.DataFrame(columns=["linea", "empaque", "producto", "formato_caja", "calibre", "cajas", "piezas"]),
            "notes": notes
        }
