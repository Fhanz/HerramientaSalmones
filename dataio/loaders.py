import pandas as pd, yaml
from pathlib import Path
import csv

# --- Nuevo: mapa por defecto para el editor de calibres ---
C_MAP_DEFAULT = {
    0: "1-2", 1: "2-3", 2: "3-4", 3: "4-5", 4: "5-6",
    5: "6-7", 6: "7-8", 7: "8-9", 8: "9-10", 9: "10-11",
    10: "11-12", 11: "12-13", 12: "13-14", 13: "14+"
}

# --- Nuevo: utilitario para completar/fijar orden del mapa ---
def _normalize_cmap(cmap: dict) -> dict:
    """Asegura claves 0..13 y orden por índice; completa faltantes con default."""
    fixed = dict(C_MAP_DEFAULT)  # copia
    if cmap:
        for k, v in cmap.items():
            try:
                ki = int(k)
            except Exception:
                continue
            if ki in fixed and isinstance(v, str) and v.strip():
                fixed[ki] = v.strip()
    # ordenar por índice
    return dict(sorted(fixed.items(), key=lambda kv: kv[0]))

# --- Nuevo: helpers de demanda ---
def _to_idx_from_label(label: str, c_map: dict) -> int:
    """Convierte '7-8'→7 usando C_map; si ya es int/str-int, retorna int."""
    try:
        return int(label)
    except Exception:
        inv = {v: k for k, v in c_map.items()}
        if label in inv:
            return inv[label]
        raise ValueError(f"Calibre inválido: {label}")

def _to_label_from_idx(idx: int, c_map: dict) -> str:
    """Convierte 7→'7-8' usando C_map."""
    try:
        return c_map[int(idx)]
    except Exception:
        raise ValueError(f"Índice de calibre inválido: {idx}")

# --- Nuevo: cargar/guardar CSV de calibres (idx, etiqueta) ---
def load_calibres_map(csv_path: str | Path) -> dict:
    """
    Lee un CSV con encabezado: idx,etiqueta
    Si no existe o está incompleto, devuelve C_MAP_DEFAULT completando faltantes.
    """
    if not csv_path:
        # si no te pasan ruta, retorna default para no romper UI
        return dict(C_MAP_DEFAULT)
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return dict(C_MAP_DEFAULT)

    cmap: dict[int, str] = {}
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # soporta nombres de columnas con espacios/blancos
        cols = [c.strip().lower() for c in (reader.fieldnames or [])]
        # tolera variantes: "idx"/"index" y "etiqueta"/"label"
        try:
            i_idx = cols.index("idx") if "idx" in cols else cols.index("index")
        except ValueError:
            i_idx = None
        try:
            i_lab = cols.index("etiqueta") if "etiqueta" in cols else cols.index("label")
        except ValueError:
            i_lab = None
        for row in reader:
            if i_idx is None or i_lab is None:
                break
            keys = list(row.keys())
            k = keys[i_idx]; v = keys[i_lab]  # nombres originales
            try:
                idx = int(row[k])
            except Exception:
                continue
            etiqueta = (row[v] or "").strip()
            if etiqueta:
                cmap[idx] = etiqueta
    return _normalize_cmap(cmap)

def save_calibres_map(cmap: dict, csv_path: str | Path) -> None:
    """
    Escribe un CSV con encabezado: idx,etiqueta
    (Crea directorios si no existen)
    """
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    cmap = _normalize_cmap(cmap)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["idx", "etiqueta"])
        writer.writeheader()
        for idx, etiqueta in cmap.items():
            writer.writerow({"idx": idx, "etiqueta": etiqueta})

# --- NUEVO: Cargar Demanda desde xlsx/csv (simple o detallada) ---
def load_demand(path: str | Path, params: dict) -> pd.DataFrame:
    """
    Acepta .xlsx/.xls o .csv en dos esquemas:

    A) simple:    calibre, piezas
    B) detallado: producto, formato, calibre_idx|calibre, demanda_cajas
       -> convierte a calibre,piezas usando ukc y C_map del YAML.

    Retorna DataFrame con columnas: calibre, piezas (agrupado y validado).
    """
    if not path:
        raise ValueError("Debes seleccionar archivo de demanda.")
    p = Path(path)
    if not p.exists():
        raise ValueError(f"No existe el archivo de demanda: {p}")

    ext = p.suffix.lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(p)
    elif ext == ".csv":
        df = pd.read_csv(p)
    else:
        raise ValueError("Formato de demanda no soportado (usa .xlsx, .xls o .csv).")

    if df.empty:
        raise ValueError("El archivo de demanda está vacío.")

    df.columns = [c.strip().lower() for c in df.columns]

    # Esquema A: simple calibre,piezas
    if {"calibre", "piezas"}.issubset(df.columns):
        out = df.copy()
        out["calibre"] = out["calibre"].astype(str).str.strip()
        out["piezas"] = pd.to_numeric(out["piezas"], errors="coerce").fillna(0).astype(int)
        if (out["piezas"] < 0).any():
            raise ValueError("Hay piezas negativas en el archivo de demanda.")
        out = out.groupby("calibre", as_index=False)["piezas"].sum()
        return out

    # Esquema B: detallado producto, formato, calibre_idx|calibre, demanda_cajas
    need_base = {"producto", "formato", "demanda_cajas"}
    if need_base.issubset(df.columns) and ("calibre_idx" in df.columns or "calibre" in df.columns):
        ukc = params.get("ukc", {})
        if not ukc:
            raise ValueError("Falta 'ukc' en parámetros YAML para convertir demanda en cajas→piezas.")
        c_map = params.get("C_map", C_MAP_DEFAULT)

        # Normaliza calibre_idx
        if "calibre_idx" not in df.columns:
            df["calibre_idx"] = df["calibre"].astype(str).str.strip().apply(lambda s: _to_idx_from_label(s, c_map))

        # Validaciones básicas
        df["demanda_cajas"] = pd.to_numeric(df["demanda_cajas"], errors="coerce").fillna(0).astype(int)
        if (df["demanda_cajas"] < 0).any():
            raise ValueError("Hay demanda_cajas negativas en el archivo de demanda.")

        # Chequeo de formato y calibre_idx en ukc
        # (lanza error claro si falta alguna combinación)
        for i, row in df.iterrows():
            k = str(row["formato"])
            cidx = int(row["calibre_idx"])
            if k not in ukc:
                raise ValueError(f"Formato desconocido en demanda: '{k}'. No está en ukc del YAML.")
            if cidx not in ukc[k]:
                raise ValueError(f"calibre_idx={cidx} no válido para formato '{k}' según ukc del YAML.")

        # piezas = demanda_cajas * ukc[formato][calibre_idx]
        df["piezas"] = df.apply(lambda r: int(r["demanda_cajas"]) * int(ukc[str(r["formato"])][int(r["calibre_idx"])]), axis=1)

        # Convertir calibre_idx -> etiqueta según C_map
        etiqueta = {int(k): v for k, v in (c_map.items() if isinstance(c_map, dict) else dict(C_MAP_DEFAULT).items())}
        df["calibre"] = df["calibre_idx"].astype(int).map(etiqueta)

        out = df.groupby("calibre", as_index=False)["piezas"].sum()
        return out

    raise ValueError(
        "Estructura de demanda no reconocida. Usa (calibre,piezas) o "
        "(producto,formato,calibre_idx|calibre,demanda_cajas)."
    )

# --- EXISTENTE: no se toca ---
def load_inputs(csv_path: str) -> pd.DataFrame:
    if not csv_path:
        raise ValueError("Debes seleccionar el CSV de calibres.")
    df = pd.read_csv(csv_path)

    df.columns = [c.strip().lower() for c in df.columns]
    for col in ("calibre", "piezas"):
        if col not in df.columns:
            raise ValueError(f"Falta columna '{col}' en {csv_path}")

    df["calibre"] = df["calibre"].astype(str).str.strip()
    df["piezas"] = pd.to_numeric(df["piezas"], errors="coerce").fillna(0).astype(int)

    if (df["piezas"] < 0).any():
        raise ValueError("Hay piezas negativas en el CSV.")

    df = df.groupby("calibre", as_index=False)["piezas"].sum()
    return df

def load_params(yaml_path: str) -> dict:
    if not yaml_path:
        raise ValueError("Debes seleccionar el YAML de parámetros.")
    with open(yaml_path, "r", encoding="utf-8") as f:
        params = yaml.safe_load(f)

    # --- Compatibilidad con esquema nuevo (Gurobi) y viejo (dummy) ---
    # Requeridos mínimos reales
    if "lineas" not in params or not isinstance(params["lineas"], dict) or not params["lineas"]:
        raise ValueError("Falta 'lineas' (diccionario no vacío) en el YAML.")

    # formatos/productos
    if "formatos" not in params:
        if "productos" in params:
            params["formatos"] = params["productos"]
        else:
            raise ValueError("Falta 'formatos' (o 'productos') en parámetros YAML.")

    # turnos/horas_por_turno → opcionales (dejan de ser hard-requeridos)
    # Si están, se validan; si no, se asigna 1 para no romper nada en otros módulos.
    t = params.get("turnos", 1)
    h = params.get("horas_por_turno", 1)
    try:
        params["turnos"] = int(t)
        params["horas_por_turno"] = int(h)
        if params["turnos"] <= 0 or params["horas_por_turno"] <= 0:
            raise ValueError
    except Exception:
        raise ValueError("turnos y horas_por_turno deben ser enteros > 0 si se especifican.")

    # Validación ligera de 'lineas' (capacidad_piezas_h solo si está)
    for l, attrs in params["lineas"].items():
        if not isinstance(attrs, dict):
            raise ValueError(f"'lineas.{l}' debe ser un diccionario.")
        # no exigimos 'capacidad_piezas_h' (el modelo real usa 'mj')

    # Defaults GUI
    params.setdefault("formatos_caja", ["10lb", "12lb", "15lb", "25lb", "35lb", "55lb", "70lb"])
    params.setdefault("areas_empaque", ["Área 4", "Fresco", "Congelado"])

    # Compatibilidad empaque: si falta, permitir todas las áreas por producto
    compat_emp = params.get("compatibilidad_empaque")
    if compat_emp is None:
        compat_emp = {p: list(params["areas_empaque"]) for p in params["formatos"]}
        params["compatibilidad_empaque"] = compat_emp
    else:
        for p in params["formatos"]:
            if p not in compat_emp:
                raise ValueError(f"Falta compatibilidad_empaque para el producto '{p}'.")
            invalid = [a for a in compat_emp[p] if a not in params["areas_empaque"]]
            if invalid:
                raise ValueError(f"Áreas de empaque inválidas para '{p}': {invalid}. Deben estar en areas_empaque.")

    # NO volver a exigir 'capacidad_empaque_cajas_h' (se usa 'ne' en el modelo real)
    return params
