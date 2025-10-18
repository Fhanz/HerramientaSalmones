# app_gui.py
import os, sys, traceback, yaml, csv
import PySimpleGUI as sg
from pathlib import Path
import pandas as pd

from dataio.loaders import load_inputs, load_params, load_demand, C_MAP_DEFAULT
from core.optimizer import solve_plan
from core.kpis import build_kpis_text
from dataio.exporters import export_excel, export_pngs
from viz.charts import make_figures

APP_TITLE = "Salmon Planner (v2.0)"

def resource_path(rel_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, rel_path)

# ---------- PIPELINE: Demanda + CSV salmones + YAML ----------
def pipeline(csv_path: str, yaml_path: str, demanda_path: str):
    params = load_params(yaml_path)          # lee YAML
    _ = load_demand(demanda_path, params)    # setea params['dpkc']
    inputs = load_inputs(csv_path)           # CSV calibre,salmones (ac)
    outputs = solve_plan(inputs, params)
    kpis_text = build_kpis_text(outputs, params)
    figs = make_figures(outputs, params)
    return {"plan_df": outputs["plan_df"], "kpis_text": kpis_text, "figs": figs, "notes": outputs.get("notes", [])}

# ---------- Popup: ingresar SALMONES por calibre ----------
def ingresar_salmones_popup(parent_window):
    layout = [
        [sg.Text("Ingresar número de SALMONES por calibre", font=("Any", 11, "bold"))],
        [sg.Column(
            [[sg.Text(f"{C_MAP_DEFAULT[i]}", size=(6, 1)),
              sg.Input("0", key=f"-SALM_{i}-", size=(10, 1))]
             for i in C_MAP_DEFAULT],
            scrollable=True, vertical_scroll_only=True, size=(260, 320)
        )],
        [sg.Push(), sg.Button("Guardar CSV"), sg.Button("Cancelar")]
    ]
    win = sg.Window("Salmones por calibre", layout, modal=True, finalize=True)
    saved_path = None
    while True:
        ev, vals = win.read()
        if ev in (sg.WIN_CLOSED, "Cancelar"):
            break
        if ev == "Guardar CSV":
            save_path = sg.popup_get_file("Guardar como", save_as=True, default_extension=".csv",
                                          file_types=(("CSV Files", "*.csv"),),
                                          initial_folder=str(Path.cwd() / "examples"), no_window=True)
            if not save_path:
                sg.popup("Guardado cancelado."); continue
            try:
                with open(save_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f); writer.writerow(["calibre", "salmones"])
                    for i in C_MAP_DEFAULT:
                        etiqueta = C_MAP_DEFAULT[i]
                        val = vals.get(f"-SALM_{i}-", "0").strip()
                        try: salmones = int(val)
                        except: salmones = 0
                        writer.writerow([etiqueta, salmones])
                sg.popup(f"Archivo guardado:\n{save_path}")
                saved_path = save_path; break
            except Exception as e:
                sg.popup_error(f"Error al guardar CSV: {e}")
    win.close()
    if saved_path: parent_window["-CSV-"].update(saved_path)

# ---------- Popup: editar capacidades (Inputs reales, no tablas) ----------
def editar_capacidades_popup(params: dict, yaml_path: str):
    mj = params.get("mj", {})
    ne = params.get("ne", {})

    # Armamos dos columnas con Inputs editables
    col_mj = [[sg.Text(str(l), size=(18,1)), sg.Input(str(mj[l]), key=f"-MJ-{l}-", size=(12,1))] for l in mj]
    col_ne = [[sg.Text(str(a), size=(18,1)), sg.Input(str(ne[a]), key=f"-NE-{a}-", size=(12,1))] for a in ne]

    layout = [
        [sg.Text("Editar capacidades", font=("Any", 12, "bold"))],
        [sg.Frame("Capacidad de líneas (mj) [piezas/turno]", [[sg.Column(col_mj, scrollable=True, size=(360, 220))]]),
         sg.Frame("Capacidad de empaque (ne) [piezas/turno]", [[sg.Column(col_ne, scrollable=True, size=(360, 220))]])],
        [sg.Push(), sg.Button("Actualizar", key="-UPD-"),
         sg.Button("Guardar como...", key="-SAVEAS-"), sg.Button("Cerrar")]
    ]
    win = sg.Window("Editar capacidades", layout, modal=True, finalize=True)

    # Helpers
    def _collect_new():
        new_mj, new_ne = {}, {}
        for l in mj:
            v = win[f"-MJ-{l}-"].get().strip()
            if v != "":
                try: new_mj[str(l)] = float(v)
                except: pass
        for a in ne:
            v = win[f"-NE-{a}-"].get().strip()
            if v != "":
                try: new_ne[str(a)] = float(v)
                except: pass
        return new_mj, new_ne

    while True:
        ev, _ = win.read()
        if ev in (sg.WIN_CLOSED, "Cerrar"):
            break
        if ev == "-UPD-":
            new_mj, new_ne = _collect_new()
            try:
                # Actualiza params en memoria
                params["mj"].update(new_mj); params["ne"].update(new_ne)
                # Reescribe YAML original
                with open(yaml_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                data.setdefault("mj", {}).update(new_mj)
                data.setdefault("ne", {}).update(new_ne)
                with open(yaml_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
                sg.popup("Capacidades actualizadas en el YAML.")
            except Exception as e:
                sg.popup_error(f"Error al actualizar YAML: {e}")
        if ev == "-SAVEAS-":
            new_mj, new_ne = _collect_new()
            save_path = sg.popup_get_file("Guardar copia como...", save_as=True, default_extension=".yaml",
                                          file_types=(("YAML files", "*.yaml;*.yml"),))
            if save_path:
                try:
                    with open(yaml_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                    data.setdefault("mj", {}).update(new_mj)
                    data.setdefault("ne", {}).update(new_ne)
                    with open(save_path, "w", encoding="utf-8") as f:
                        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
                    sg.popup(f"Archivo guardado:\n{save_path}")
                except Exception as e:
                    sg.popup_error(f"No se pudo guardar: {e}")
    win.close()

# =======================
#   UI principal
# =======================
sg.theme("SystemDefault")

TABLE_COLUMNS = ["Línea", "Empaque", "Producto", "Formato caja", "Calibre", "N° de cajas", "N° de piezas"]

layout = [
    [sg.Text("Calibres CSV"),
     sg.Input(key="-CSV-", expand_x=True),
     sg.Button("Ingresar", key="-INGRESAR_SALM-"),
     sg.FileBrowse("Buscar", target="-CSV-", file_types=(("CSV Files", "*.csv"),))],
    [sg.Text("Demanda (xlsx/csv)"),
     sg.Input(key="-DEM-", expand_x=True),
     sg.FileBrowse("Buscar", target="-DEM-", file_types=(("Excel/CSV", "*.xlsx;*.xls;*.csv"),))],
    [sg.Text("Parámetros YAML"),
     sg.Input(key="-YAML-", expand_x=True, enable_events=True),   # <<— importante
     sg.FileBrowse("Buscar", target="-YAML-", file_types=(("YAML", "*.yml;*.yaml"),)),
     sg.Button("Editar capacidades", key="-EDIT_CAP-", disabled=True)],
    [sg.Button("Optimizar", key="-RUN-")],
    [sg.Text("KPIs:")],
    [sg.Multiline(key="-KPIS-", expand_x=True, size=(80, 8), disabled=True, autoscroll=False, no_scrollbar=True)],
    [sg.Push(), sg.Button("Exportar Excel", key="-XLS-"), sg.Button("Exportar Gráficos", key="-PNG-")],
    [sg.Table(values=[], headings=TABLE_COLUMNS, key="-TAB-", enable_events=False,
              justification="center", auto_size_columns=True, expand_x=True, expand_y=True, num_rows=12)]
]

window = sg.Window(APP_TITLE, layout, resizable=True, finalize=True)

last_outputs = None
params_loaded: dict | None = None
yaml_loaded_path: str | None = None

def set_busy(is_busy: bool):
    for key in ("-RUN-", "-XLS-", "-PNG-", "-EDIT_CAP-"):
        window[key].update(disabled=is_busy)

# ---------- LOOP ----------
while True:
    ev, vals = window.read()
    if ev in (sg.WINDOW_CLOSED, "Exit"):
        break

    # YAML seleccionado/tecleado → cargar params y habilitar editar
    if ev == "-YAML-":
        ypath = vals["-YAML-"]
        if ypath and os.path.exists(ypath):
            try:
                params_loaded = load_params(ypath)
                yaml_loaded_path = ypath
                window["-EDIT_CAP-"].update(disabled=False)
            except Exception as e:
                params_loaded = None; yaml_loaded_path = None
                window["-EDIT_CAP-"].update(disabled=True)
                sg.popup_error(f"Error al leer YAML: {e}")
        else:
            params_loaded = None; yaml_loaded_path = None
            window["-EDIT_CAP-"].update(disabled=True)
        continue

    if ev == "-EDIT_CAP-":
        if params_loaded and yaml_loaded_path:
            editar_capacidades_popup(params_loaded, yaml_loaded_path)
        else:
            sg.popup("Primero selecciona un YAML válido.")
        continue

    if ev == "-INGRESAR_SALM-":
        ingresar_salmones_popup(window)
        continue

    if ev == "-RUN-":
        yaml_path = vals["-YAML-"]
        demanda_path = vals["-DEM-"]
        csv_path = vals["-CSV-"]

        if not yaml_path or not os.path.exists(yaml_path):
            sg.popup("Selecciona el YAML de parámetros."); continue
        if not demanda_path or not os.path.exists(demanda_path):
            sg.popup("Carga el archivo de Demanda (xlsx/csv)."); continue
        if not csv_path or not os.path.exists(csv_path):
            sg.popup("Carga el CSV de Calibres (calibre,salmones)."); continue

        set_busy(True)
        try:
            result = pipeline(csv_path, yaml_path, demanda_path)
            last_outputs = result
            window["-KPIS-"].update(result["kpis_text"])

            plan_df = result["plan_df"]
            if plan_df is not None and not plan_df.empty:
                gui_df = plan_df.rename(columns={
                    "linea": "Línea","empaque": "Empaque","producto": "Producto",
                    "formato_caja": "Formato caja","calibre": "Calibre",
                    "cajas": "N° de cajas","piezas": "N° de piezas"})
                window["-TAB-"].update(values=gui_df[TABLE_COLUMNS].values.tolist())
            else:
                window["-TAB-"].update(values=[])
        except Exception as e:
            traceback.print_exc()
            sg.popup_error(f"Error al optimizar: {e}")
        finally:
            set_busy(False)
        continue

    if ev == "-XLS-":
        if not last_outputs:
            sg.popup("Primero corre Optimizar."); continue
        out = sg.popup_get_file("Guardar Excel como", save_as=True, default_extension=".xlsx",
                                file_types=(("Excel", "*.xlsx"),))
        if out:
            try:
                export_excel(last_outputs, out)
                sg.popup(f"Excel exportado: {out}")
            except Exception as e:
                sg.popup_error(f"No se pudo exportar Excel: {e}")
        continue

    if ev == "-PNG-":
        if not last_outputs:
            sg.popup("Primero corre Optimizar."); continue
        outdir = sg.popup_get_folder("Selecciona carpeta destino", default_path=os.getcwd())
        if outdir:
            try:
                export_pngs(last_outputs["figs"], outdir)
                sg.popup(f"Gráficos exportados en {outdir}")
            except Exception as e:
                sg.popup_error(f"No se pudo exportar PNG: {e}")
        continue

window.close()
