FROM python:3.11-slim

WORKDIR /app

# Copiar archivos de requerimientos
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY . .

USER app
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-u", "caddis_publicaciones_to_sheets.py"]