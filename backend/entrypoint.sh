#!/bin/sh
set -e

echo "[entrypoint] Applying migrations..."
flask --app app db upgrade
if [ "${DEMO_MODE:-true}" = "true" ]; then
    flask --app app seed-demo-user
fi
flask --app app seed-sources
echo "[entrypoint] Starting gunicorn..."
exec gunicorn -w 4 --threads 4 -b 0.0.0.0:6767 --timeout 600 app:app
