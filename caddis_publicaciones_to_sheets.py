# -*- coding: utf-8 -*-
"""
Extrae las publicaciones (listados por tienda) del ERP Caddis y las vuelca en
Google Sheets en formato tabla plana.

Pensado para un Cloud Run Job con Workload Identity Federation, disparado por
GitHub Actions.

Variables de entorno (Cloud Run):
  SPREADSHEET_ID            → ID de la planilla destino
  WORKLOAD_IDENTITY_PROVIDER→ Provider WIF (para compatibilidad, aunque el
                               script usa `google.auth.default()`)
  SHEET_NAME (opcional)     → Pestaña destino, por defecto "publicaciones"
"""

import os
import sys
from datetime import datetime
from typing import List, Dict

import requests
import gspread
from google.auth import default  # Credenciales vía WIF

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
API_URL = "https://api.caddis.com.ar/v1"
CREDENTIALS = {
    "usuario": "GPSMUNDO-TEST",
    "password": "875c471f5ad0b48114193d35f3ef45f6",
}

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
# Helpers de entorno y login
# ---------------------------------------------------------------------------

def _validate_env() -> Dict[str, str]:
    req = {
        "SPREADSHEET_ID": "ID de la planilla destino",
    }
    missing = [k for k in req if not os.getenv(k)]
    if missing:
        print("Faltan env vars requeridas:", ", ".join(missing))
        sys.exit(1)
    return {
        "spreadsheet_id": os.getenv("SPREADSHEET_ID"),
        "sheet_name": os.getenv("SHEET_NAME", "publicaciones"),
    }


def _login() -> str:
    print("▶ Login Caddis …")
    r = requests.post(f"{API_URL}/login", json=CREDENTIALS, timeout=30)
    r.raise_for_status()
    token = r.json()["body"]["access_token"]
    print("✔ Token OK")
    return token

# ---------------------------------------------------------------------------
# Descarga de publicaciones con paginación
# ---------------------------------------------------------------------------

def _fetch_publicaciones(token: str) -> List[Dict]:
    print("▶ Descargando publicaciones …")
    headers = {"Authorization": f"Bearer {token}"}
    page = 1
    registros: List[Dict] = []

    while True:
        url = f"{API_URL}/ecommerce/publicaciones?pagina={page}"
        r = requests.get(url, headers=headers, timeout=60)

        if r.status_code == 404:
            print(f"  • Página {page} 404 ⇒ fin de paginación.")
            break
        if r.status_code >= 400:
            print(f"✖ Error {r.status_code}: {r.text}")
            r.raise_for_status()

        data = r.json().get("body", [])
        if not data:
            print(f"  • Página {page} vacía ⇒ fin de paginación.")
            break

        registros.extend(data)
        print(f"  • Página {page}: {len(data)} SKUs (acum: {len(registros)})")
        page += 1

    return registros

# ---------------------------------------------------------------------------
# Transformación a filas para Sheets
# ---------------------------------------------------------------------------

def _flatten(raw: List[Dict]) -> List[List]:
    ts = datetime.utcnow().isoformat(sep="T", timespec="seconds")
    rows: List[List] = []
    for art in raw:
        sku = art["sku"]
        for pub in art.get("publicaciones", []):
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
# Escritura en Google Sheets
# ---------------------------------------------------------------------------

def _write(rows: List[List], cfg: Dict[str, str]):
    print("▶ Conectando a Google Sheets …")
    creds, _ = default()
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(cfg["spreadsheet_id"])

    try:
        ws = ss.worksheet(cfg["sheet_name"])
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=cfg["sheet_name"], rows="1", cols=str(len(HEADER)))

    ws.clear()
    ws.append_rows([HEADER] + rows, value_input_option="USER_ENTERED")
    print(f"✔ Hoja '{ws.title}' actualizada ({len(rows)} filas).")

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    print("=== Publicaciones → Sheets ===", datetime.utcnow().isoformat())
    cfg = _validate_env()
    token = _login()
    raw = _fetch_publicaciones(token)
    rows = _flatten(raw)
    _write(rows, cfg)
    print("=== Proceso completado OK ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("✖ Error fatal:", exc)
        sys.exit(1)
