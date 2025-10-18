# exporters.py
import os
from pathlib import Path
import pandas as pd
import plotly.io as pio
import PySimpleGUI as sg


def _safe_to_excel(writer: pd.ExcelWriter, df: pd.DataFrame, sheet: str) -> None:
    """Escribe un DataFrame a Excel siempre con columnas aunque esté vacío."""
    if df is None:
        df = pd.DataFrame()
    # Evita escribir índices y fuerza DataFrame aunque sea vacío
    (df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame(df)).to_excel(
        writer, sheet_name=sheet, index=False
    )


def _make_resumen(plan_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Construye tablas de resumen a partir de plan_df sin requerir params:
      - por línea
      - por empaque
      - por producto
      - por formato de caja
      - por calibre
    Cada tabla incluye totales de piezas y cajas.
    """
    if plan_df is None or plan_df.empty:
        empty = pd.DataFrame(columns=["clave", "N° de piezas", "N° de cajas"])
        return {
            "por_linea": empty.copy(),
            "por_empaque": empty.copy(),
            "por_producto": empty.copy(),
            "por_formato": empty.copy(),
            "por_calibre": empty.copy(),
        }

    def agg(df: pd.DataFrame, key: str, label: str) -> pd.DataFrame:
        g = (df.groupby(key, dropna=False)[["piezas", "cajas"]]
               .sum()
               .reset_index()
               .rename(columns={
                   key: label,
                   "piezas": "N° de piezas",
                   "cajas": "N° de cajas",
               }))
        # Ordena por piezas desc
        return g.sort_values(by="N° de piezas", ascending=False, ignore_index=True)

    resumen = {
        "por_linea":    agg(plan_df, "linea", "Línea"),
        "por_empaque":  agg(plan_df, "empaque", "Empaque"),
        "por_producto": agg(plan_df, "producto", "Producto"),
        "por_formato":  agg(plan_df, "formato_caja", "Formato caja"),
        "por_calibre":  agg(plan_df, "calibre", "Calibre"),
    }
    return resumen


def export_excel(outputs: dict, path: str) -> str:
    """
    Genera un Excel con:
      - Planificacion (detalle fila a fila)
      - Resumen (agregados por línea, empaque, producto, formato, calibre)
      - KPIs (texto)
      - Notas (si existen)
      - (opcional) Uso lineas (si viene en outputs['usage'])
    """
    plan_df = outputs.get("plan_df", pd.DataFrame())
    kpis_text = outputs.get("kpis_text", "")
    notes = outputs.get("notes", [])
    usage = outputs.get("usage", {}) or {}

    # Asegura extensión .xlsx
    path = str(path)
    if not path.lower().endswith(".xlsx"):
        path += ".xlsx"

    # Construye resúmenes
    resumen = _make_resumen(plan_df)

    # Escribir
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        # 1) Hoja de planificación (detalle)
        _safe_to_excel(xw, plan_df, "Planificacion")

        # 2) Hoja Resumen (varias sub-hojas)
        for name, df in resumen.items():
            sheet_name = f"Resumen_{name.replace('por_','')}"
            _safe_to_excel(xw, df, sheet_name)

        # 3) Hoja de KPIs (texto)
        kpi_lines = (kpis_text or "").splitlines()
        kpi_df = pd.DataFrame({"KPIs": kpi_lines})
        _safe_to_excel(xw, kpi_df, "KPIs")

        # 4) Hoja de uso de líneas (si nos pasaron 'usage')
        if usage:
            usage_df = (pd.DataFrame(list(usage.items()), columns=["Línea", "Uso %"])
                        .sort_values(by="Línea"))
            _safe_to_excel(xw, usage_df, "Uso_lineas")

        # 5) Hoja de notas (si existieran)
        if notes:
            notas_df = pd.DataFrame({"Notas": notes})
            _safe_to_excel(xw, notas_df, "Notas")

    return os.path.abspath(path)


def export_pngs(figs: dict, outdir: str) -> list[str]:
    """
    Exporta figuras Plotly a PNG usando kaleido.
    Si kaleido no está disponible o falla, muestra un popup por cada gráfico problemático.
    """
    os.makedirs(outdir, exist_ok=True)
    exported: list[str] = []
    for name, fig in (figs or {}).items():
        try:
            outpath = os.path.join(outdir, f"{name}.png")
            # scale=2 para mejor nitidez en informes
            pio.write_image(fig, outpath, scale=2)
            exported.append(outpath)
        except Exception as e:
            # Falla típica: RuntimeError: Image export using the "kaleido" engine requires the kaleido package,
            # solución: pip install -U kaleido
            sg.popup_error(f"No se pudo exportar el gráfico '{name}': {e}")
    return exported
