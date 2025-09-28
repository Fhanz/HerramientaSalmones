import plotly.express as px
import pandas as pd

def make_figures(outputs: dict, params: dict) -> dict:
    figs = {}
    df = outputs.get("plan_df")
    if df is None or df.empty:
        return figs

    # Asegurar que estén las columnas mínimas
    needed = {"linea", "producto", "piezas"}
    if not needed.issubset(df.columns):
        return figs

    # 1) Barras por producto (agrupado y ordenado)
    by_prod = (
        df.groupby("producto", as_index=False)["piezas"]
          .sum()
          .sort_values("piezas", ascending=False)
    )
    figs["barras_producto"] = px.bar(
        by_prod, x="producto", y="piezas", title="Piezas por producto",
        text="piezas"
    )

    # 2) Apilado por línea (producto como color)
    by_line_prod = (
        df.groupby(["linea","producto"], as_index=False)["piezas"]
          .sum()
          .sort_values(["linea","piezas"], ascending=[True, False])
    )
    figs["apilado_linea"] = px.bar(
        by_line_prod, x="linea", y="piezas", color="producto",
        title="Distribución por línea (apilado)"
    )

    # 3) Pastel global (mix por producto)
    figs["pastel_global"] = px.pie(
        by_prod, names="producto", values="piezas", title="Mix de productos"
    )

    for f in figs.values():
        f.update_layout(margin=dict(l=20, r=20, t=50, b=20))

    return figs
