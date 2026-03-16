# TAG Report Service

Servicio web que genera reportes PDF de gastos TAG para AWS.

## Setup en Render.com

1. Sube esta carpeta a un repositorio GitHub (público o privado)
2. En Render.com: New → Web Service → conecta tu repo
3. Configuración:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
   - Plan: Free

## Endpoint

POST /generar-reporte

Parámetros (multipart/form-data):
- csv_files: archivos CSV de las concesionarias
- fechas_visita: "09-03-2026,12-03-2026"
- semana: "09/03/2026 - 13/03/2026"

Respuesta JSON:
- pdf_base64: PDF en base64
- total: monto total
- total_formateado: "$22.259"
- filename: nombre sugerido del archivo

flask-cors==4.0.0
