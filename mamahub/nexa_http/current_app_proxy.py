from __future__ import annotations

import logging
from typing import Any

from nexa_http import context as ctx


class _CurrentApp:
    """Subset of Flask ``current_app`` used by addons (logger, paths)."""

    @property
    def logger(self) -> logging.Logger:
        app = ctx.get_current_app()
        return getattr(app.state, "logger", logging.getLogger("nexa"))

    @property
    def instance_path(self) -> str:
        app = ctx.get_current_app()
        return str(getattr(app.state, "instance_path", "") or "")

    @property
    def root_path(self) -> str:
        app = ctx.get_current_app()
        return str(getattr(app.state, "root_path", "") or "")

    def __getattr__(self, name: str) -> Any:
        return getattr(ctx.get_current_app(), name)


current_app = _CurrentApp()
