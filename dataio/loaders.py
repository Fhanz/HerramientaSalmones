import pandas as pd, yaml

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

    requeridos_base = ("lineas", "turnos", "horas_por_turno",
                       "compatibilidad", "capacidad_empaque_cajas_h", "piezas_por_caja")
    for k in requeridos_base:
        if k not in params:
            raise ValueError(f"Falta '{k}' en parámetros YAML.")

    if "formatos" not in params:
        if "productos" in params:
            params["formatos"] = params["productos"]
        else:
            raise ValueError("Falta 'formatos' (o 'productos') en parámetros YAML.")

    if int(params["turnos"]) <= 0 or int(params["horas_por_turno"]) <= 0:
        raise ValueError("turnos y horas_por_turno deben ser enteros > 0.")
    params["turnos"] = int(params["turnos"])
    params["horas_por_turno"] = int(params["horas_por_turno"])

    if not isinstance(params["lineas"], dict) or not params["lineas"]:
        raise ValueError("'lineas' debe ser un diccionario no vacío.")
    for l, attrs in params["lineas"].items():
        if "capacidad_piezas_h" not in attrs:
            raise ValueError(f"Falta 'capacidad_piezas_h' para la línea '{l}'.")

    params.setdefault("formatos_caja", ["10lb", "12lb", "15lb", "25lb", "35lb", "55lb", "70lb"])
    params.setdefault("areas_empaque", ["Área 4", "Fresco", "Congelado"])

    # Compatibilidad de empaque (opcional pero recomendado)
    # Formato esperado: { producto: [areas permitidas...] }
    compat_emp = params.get("compatibilidad_empaque")
    if compat_emp is None:
        # Si no está, por defecto todos los productos pueden ir a cualquier área
        compat_emp = {p: list(params["areas_empaque"]) for p in params["formatos"]}
        params["compatibilidad_empaque"] = compat_emp
    else:
        # Validación básica de claves
        for p in params["formatos"]:
            if p not in compat_emp:
                raise ValueError(f"Falta compatibilidad_empaque para el producto '{p}'.")
            # Chequear que las áreas declaradas existan en areas_empaque
            invalid = [a for a in compat_emp[p] if a not in params["areas_empaque"]]
            if invalid:
                raise ValueError(f"Áreas de empaque inválidas para '{p}': {invalid}. Deben estar en areas_empaque.")

    return params
