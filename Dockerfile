# syntax=docker/dockerfile:1

FROM python:3.11-slim

# Dependencias de sistema mínimas para compilar algunas libs de Python
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Crear usuario no root para ejecutar el contenedor
RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

# Copiamos requirements primero para aprovechar la caché
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el script principal
COPY caddis_publicaciones_to_sheets.py .

USER app
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-u", "caddis_publicaciones_to_sheets.py"]