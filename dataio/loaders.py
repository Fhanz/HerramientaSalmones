import pandas as pd, yaml
from pathlib import Path
import csv
from typing import Dict, Any, Tuple

# =========================
# Calibres
# =========================
C_MAP_DEFAULT: Dict[int, str] = {
    0: "1-2", 1: "2-3", 2: "3-4", 3: "4-5", 4: "5-6",
    5: "6-7", 6: "7-8", 7: "8-9", 8: "9-10", 9: "10-11",
    10: "11-12", 11: "12-13", 12: "13-14", 13: "14+"
}

def _normalize_cmap(cmap: Dict[int, str] | Dict[str, str] | None) -> Dict[int, str]:
    """Devuelve un C_map con claves enteras 0..13 y etiquetas válidas."""
    base = dict(C_MAP_DEFAULT)
    if not isinstance(cmap, dict):
        return base
    # normaliza claves a int
    for k, v in cmap.items():
        try:
            ki = int(k)
        except Exception:
            continue
        if 0 <= ki <= 13 and isinstance(v, str) and v.strip():
            base[ki] = v.strip()
    return dict(sorted(base.items(), key=lambda kv: kv[0]))

def _to_idx_from_label(label: str, cmap: Dict[int, str]) -> int:
    inv = {v: k for k, v in cmap.items()}
    lab = str(label).strip()
    if lab in inv:
        return inv[lab]
    # intenta interpretar "10-11" -> buscar exacto sin espacios
    lab2 = lab.replace(" ", "")
    inv2 = {v.replace(" ", ""): k for k, v in cmap.items()}
    if lab2 in inv2:
        return inv2[lab2]
    raise ValueError(f"Etiqueta de calibre '{label}' no existe en C_map.")

# =========================
# Calibres map (csv util)
# =========================
def load_calibres_map(csv_path: str | Path | None) -> Dict[int, str]:
    """Lee CSV idx,etiqueta; si falta vuelve a default."""
    if not csv_path:
        return dict(C_MAP_DEFAULT)
    p = Path(csv_path)
    if not p.exists():
        return dict(C_MAP_DEFAULT)
    cmap: Dict[int, str] = {}
    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "idx" in row and "etiqueta" in row and str(row["idx"]).strip() != "":
                try:
                    idx = int(row["idx"])
                except Exception:
                    continue
                cmap[idx] = str(row["etiqueta"]).strip()
    return _normalize_cmap(cmap)

def save_calibres_map(csv_path: str | Path, cmap: Dict[int, str]) -> None:
    p = Path(csv_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["idx", "etiqueta"])
        writer.writeheader()
        for idx, etiqueta in _normalize_cmap(cmap).items():
            writer.writerow({"idx": idx, "etiqueta": etiqueta})

# =========================
# Demand / Availability loaders
# =========================
def load_demand(path: str | Path, params: dict) -> pd.DataFrame:
    """
    Lee un Excel/CSV de demanda.
    - Si el archivo contiene columnas de DEMANDA por (producto, formato, calibre|calibre_idx, demanda_cajas),
      entonces se calcula params['dpkc'] y se retorna un DataFrame vacío (para no tocar 'ac').
    - Si el archivo contiene columnas de DISPONIBILIDAD (calibre, salmones|piezas),
      se retorna ese DataFrame para que el optimizador pueda leer 'ac' desde GUI/pipeline.

    Columnas DEMANDA esperadas (insensible a mayúsculas):
      producto | formato | (calibre_idx OR calibre) | demanda_cajas

    Columnas DISPONIBILIDAD esperadas (insensible a mayúsculas):
      calibre | salmones  (recomendado)
      calibre | piezas    (se aceptará pero NO se usará para 'ac' en optimizer, solo para continuidad)
    """
    if not path:
        raise ValueError("Debes seleccionar archivo de demanda / disponibilidad.")
    p = Path(path)
    if not p.exists():
        raise ValueError(f"No existe el archivo: {p}")

    ext = p.suffix.lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(p)
    elif ext == ".csv":
        df = pd.read_csv(p)
    else:
        raise ValueError("Formato no soportado (usa .xlsx, .xls o .csv).")

    # normaliza encabezados
    df.columns = [c.strip().lower() for c in df.columns]

    # Detecta DEMANDA detallada
    if {"producto","formato","demanda_cajas"}.issubset(df.columns) and ("calibre_idx" in df.columns or "calibre" in df.columns):
        c_map = _normalize_cmap(params.get("C_map"))
        # asegurar calibre_idx
        if "calibre_idx" not in df.columns:
            df["calibre_idx"] = df["calibre"].astype(str).map(lambda s: _to_idx_from_label(s, c_map))
        # normaliza tipos
        df["producto"] = df["producto"].astype(str).str.strip()
        df["formato"]  = df["formato"].astype(str).str.strip()
        df["calibre_idx"] = pd.to_numeric(df["calibre_idx"], errors="coerce").astype("Int64")
        df["demanda_cajas"] = pd.to_numeric(df["demanda_cajas"], errors="coerce").fillna(0).astype(int)

        # agrega y guarda en params['dpkc']
        dpkc: Dict[tuple[str,str,int], float] = {}
        g = df.groupby(["producto","formato","calibre_idx"], dropna=True)["demanda_cajas"].sum().reset_index()
        for _, r in g.iterrows():
            p_, k_, c_ = str(r["producto"]), str(r["formato"]), int(r["calibre_idx"])
            dpkc[(p_, k_, c_)] = float(int(r["demanda_cajas"]))
        params["dpkc"] = dpkc
        # devolver DF vacío para no interferir con 'ac' (lo da el GUI)
        return pd.DataFrame()

    # Detecta DISPONIBILIDAD simple
    if "calibre" in df.columns and ("salmones" in df.columns or "piezas" in df.columns):
        # se usa tal cual; optimizer decidirá si lo ocupa o ignora
        return df.copy()

    raise ValueError("No reconozco el esquema del archivo. Esperaba:\n"
                     "  DEMANDA: producto, formato, (calibre_idx|calibre), demanda_cajas\n"
                     "  o DISPONIBILIDAD: calibre, salmones|piezas")

def load_inputs(csv_path: str | Path) -> pd.DataFrame:
    """Lee disponibilidad simple (calibre,salmones|piezas) desde CSV/Excel para 'ac'."""
    if not csv_path:
        return pd.DataFrame()
    p = Path(csv_path)
    if not p.exists():
        raise ValueError(f"No existe el archivo: {p}")
    ext = p.suffix.lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(p)
    elif ext == ".csv":
        df = pd.read_csv(p)
    else:
        raise ValueError("Formato no soportado (usa .xlsx, .xls o .csv).")
    df.columns = [c.strip().lower() for c in df.columns]
    if "calibre" not in df.columns:
        raise ValueError("Falta columna 'calibre' en el archivo de disponibilidad.")
    if "salmones" not in df.columns and "piezas" not in df.columns:
        raise ValueError("Falta columna 'salmones' o 'piezas' en el archivo de disponibilidad.")
    return df.copy()

# =========================
# Params YAML
# =========================
REQUIRED_KEYS = [
    "productos","lineas","areas_empaque","formatos_caja",
    "ukc","wc","sp","yp","qp","rpk","mj","ne"
]

def load_params(yaml_path: str | Path) -> dict:
    if not yaml_path:
        raise ValueError("Debes seleccionar el YAML de parámetros.")
    with Path(yaml_path).open("r", encoding="utf-8") as f:
        params: Dict[str, Any] = yaml.safe_load(f) or {}

    # Backcompat: si viene 'formatos' en lugar de 'productos', copiar
    if "productos" not in params and "formatos" in params and isinstance(params["formatos"], list):
        params["productos"] = list(params["formatos"])

    # Chequeos básicos
    for k in ["productos","areas_empaque","formatos_caja"]:
        if k not in params or not isinstance(params[k], list) or not params[k]:
            raise ValueError(f"Falta '{k}' (lista no vacía) en YAML.")
    if "lineas" not in params or not isinstance(params["lineas"], dict) or not params["lineas"]:
        raise ValueError("Falta 'lineas' (diccionario no vacío) en YAML.")

    # Normaliza C_map
    params["C_map"] = _normalize_cmap(params.get("C_map"))

    # Normaliza tablas numéricas esperadas
    def _as_float_dict(d: dict, name: str) -> Dict:
        if not isinstance(d, dict) or not d:
            raise ValueError(f"Falta '{name}' en YAML.")
        return { (int(k) if isinstance(k, str) and k.isdigit() else k): float(v) for k, v in d.items() }

    # ukc: dict formato -> dict calibre_idx -> int
    if "ukc" not in params or not isinstance(params["ukc"], dict):
        raise ValueError("Falta 'ukc' en YAML.")
    ukc: Dict[str, Dict[int, int]] = {}
    for k_fmt, row in params["ukc"].items():
        if not isinstance(row, dict):
            raise ValueError("Cada entrada de 'ukc' debe ser un dict calibre_idx->piezas.")
        ukc[str(k_fmt)] = { int(ci): int(val) for ci, val in row.items() }
    params["ukc"] = ukc

    # wc: dict calibre_idx -> float
    params["wc"] = { int(k): float(v) for k, v in params.get("wc", {}).items() }

    # sp/yp/qp: dict producto -> float
    for name in ["sp","yp","qp"]:
        if name not in params or not isinstance(params[name], dict):
            raise ValueError(f"Falta '{name}' en YAML.")
        params[name] = { str(p): float(v) for p, v in params[name].items() }

    # rpk: producto -> { formato -> precio }
    if "rpk" not in params or not isinstance(params["rpk"], dict):
        raise ValueError("Falta 'rpk' en YAML.")
    params["rpk"] = { str(p): { str(k): float(v) for k, v in row.items() } for p, row in params["rpk"].items() }

    # capacidades
    if "mj" not in params or not isinstance(params["mj"], dict):
        raise ValueError("Falta 'mj' (capacidad por línea) en YAML.")
    params["mj"] = { str(j): float(v) for j, v in params["mj"].items() }

    if "ne" not in params or not isinstance(params["ne"], dict):
        raise ValueError("Falta 'ne' (capacidad por área) en YAML.")
    params["ne"] = { str(e): float(v) for e, v in params["ne"].items() }

    # Compatibilidad calibre–línea: aceptar 'bcj', o 'compatibilidad_indices' (lista), o 'compatibilidad' por etiqueta
    bcj_map: Dict[Tuple[int,str], int] = {}
    if "bcj" in params and isinstance(params["bcj"], dict) and params["bcj"]:
        for key, val in params["bcj"].items():
            if isinstance(key, str) and "," in key:
                c_str, j = key.split(",", 1)
                c = int(c_str.strip())
                bcj_map[(c, str(j).strip())] = int(val)
            elif isinstance(key, (tuple, list)) and len(key) == 2:
                c, j = key
                bcj_map[(int(c), str(j))] = int(val)
    elif "compatibilidad_indices" in params and isinstance(params["compatibilidad_indices"], dict):
        for j, lst in params["compatibilidad_indices"].items():
            for c in lst:
                bcj_map[(int(c), str(j))] = 1
    elif "compatibilidad" in params and isinstance(params["compatibilidad"], dict):
        inv = {v: k for k, v in params["C_map"].items()}
        for j, labels in params["compatibilidad"].items():
            for lab in labels:
                if lab not in inv:
                    raise ValueError(f"Etiqueta de calibre '{lab}' en compatibilidad no existe en C_map.")
                bcj_map[(int(inv[lab]), str(j))] = 1
    if bcj_map:
        params["bcj"] = { f"{c},{j}": int(v) for (c,j), v in bcj_map.items() }

    # Compatibilidad producto–empaque
    compat_emp = params.get("compatibilidad_empaque")
    if compat_emp is None:
        # por defecto: todo permitido
        params["compatibilidad_empaque"] = { str(p): list(params["areas_empaque"]) for p in params["productos"] }
    else:
        fixed = {}
        for p_ in params["productos"]:
            if p_ not in compat_emp:
                raise ValueError(f"Falta compatibilidad_empaque para el producto '{p_}'.")
            fixed[str(p_)] = [str(e) for e in compat_emp[p_] if e in params["areas_empaque"]]
            if len(fixed[str(p_)]) != len(compat_emp[p_]):
                invalid = [e for e in compat_emp[p_] if e not in params["areas_empaque"]]
                raise ValueError(f"Áreas de empaque inválidas para '{p_}': {invalid}.")
        params["compatibilidad_empaque"] = fixed

    # Nunca usar 'ac' ni 'dpkc' desde YAML (vienen de GUI/Excel)
    params.pop("ac", None)
    params.pop("dpkc", None)

    return params
