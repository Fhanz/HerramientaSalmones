import os
import pandas as pd
import plotly.io as pio
import PySimpleGUI as sg

def export_excel(outputs: dict, path: str) -> str:
    plan_df = outputs.get("plan_df", pd.DataFrame())
    kpis_text = outputs.get("kpis_text", "")
    notes = outputs.get("notes", [])

    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        # Hoja de planificación
        plan_df.to_excel(xw, sheet_name="Planificacion", index=False)

        # Hoja de KPIs
        kpi_lines = (kpis_text or "").splitlines()
        pd.DataFrame({"KPIs": kpi_lines}).to_excel(xw, sheet_name="KPIs", index=False)

        # Hoja de notas (si existieran)
        if notes:
            pd.DataFrame({"Notas": notes}).to_excel(xw, sheet_name="Notas", index=False)

    return os.path.abspath(path)

def export_pngs(figs: dict, outdir: str) -> list[str]:
    os.makedirs(outdir, exist_ok=True)
    exported = []
    for name, fig in (figs or {}).items():
        try:
            outpath = os.path.join(outdir, f"{name}.png")
            pio.write_image(fig, outpath, scale=2)
            exported.append(outpath)
        except Exception as e:
            # Si ocurre un error al exportar (ej. falta kaleido o problema con PyInstaller),
            # mostramos un popup indicando qué gráfico no se pudo exportar y el motivo.
            sg.popup_error(f"No se pudo exportar el gráfico '{name}': {e}")
    return exported
