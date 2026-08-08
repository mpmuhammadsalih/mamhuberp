from __future__ import annotations

from starlette.requests import Request


def inject_flask_route_names(request: Request) -> None:
    """Populate ``request.state.flask_*`` for permission checks (Flask-compatible strings)."""
    route = request.scope.get("route")
    bp = None
    ep = None
    if route is not None:
        name = getattr(route, "name", None) or ""
        if "__" in name:
            bp, _, ep = name.partition("__")
        elif name:
            ep = name
    request.state.flask_blueprint = bp
    request.state.flask_endpoint = f"{bp}.{ep}" if bp and ep else (ep or None)
