#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../frontend"
exec npm run dev -- --port 3090 --hostname 127.0.0.1
