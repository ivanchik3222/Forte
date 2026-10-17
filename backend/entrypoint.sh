#!/bin/sh
set -e

echo "[entrypoint] Applying migrations..."
flask --app app db upgrade
flask --app app seed-demo-user
flask --app app seed-sources
echo "[entrypoint] Starting gunicorn..."
exec gunicorn -w 4 --threads 4 -b 0.0.0.0:6767 --timeout 600 app:app
