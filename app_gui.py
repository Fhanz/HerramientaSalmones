# app_gui.py
import os
import sys
import traceback
import yaml
import csv
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

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
    params = load_params(yaml_path)
    _ = load_demand(demanda_path, params)
    inputs = load_inputs(csv_path)
    outputs = solve_plan(inputs, params)
    kpis_text = build_kpis_text(outputs, params)
    figs = make_figures(outputs, params)
    return {
        "plan_df": outputs["plan_df"],
        "kpis_text": kpis_text,
        "figs": figs,
        "notes": outputs.get("notes", []),
    }


# ---------- Popup: ingresar SALMONES por calibre ----------
def ingresar_salmones_popup(parent, csv_var: tk.StringVar):
    top = tk.Toplevel(parent)
    top.title("Salmones por calibre")
    top.grab_set()

    label = ttk.Label(
        top,
        text="Ingresar número de SALMONES por calibre",
        font=("TkDefaultFont", 10, "bold"),
    )
    label.pack(padx=10, pady=10, anchor="w")

    frame_list = ttk.Frame(top)
    frame_list.pack(padx=10, pady=(0, 10), fill="both", expand=True)

    # Scrollable area
    canvas = tk.Canvas(frame_list)
    scrollbar = ttk.Scrollbar(frame_list, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)

    inner.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
    )

    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    entries = {}

    for i in C_MAP_DEFAULT:
        row = ttk.Frame(inner)
        row.pack(fill="x", pady=2)

        etiqueta = C_MAP_DEFAULT[i]
        ttk.Label(row, text=str(etiqueta), width=10).pack(side="left")
        entry = ttk.Entry(row, width=10)
        entry.insert(0, "0")
        entry.pack(side="left", padx=5)
        entries[i] = entry

    btn_frame = ttk.Frame(top)
    btn_frame.pack(padx=10, pady=10, fill="x")

    def on_guardar():
        initial_dir = str(Path.cwd() / "examples")
        save_path = filedialog.asksaveasfilename(
            parent=top,
            title="Guardar como",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            initialdir=initial_dir,
        )
        if not save_path:
            messagebox.showinfo("Guardado cancelado", "Guardado cancelado.")
            return

        try:
            with open(save_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["calibre", "salmones"])
                for i in C_MAP_DEFAULT:
                    etiqueta = C_MAP_DEFAULT[i]
                    val = entries[i].get().strip()
                    try:
                        salmones = int(val)
                    except Exception:
                        salmones = 0
                    writer.writerow([etiqueta, salmones])
            messagebox.showinfo("Archivo guardado", f"Archivo guardado:\n{save_path}")
            csv_var.set(save_path)
            top.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Error al guardar CSV: {e}")

    def on_cancelar():
        top.destroy()

    ttk.Button(btn_frame, text="Guardar CSV", command=on_guardar).pack(
        side="right", padx=5
    )
    ttk.Button(btn_frame, text="Cancelar", command=on_cancelar).pack(side="right")


# ---------- Popup: editar capacidades ----------
def editar_capacidades_popup(parent, params: dict, yaml_path: str):
    mj = params.get("mj", {})
    ne = params.get("ne", {})

    top = tk.Toplevel(parent)
    top.title("Editar capacidades")
    top.grab_set()

    title = ttk.Label(
        top, text="Editar capacidades", font=("TkDefaultFont", 11, "bold")
    )
    title.pack(padx=10, pady=10, anchor="w")

    main_frame = ttk.Frame(top)
    main_frame.pack(padx=10, pady=(0, 10), fill="both", expand=True)

    frame_mj = ttk.LabelFrame(main_frame, text="Capacidad de líneas (mj) [piezas/turno]")
    frame_ne = ttk.LabelFrame(
        main_frame, text="Capacidad de empaque (ne) [piezas/turno]"
    )
    frame_mj.pack(side="left", fill="both", expand=True, padx=(0, 5))
    frame_ne.pack(side="left", fill="both", expand=True, padx=(5, 0))

    mj_entries = {}
    ne_entries = {}

    for l in mj:
        row = ttk.Frame(frame_mj)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=str(l), width=18).pack(side="left")
        e = ttk.Entry(row, width=12)
        e.insert(0, str(mj[l]))
        e.pack(side="left", padx=5)
        mj_entries[l] = e

    for a in ne:
        row = ttk.Frame(frame_ne)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=str(a), width=18).pack(side="left")
        e = ttk.Entry(row, width=12)
        e.insert(0, str(ne[a]))
        e.pack(side="left", padx=5)
        ne_entries[a] = e

    btn_frame = ttk.Frame(top)
    btn_frame.pack(padx=10, pady=10, fill="x")

    def collect_new():
        new_mj, new_ne = {}, {}
        for l, entry in mj_entries.items():
            v = entry.get().strip()
            if v != "":
                try:
                    new_mj[str(l)] = float(v)
                except Exception:
                    pass
        for a, entry in ne_entries.items():
            v = entry.get().strip()
            if v != "":
                try:
                    new_ne[str(a)] = float(v)
                except Exception:
                    pass
        return new_mj, new_ne

    def on_actualizar():
        new_mj, new_ne = collect_new()
        try:
            params["mj"].update(new_mj)
            params["ne"].update(new_ne)

            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data.setdefault("mj", {}).update(new_mj)
            data.setdefault("ne", {}).update(new_ne)
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

            messagebox.showinfo("OK", "Capacidades actualizadas en el YAML.")
        except Exception as e:
            messagebox.showerror("Error", f"Error al actualizar YAML: {e}")

    def on_guardar_como():
        new_mj, new_ne = collect_new()
        save_path = filedialog.asksaveasfilename(
            parent=top,
            title="Guardar copia como...",
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml;*.yml")],
        )
        if not save_path:
            return
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data.setdefault("mj", {}).update(new_mj)
            data.setdefault("ne", {}).update(new_ne)
            with open(save_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
            messagebox.showinfo("Archivo guardado", f"Archivo guardado:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar: {e}")

    def on_cerrar():
        top.destroy()

    ttk.Button(btn_frame, text="Actualizar", command=on_actualizar).pack(
        side="right", padx=5
    )
    ttk.Button(btn_frame, text="Guardar como...", command=on_guardar_como).pack(
        side="right", padx=5
    )
    ttk.Button(btn_frame, text="Cerrar", command=on_cerrar).pack(side="left")


# =======================
#   UI principal
# =======================
TABLE_COLUMNS = [
    "Línea",
    "Empaque",
    "Producto",
    "Formato caja",
    "Calibre",
    "N° de cajas",
    "N° de piezas",
]


def main():
    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("900x600")

    # Variables de entrada
    csv_var = tk.StringVar()
    dem_var = tk.StringVar()
    yaml_var = tk.StringVar()

    # Estado
    state = {
        "last_outputs": None,
        "params_loaded": None,
        "yaml_loaded_path": None,
    }

    # Layout principal
    main_frame = ttk.Frame(root, padding=10)
    main_frame.pack(fill="both", expand=True)

    # Fila CSV
    row_csv = ttk.Frame(main_frame)
    row_csv.pack(fill="x", pady=3)
    ttk.Label(row_csv, text="Calibres CSV").pack(side="left")
    entry_csv = ttk.Entry(row_csv, textvariable=csv_var)
    entry_csv.pack(side="left", fill="x", expand=True, padx=5)

    def on_browse_csv():
        path = filedialog.askopenfilename(
            parent=root,
            title="Seleccionar CSV de calibres",
            filetypes=[("CSV Files", "*.csv")],
        )
        if path:
            csv_var.set(path)

    ttk.Button(
        row_csv,
        text="Ingresar",
        command=lambda: ingresar_salmones_popup(root, csv_var),
    ).pack(side="left", padx=5)
    ttk.Button(row_csv, text="Buscar", command=on_browse_csv).pack(side="left")

    # Fila Demanda
    row_dem = ttk.Frame(main_frame)
    row_dem.pack(fill="x", pady=3)
    ttk.Label(row_dem, text="Demanda (xlsx/csv)").pack(side="left")
    entry_dem = ttk.Entry(row_dem, textvariable=dem_var)
    entry_dem.pack(side="left", fill="x", expand=True, padx=5)

    def on_browse_dem():
        path = filedialog.askopenfilename(
            parent=root,
            title="Seleccionar archivo de demanda",
            filetypes=[
                ("Excel/CSV", "*.xlsx;*.xls;*.csv"),
                ("Excel", "*.xlsx;*.xls"),
                ("CSV", "*.csv"),
            ],
        )
        if path:
            dem_var.set(path)

    ttk.Button(row_dem, text="Buscar", command=on_browse_dem).pack(side="left")

    # Fila YAML
    row_yaml = ttk.Frame(main_frame)
    row_yaml.pack(fill="x", pady=3)
    ttk.Label(row_yaml, text="Parámetros YAML").pack(side="left")
    entry_yaml = ttk.Entry(row_yaml, textvariable=yaml_var)
    entry_yaml.pack(side="left", fill="x", expand=True, padx=5)

    def on_browse_yaml():
        path = filedialog.askopenfilename(
            parent=root,
            title="Seleccionar YAML",
            filetypes=[("YAML", "*.yml;*.yaml"), ("Todos", "*.*")],
        )
        if path:
            yaml_var.set(path)

    ttk.Button(row_yaml, text="Buscar", command=on_browse_yaml).pack(side="left")

    edit_cap_button = ttk.Button(
        row_yaml,
        text="Editar capacidades",
        state="normal",
        command=lambda: on_edit_cap(),
    )
    edit_cap_button.pack(side="left", padx=5)

    # Botón Optimizar
    row_run = ttk.Frame(main_frame)
    row_run.pack(fill="x", pady=(10, 5))
    run_button = ttk.Button(row_run, text="Optimizar")
    run_button.pack(side="left")

    # KPIs
    ttk.Label(main_frame, text="KPIs:").pack(anchor="w", pady=(5, 2))
    kpis_text = tk.Text(main_frame, height=8, wrap="word")
    kpis_text.configure(state="disabled")
    kpis_text.pack(fill="x", expand=False)

    # Botones Exportar
    row_export = ttk.Frame(main_frame)
    row_export.pack(fill="x", pady=(5, 5))
    xls_button = ttk.Button(row_export, text="Exportar Excel")
    png_button = ttk.Button(row_export, text="Exportar Gráficos")
    xls_button.pack(side="right", padx=5)
    png_button.pack(side="right", padx=5)

    # Tabla
    table_frame = ttk.Frame(main_frame)
    table_frame.pack(fill="both", expand=True, pady=(5, 0))

    tree = ttk.Treeview(table_frame, columns=TABLE_COLUMNS, show="headings")
    for col in TABLE_COLUMNS:
        tree.heading(col, text=col)
        tree.column(col, width=100, anchor="center")

    vsb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)

    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    # Helpers
    def set_busy(is_busy: bool):
        state_str = "disabled" if is_busy else "normal"
        run_button.config(state=state_str)
        xls_button.config(state=state_str)
        png_button.config(state=state_str)
        edit_cap_button.config(state=state_str)
        root.update_idletasks()

    def update_kpis(text: str):
        kpis_text.configure(state="normal")
        kpis_text.delete("1.0", tk.END)
        kpis_text.insert(tk.END, text or "")
        kpis_text.configure(state="disabled")

    def update_table(plan_df: pd.DataFrame | None):
        for item in tree.get_children():
            tree.delete(item)
        if plan_df is None or plan_df.empty:
            return
        gui_df = plan_df.rename(
            columns={
                "linea": "Línea",
                "empaque": "Empaque",
                "producto": "Producto",
                "formato_caja": "Formato caja",
                "calibre": "Calibre",
                "cajas": "N° de cajas",
                "piezas": "N° de piezas",
            }
        )
        for _, row in gui_df[TABLE_COLUMNS].iterrows():
            tree.insert("", tk.END, values=list(row))

    # Callbacks

    def on_edit_cap():
        ypath = yaml_var.get()
        if not ypath or not os.path.exists(ypath):
            messagebox.showinfo(
                "Editar capacidades", "Primero selecciona un YAML válido."
            )
            return
        try:
            params = load_params(ypath)
            state["params_loaded"] = params
            state["yaml_loaded_path"] = ypath
        except Exception as e:
            messagebox.showerror("Error", f"Error al leer YAML: {e}")
            return
        editar_capacidades_popup(root, state["params_loaded"], state["yaml_loaded_path"])

    def on_run():
        yaml_path = yaml_var.get()
        demanda_path = dem_var.get()
        csv_path = csv_var.get()

        if not yaml_path or not os.path.exists(yaml_path):
            messagebox.showinfo("Falta archivo", "Selecciona el YAML de parámetros.")
            return
        if not demanda_path or not os.path.exists(demanda_path):
            messagebox.showinfo(
                "Falta archivo", "Carga el archivo de Demanda (xlsx/csv)."
            )
            return
        if not csv_path or not os.path.exists(csv_path):
            messagebox.showinfo(
                "Falta archivo", "Carga el CSV de Calibres (calibre,salmones)."
            )
            return

        set_busy(True)
        try:
            result = pipeline(csv_path, yaml_path, demanda_path)
            state["last_outputs"] = result
            update_kpis(result["kpis_text"])
            update_table(result["plan_df"])
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error", f"Error al optimizar: {e}")
        finally:
            set_busy(False)

    def on_export_xls():
        if not state["last_outputs"]:
            messagebox.showinfo("Exportar Excel", "Primero corre Optimizar.")
            return
        out = filedialog.asksaveasfilename(
            parent=root,
            title="Guardar Excel como",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not out:
            return
        try:
            export_excel(state["last_outputs"], out)
            messagebox.showinfo("Excel exportado", f"Excel exportado: {out}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo exportar Excel: {e}")

    def on_export_png():
        if not state["last_outputs"]:
            messagebox.showinfo("Exportar Gráficos", "Primero corre Optimizar.")
            return
        outdir = filedialog.askdirectory(
            parent=root,
            title="Selecciona carpeta destino",
            initialdir=os.getcwd(),
        )
        if not outdir:
            return
        try:
            export_pngs(state["last_outputs"]["figs"], outdir)
            messagebox.showinfo(
                "Gráficos exportados", f"Gráficos exportados en:\n{outdir}"
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo exportar PNG: {e}")

    # Bind buttons
    run_button.config(command=on_run)
    xls_button.config(command=on_export_xls)
    png_button.config(command=on_export_png)

    # Cerrar
    def on_close():
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
