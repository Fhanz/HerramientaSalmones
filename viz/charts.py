# viz/charts.py
import plotly.express as px
import pandas as pd

def _fmt_thousands(fig, ycol="piezas"):
    """Aplica formato de miles al eje Y y a las etiquetas de texto."""
    fig.update_traces(texttemplate="%{y:,.0f}", textposition="outside", cliponaxis=False)
    fig.update_yaxes(tickformat=",")
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))
    return fig


def _agg(df: pd.DataFrame, group_cols, sum_cols=("piezas", "cajas")):
    g = (df.groupby(group_cols, dropna=False)[list(sum_cols)]
           .sum()
           .reset_index())
    return g


def _congelado_kg_by_product(plan_df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    Calcula kg enviados a Congelado por producto usando:
      kg = sum( (ukc[k,c]*cajas/sp[p]) * wc[c] * yp[p] ) / 2.20462
    """
    if plan_df is None or plan_df.empty or "Congelado" not in plan_df["empaque"].unique():
        return pd.DataFrame(columns=["producto", "kg_congelado"])

    ukc = params.get("ukc", {})
    sp = params.get("sp", {})
    yp = params.get("yp", {})
    wc = params.get("wc", {})
    C_map = params.get("C_map", {})
    C_inv = {v: k for k, v in C_map.items()} if C_map else {}

    dfc = plan_df[plan_df["empaque"] == "Congelado"].copy()
    dfc["c_idx"] = dfc["calibre"].astype(str).map(C_inv) if C_inv else None

    kg_vals = []
    for _, r in dfc.iterrows():
        p = str(r["producto"])
        k = str(r["formato_caja"])
        c = r["c_idx"]
        if c is None:
            # si el calibre ya viene como índice numérico en "calibre"
            try:
                c = int(r["calibre"])
            except Exception:
                c = None
        if c is None:
            continue
        piezas_por_caja = ukc.get(k, {}).get(int(c), 0)
        if piezas_por_caja <= 0:
            continue
        kg = ((piezas_por_caja * float(r["cajas"])) / max(1e-9, float(sp.get(p, 1.0)))) \
             * float(wc.get(int(c), 0.0)) * float(yp.get(p, 1.0))
        kg /= 2.20462
        kg_vals.append((p, kg))

    if not kg_vals:
        return pd.DataFrame(columns=["producto", "kg_congelado"])

    dfkg = pd.DataFrame(kg_vals, columns=["producto", "kg_congelado"])
    dfkg = dfkg.groupby("producto", as_index=False)["kg_congelado"].sum()
    return dfkg.sort_values("kg_congelado", ascending=False, ignore_index=True)


def make_figures(outputs: dict, params: dict) -> dict:
    """
    Devuelve un dict de figuras Plotly Express. Claves:
      - barras_producto           (piezas por producto)
      - apilado_linea             (piezas por línea y producto)
      - apilado_empaque           (piezas por empaque y producto)
      - cajas_por_formato         (cajas por formato)
      - piezas_por_calibre        (piezas por calibre)
      - congelado_kg_por_producto (kg a Congelado por producto, si aplica)
    """
    figs = {}
    df = outputs.get("plan_df")
    if df is None or df.empty:
        return figs

    # columnas mínimas requeridas
    needed = {"linea", "producto", "piezas"}
    if not needed.issubset(df.columns):
        return figs

    # 1) Barras por producto (piezas)
    by_prod = (
        df.groupby("producto", as_index=False)["piezas"]
          .sum()
          .sort_values("piezas", ascending=False)
    )
    if not by_prod.empty:
        fig1 = px.bar(by_prod, x="producto", y="piezas",
                      title="Piezas por producto", text="piezas")
        figs["barras_producto"] = _fmt_thousands(fig1)

    # 2) Apilado por línea (producto como color)
    by_line_prod = (
        df.groupby(["linea", "producto"], as_index=False)["piezas"]
          .sum()
          .sort_values(["linea", "piezas"], ascending=[True, False])
    )
    if not by_line_prod.empty:
        fig2 = px.bar(by_line_prod, x="linea", y="piezas", color="producto",
                      title="Distribución por línea (apilado)")
        fig2.update_layout(barmode="stack")
        figs["apilado_linea"] = _fmt_thousands(fig2)

    # 3) Apilado por empaque (producto como color), si existe la columna
    if "empaque" in df.columns:
        by_emp_prod = (
            df.groupby(["empaque", "producto"], as_index=False)["piezas"]
              .sum()
              .sort_values(["empaque", "piezas"], ascending=[True, False])
        )
        if not by_emp_prod.empty:
            fig3 = px.bar(by_emp_prod, x="empaque", y="piezas", color="producto",
                          title="Distribución por empaque (apilado)")
            fig3.update_layout(barmode="stack")
            figs["apilado_empaque"] = _fmt_thousands(fig3)

    # 4) Cajas por formato (si hay columna formato_caja)
    if "formato_caja" in df.columns and "cajas" in df.columns:
        by_fmt = (
            df.groupby("formato_caja", as_index=False)["cajas"]
              .sum()
              .sort_values("cajas", ascending=False)
        )
        if not by_fmt.empty:
            fig4 = px.bar(by_fmt, x="formato_caja", y="cajas",
                          title="Cajas por formato", text="cajas")
            fig4.update_traces(texttemplate="%{y:,.0f}", textposition="outside", cliponaxis=False)
            fig4.update_yaxes(tickformat=",")
            fig4.update_layout(margin=dict(l=20, r=20, t=50, b=20))
            figs["cajas_por_formato"] = fig4

    # 5) Piezas por calibre (usa etiqueta del DF; si son índices, igual funciona)
    if "calibre" in df.columns:
        by_cal = (
            df.groupby("calibre", as_index=False)["piezas"]
              .sum()
              .sort_values("piezas", ascending=False)
        )
        if not by_cal.empty:
            fig5 = px.bar(by_cal, x="calibre", y="piezas",
                          title="Piezas por calibre", text="piezas")
            figs["piezas_por_calibre"] = _fmt_thousands(fig5)

    # 6) Kg a Congelado por producto (si aplica y hay params suficientes)
    try:
        dfkg = _congelado_kg_by_product(df, params)
        if not dfkg.empty:
            fig6 = px.bar(dfkg, x="producto", y="kg_congelado",
                          title="Kg a Congelado por producto", text="kg_congelado")
            fig6.update_traces(texttemplate="%{y:,.1f}", textposition="outside", cliponaxis=False)
            fig6.update_yaxes(tickformat=",")
            fig6.update_layout(margin=dict(l=20, r=20, t=50, b=20))
            figs["congelado_kg_por_producto"] = fig6
    except Exception:
        # Si faltan parámetros o hay un problema, simplemente no generamos esta figura.
        pass

    return figs
