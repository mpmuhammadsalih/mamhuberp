#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
export PYTHONPATH=.
# Bind loopback only — nginx proxies https://whatsapp.mamahub.store → 127.0.0.1:8090
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8090
