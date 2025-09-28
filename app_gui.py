import os, sys, traceback
import PySimpleGUI as sg
from dataio.loaders import load_inputs, load_params
from core.optimizer import solve_plan
from core.kpis import build_kpis_text
from dataio.exporters import export_excel, export_pngs
from viz.charts import make_figures

APP_TITLE = "Salmon Planner (v1.0)"

def resource_path(rel_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, rel_path)

def pipeline(csv_path: str, yaml_path: str):
    inputs = load_inputs(csv_path)
    params = load_params(yaml_path)
    outputs = solve_plan(inputs, params)
    kpis_text = build_kpis_text(outputs, params)
    figs = make_figures(outputs, params)
    return {
        "plan_df": outputs["plan_df"],
        "kpis_text": kpis_text,
        "figs": figs,
        "notes": outputs.get("notes", [])
    }

sg.theme("SystemDefault")
layout = [
    [sg.Text("Calibres CSV"), sg.Input(key="-CSV-", expand_x=True), sg.FileBrowse("Buscar")],
    [sg.Text("Parámetros YAML"), sg.Input(key="-YAML-", expand_x=True), sg.FileBrowse("Buscar")],
    [sg.Button("Optimizar", key="-RUN-"), sg.Push(),
     sg.Button("Exportar Excel", key="-XLS-"), sg.Button("Exportar Gráficos", key="-PNG-")],
    [sg.Text("KPIs:"), sg.Multiline(key="-KPIS-", size=(80,8), disabled=True, autoscroll=False, no_scrollbar=True)],
    [sg.Table(
        values=[],
        headings=["línea","empaque","producto","formato caja","calibre","n° de cajas","n° de piezas"],
        key="-TAB-",
        auto_size_columns=True, expand_x=True, expand_y=True, num_rows=12
    )]
]

try:
    window = sg.Window(APP_TITLE, layout, icon=resource_path("assets/icon.ico"), resizable=True, finalize=True)
except Exception:
    window = sg.Window(APP_TITLE, layout, resizable=True, finalize=True)

last_outputs = None

def set_busy(is_busy: bool):
    window["-RUN-"].update(disabled=is_busy)
    window["-XLS-"].update(disabled=is_busy)
    window["-PNG-"].update(disabled=is_busy)

while True:
    ev, vals = window.read()
    if ev in (sg.WINDOW_CLOSED, "Exit"):
        break

    if ev == "-RUN-":
        if not vals["-CSV-"] or not vals["-YAML-"]:
            sg.popup("Selecciona el CSV y el YAML antes de optimizar.")
            continue
        set_busy(True)
        window["-KPIS-"].update("Ejecutando optimización...\n")
        window.perform_long_operation(lambda: pipeline(vals["-CSV-"], vals["-YAML-"]), "-DONE-")

    elif ev == "-DONE-":
        try:
            result = vals["-DONE-"]
            last_outputs = result

            window["-KPIS-"].update(result["kpis_text"])

            plan_df = result["plan_df"]
            if plan_df is not None and not plan_df.empty:
                cols = ["linea","empaque","producto","formato_caja","calibre","cajas","piezas"]
                rows = plan_df[cols].values.tolist()
            else:
                rows = []
            window["-TAB-"].update(values=rows)
        except Exception as e:
            traceback.print_exc()
            sg.popup_error(f"Error al procesar resultados: {e}")
        finally:
            set_busy(False)

    elif ev == "-XLS-":
        if not last_outputs:
            sg.popup("Primero corre Optimizar.")
            continue
        try:
            export_excel(last_outputs, "planificacion.xlsx")
            sg.popup("Excel exportado como planificacion.xlsx")
        except Exception as e:
            sg.popup_error(f"No se pudo exportar Excel: {e}")

    elif ev == "-PNG-":
        if not last_outputs:
            sg.popup("Primero corre Optimizar.")
            continue
        try:
            outdir = sg.popup_get_folder("Selecciona carpeta destino", default_path=os.getcwd())
            if outdir:
                export_pngs(last_outputs["figs"], outdir)
                sg.popup(f"Gráficos exportados en {outdir}")
        except Exception as e:
            sg.popup_error(f"No se pudo exportar PNG: {e}")

window.close()
