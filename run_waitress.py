"""Production entry: Waitress (WSGI) + ASGI adapter for the FastAPI app."""
import os

from a2wsgi import ASGIMiddleware
from waitress import serve

from config.bootstrap_env import bootstrap_dotenv

from nexa_http.network_util import resolve_lan_ip

bootstrap_dotenv()

from app import app  # noqa: E402

_port_raw = (os.getenv("FLASK_PORT") or os.getenv("PORT") or "5051").strip()
try:
    port = int(_port_raw)
except ValueError:
    port = 5051

local_ip = resolve_lan_ip()

print("\n  Waitress serving Nexus (ASGI via a2wsgi):")
print(f"    http://127.0.0.1:{port}")
print(f"    http://{local_ip}:{port}  (network)\n")

serve(
    ASGIMiddleware(app),
    host="0.0.0.0",
    port=port,
    threads=8,
    expose_tracebacks=True,
)
