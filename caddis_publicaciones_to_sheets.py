# -*- coding: utf-8 -*-
"""
Extrae las publicaciones (listados por tienda) del ERP Caddis y las vuelca en una
hoja de Google Sheets con una tabla plana.  
Se autentica con Workload Identity Federation (misma lógica que tu script de
stock). Pensado para correr en un Cloud Run Job disparado por GitHub Actions.

Env vars necesarios en Cloud Run:
  SPREADSHEET_ID   → ID de la planilla destino
  WORKLOAD_IDENTITY_PROVIDER → mismo que en el job de stock
  SHEET_NAME (opcional)      → nombre de la pestaña, por defecto "publicaciones"
"""

import os
import sys
from datetime import datetime
from typing import List, Dict

import requests
import gspread
from google.auth import default  # Workload Identity Federation creds

# ---------------------------------------------------------------------------
# Configuración estática
# ---------------------------------------------------------------------------
API_URL = "https://api.caddis.com.ar/v1"
CREDENTIALS = {
    "usuario": "GPSMUNDO-TEST",
    "password": "875c471f5ad0b48114193d35f3ef45f6",
}
PAGE_LIMIT = 5000  # Caddis usa este límite en los endpoints de paginación

# Columnas del sheet en el orden que se escribirán
HEADER = [
    "sku",
    "tienda_id",
    "tienda_nombre",
    "tienda_usuario",
    "id_producto",
    "id_variante",
    "titulo",
    "estado",
    "stock",
    "precio",
    "fecha_extraccion",
]


# ---------------------------------------------------------------------------
# Utilidades de entorno y autenticación
# ---------------------------------------------------------------------------

def _validate_env() -> Dict[str, str]:
    """Asegura que existan las env vars necesarias y las devuelve."""
    required = {
        "SPREADSHEET_ID": "ID de la hoja de cálculo de destino (en la URL)",
        "WORKLOAD_IDENTITY_PROVIDER": "ID del Workload Identity Provider",
    }
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print("\nFaltan variables de entorno:")
        for k in missing:
            print(f"  {k}: {required[k]}")
        sys.exit(1)

    return {
        "spreadsheet_id": os.getenv("SPREADSHEET_ID"),
        "wip": os.getenv("WORKLOAD_IDENTITY_PROVIDER"),
        "sheet_name": os.getenv("SHEET_NAME", "publicaciones"),
    }


def _login() -> str:
    """Obtiene access_token Caddis."""
    print("▶ Iniciando login en Caddis…")
    try:
        resp = requests.post(f"{API_URL}/login", json=CREDENTIALS, timeout=30)
        resp.raise_for_status()
        token = resp.json()["body"]["access_token"]
        print("✔ Login OK")
        return token
    except requests.RequestException as err:
        print("✖ Error autenticando en Caddis:", err)
        raise


# ---------------------------------------------------------------------------
# Extracción de publicaciones
# ---------------------------------------------------------------------------

def _fetch_publicaciones(token: str) -> List[Dict]:
    """Itera páginas hasta agotar resultados y devuelve la lista plana."""
    print("▶ Descargando publicaciones… (límite página", PAGE_LIMIT, ")")
    headers = {"Authorization": f"Bearer {token}"}
    page = 1
    registros: List[Dict] = []

    while True:
        url = f"{API_URL}/articulos/publicaciones?pagina={page}&limite={PAGE_LIMIT}"
        try:
            resp = requests.get(url, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            body = data.get("body", [])
            if not body:
                print(f"  • Página {page} vacía. Fin de paginación.")
                break
            registros.extend(body)
            print(f"  • Página {page}: {len(body)} SKUs → acumulado {len(registros)}")
            page += 1
        except requests.RequestException as err:
            # Si Caddis responde 404 cuando no hay más páginas
            if getattr(err.response, "status_code", None) == 404:
                print(f"  • Página {page} devolvió 404. Fin de paginación.")
                break
            raise

    return registros


# ---------------------------------------------------------------------------
# Transformación
# ---------------------------------------------------------------------------

def _flatten(raw: List[Dict]) -> List[List]:
    """Convierte la estructura nested en filas listas para Sheets."""
    ts = datetime.utcnow().isoformat(timespec="seconds")
    rows: List[List] = []
    for item in raw:
        sku = item["sku"]
        for pub in item.get("publicaciones", []):
            rows.append([
                sku,
                pub["tienda"]["id"],
                pub["tienda"]["nombre"],
                pub["tienda"]["usuario"],
                pub["id_producto"],
                pub["id_variante"],
                pub["titulo"],
                pub["estado"],
                pub["stock"],
                pub["precio"],
                ts,
            ])
    print(f"▶ Filas generadas: {len(rows)}")
    return rows


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------

def _write_to_sheet(rows: List[List], cfg: Dict[str, str]):
    print("▶ Conectando a Google Sheets…")
    creds, _ = default()  # Workload Identity Federation
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(cfg["spreadsheet_id"])

    try:
        ws = ss.worksheet(cfg["sheet_name"])
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=cfg["sheet_name"], rows="1", cols=str(len(HEADER)))

    # Limpiar todo manteniendo el mismo worksheet
    ws.clear()
    # Escribir encabezado y datos en una sola llamada
    ws.append_rows([HEADER] + rows, value_input_option="USER_ENTERED")
    print(f"✔ Escribí {len(rows)} filas (más encabezado) en '{ws.title}'.")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    print("=== Publicaciones → Google Sheets ===")
    print("Fecha/Hora UTC:", datetime.utcnow())

    cfg = _validate_env()
    token = _login()
    raw = _fetch_publicaciones(token)
    rows = _flatten(raw)
    _write_to_sheet(rows, cfg)

    print("=== Proceso finalizado OK ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("✖ Error fatal:", exc)
        sys.exit(1)
