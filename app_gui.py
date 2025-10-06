import os, sys, traceback
import PySimpleGUI as sg
from pathlib import Path
import csv

from dataio.loaders import (
    load_inputs, load_params, load_demand, C_MAP_DEFAULT
)
from core.optimizer import solve_plan
from core.kpis import build_kpis_text
from dataio.exporters import export_excel, export_pngs
from viz.charts import make_figures

APP_TITLE = "Salmon Planner (v1.0)"


def resource_path(rel_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, rel_path)


def pipeline(csv_path: str | None, yaml_path: str, demanda_path: str | None):
    params = load_params(yaml_path)
    if demanda_path:
        inputs = load_demand(demanda_path, params)
    else:
        inputs = load_inputs(csv_path)
    outputs = solve_plan(inputs, params)
    kpis_text = build_kpis_text(outputs, params)
    figs = make_figures(outputs, params)
    return {
        "plan_df": outputs["plan_df"],
        "kpis_text": kpis_text,
        "figs": figs,
        "notes": outputs.get("notes", [])
    }


# -------- Ventana para ingresar piezas por calibre (crea CSV simple) --------
def ingresar_piezas_popup(parent_window):
    layout = [
        [sg.Text("Ingresar número de piezas por calibre", font=("Any", 11, "bold"))],
        [sg.Column(
            [[sg.Text(f"{C_MAP_DEFAULT[i]}", size=(6, 1)),
              sg.Input("0", key=f"-PIEZ_{i}-", size=(10, 1))]
             for i in C_MAP_DEFAULT],
            scrollable=True, vertical_scroll_only=True, size=(220, 300)
        )],
        [sg.Push(), sg.Button("Guardar CSV"), sg.Button("Cancelar")]
    ]

    win = sg.Window("Piezas por calibre", layout, modal=True, finalize=True)
    saved_path = None

    while True:
        ev, vals = win.read()
        if ev in (sg.WIN_CLOSED, "Cancelar"):
            break
        if ev == "Guardar CSV":
            save_path = sg.popup_get_file(
                "Guardar como",
                save_as=True,
                default_extension=".csv",
                file_types=(("CSV Files", "*.csv"),),
                initial_folder=str(Path.cwd() / "examples"),
                no_window=True
            )
            if not save_path:
                sg.popup("Guardado cancelado.")
                continue

            try:
                with open(save_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["calibre", "piezas"])
                    for i in C_MAP_DEFAULT:
                        etiqueta = C_MAP_DEFAULT[i]
                        val = vals.get(f"-PIEZ_{i}-", "0").strip()
                        try:
                            piezas = int(val)
                        except Exception:
                            piezas = 0
                        writer.writerow([etiqueta, piezas])
                sg.popup(f"Archivo guardado correctamente:\n{save_path}")
                saved_path = save_path
                break
            except Exception as e:
                sg.popup_error(f"Error al guardar CSV: {e}")

    win.close()

    # Actualiza el campo de Calibres CSV automáticamente
    if saved_path:
        parent_window["-CSV-"].update(saved_path)


# =======================
#   UI principal
# =======================
sg.theme("SystemDefault")

# Columnas fijas para la tabla
TABLE_COLUMNS = ["línea", "empaque", "producto", "formato caja",
                 "calibre", "n° de cajas", "n° de piezas"]

layout = [
    [sg.Text("Calibres CSV"),
     sg.Input(key="-CSV-", expand_x=True),
     sg.Button("Ingresar", key="-INGRESAR_PZ-"),
     sg.FileBrowse("Buscar", target="-CSV-", file_types=(("CSV Files", "*.csv"),))],
    [sg.Text("Demanda (xlsx/csv)"),
      sg.Input(key="-DEM-", expand_x=True),
      sg.FileBrowse("Buscar", target="-DEM-", file_types=(("Excel/CSV", "*.xlsx;*.xls;*.csv"),))],
    [sg.Text("Parámetros YAML"),
     sg.Input(key="-YAML-", expand_x=True),
     sg.FileBrowse("Buscar", target="-YAML-", file_types=(("YAML", "*.yml;*.yaml"),))],
    [sg.Button("Optimizar", key="-RUN-")],
    [sg.Text("KPIs:")],
    [sg.Multiline(key="-KPIS-", expand_x=True, size=(80, 8),
                  disabled=True, autoscroll=False, no_scrollbar=True)],
    # Botones de exportación, alineados abajo a la derecha del cuadro de KPIs
    [sg.Push(), sg.Button("Exportar Excel", key="-XLS-"),
     sg.Button("Exportar Gráficos", key="-PNG-")],
    [sg.Table(
        values=[],
        headings=TABLE_COLUMNS,
        key="-TAB-",
        enable_events=True,
        enable_click_events=True,  # detectar clic en encabezados
        justification="center",
        auto_size_columns=True, expand_x=True, expand_y=True, num_rows=12
    )]
]

try:
    window = sg.Window(APP_TITLE, layout, icon=resource_path("assets/icon.ico"),
                       resizable=True, finalize=True)
except Exception:
    window = sg.Window(APP_TITLE, layout, resizable=True, finalize=True)

last_outputs = None
current_df = None  # DataFrame actualmente mostrado
sort_states = {col: None for col in TABLE_COLUMNS}  # None / True(asc) / False(desc)
current_sorted_col = None  # declarado a nivel de módulo (no usar 'global' fuera de funciones)


def set_busy(is_busy: bool):
    window["-RUN-"].update(disabled=is_busy)
    window["-XLS-"].update(disabled=is_busy)
    window["-PNG-"].update(disabled=is_busy)


def _decorate_headings(active_col: str | None, ascending: bool | None):
    """Pone flecha ▲/▼ en el encabezado activo usando el widget Treeview."""
    arrows = {"asc": " ▲", "desc": " ▼", "none": ""}
    tv = window["-TAB-"].Widget  # ttk.Treeview
    for i, base in enumerate(TABLE_COLUMNS, start=1):
        txt = base
        if active_col == base:
            if ascending is True:
                txt += arrows["asc"]
            elif ascending is False:
                txt += arrows["desc"]
        # columnas de Treeview son '#1', '#2', ...
        tv.heading(f"#{i}", text=txt)


def _refresh_table(df):
    """Refresca valores y encabezados (con flecha si hay orden activo)."""
    global current_df
    current_df = df.copy() if df is not None else None
    rows = []
    if current_df is not None and not current_df.empty:
        # Asegurar nombres esperados en la GUI
        gui_df = current_df.rename(columns={
            "linea": "línea",
            "formato_caja": "formato caja",
            "cajas": "n° de cajas",
            "piezas": "n° de piezas"
        })
        rows = gui_df[TABLE_COLUMNS].values.tolist()
    window["-TAB-"].update(values=rows)
    _decorate_headings(current_sorted_col, sort_states.get(current_sorted_col))


# -------- Loop principal --------
while True:
    ev, vals = window.read()
    if ev in (sg.WINDOW_CLOSED, "Exit"):
        break

    # --- Click en encabezado de la tabla: ordenar ---
    if isinstance(ev, tuple) and ev[0] == "-TAB-" and ev[2][0] == -1:
        col_idx = ev[2][1]
        col_name_gui = TABLE_COLUMNS[col_idx]
        if last_outputs and "plan_df" in last_outputs and current_df is not None:
            # Determinar nombre de columna en DataFrame base
            col_map_rev = {
                "línea": "linea",
                "empaque": "empaque",
                "producto": "producto",
                "formato caja": "formato_caja",
                "calibre": "calibre",
                "n° de cajas": "cajas",
                "n° de piezas": "piezas",
            }
            base_col = col_map_rev[col_name_gui]

            # Alternar estado: None -> asc -> desc -> asc ...
            prev = sort_states[col_name_gui]
            ascending = True if prev is None else (not prev)

            # Ordenar y refrescar
            try:
                df_sorted = current_df.sort_values(by=[base_col], ascending=ascending).reset_index(drop=True)
            except Exception:
                # por si hay tipos mezclados, forzar como string
                df_sorted = current_df.copy()
                df_sorted[base_col] = df_sorted[base_col].astype(str)
                df_sorted = df_sorted.sort_values(by=[base_col], ascending=ascending).reset_index(drop=True)

            # Actualizar estados y encabezados
            for k in sort_states:
                sort_states[k] = None
            sort_states[col_name_gui] = ascending
            current_sorted_col = col_name_gui

            _refresh_table(df_sorted)
        continue

    if ev == "-INGRESAR_PZ-":
        ingresar_piezas_popup(window)
        continue

    if ev == "-RUN-":
        yaml_path = vals["-YAML-"]
        demanda_path = vals["-DEM-"] if vals["-DEM-"] else None
        csv_path = vals["-CSV-"] if vals["-CSV-"] else None

        if not yaml_path:
            sg.popup("Selecciona el YAML de parámetros.")
            continue
        if not demanda_path and not csv_path:
            sg.popup("Carga Demanda (xlsx/csv) o un Calibres CSV.")
            continue

        set_busy(True)
        window["-KPIS-"].update("Ejecutando optimización...\n")
        window.perform_long_operation(lambda: pipeline(csv_path, yaml_path, demanda_path), "-DONE-")

    elif ev == "-DONE-":
        try:
            result = vals["-DONE-"]
            last_outputs = result

            window["-KPIS-"].update(result["kpis_text"])

            plan_df = result["plan_df"]
            if plan_df is not None and not plan_df.empty:
                # Reset estados de orden
                for k in sort_states:
                    sort_states[k] = None
                current_sorted_col = None  # no usar 'global' aquí; estamos en nivel de módulo

                _refresh_table(plan_df)
            else:
                window["-TAB-"].update(values=[])
                _decorate_headings(None, None)
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
            outdir = sg.popup_get_folder("Selecciona carpeta destino",
                                         default_path=os.getcwd())
            if outdir:
                export_pngs(last_outputs["figs"], outdir)
                sg.popup(f"Gráficos exportados en {outdir}")
        except Exception as e:
            sg.popup_error(f"No se pudo exportar PNG: {e}")

window.close()
