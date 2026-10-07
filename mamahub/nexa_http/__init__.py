"""Flask-like helpers on top of FastAPI / Starlette (request, session, Blueprint → APIRouter)."""

from nexa_http.blueprint import Blueprint
from nexa_http.current_app_proxy import current_app
from nexa_http.context import (
    app_context,
    get_current_app,
    get_current_request,
    g,
    has_request_context,
    set_current_app,
)
from nexa_http.flash import flash, get_flashed_messages
from nexa_http.request_wrap import request
from nexa_http.responses import Response, jsonify, send_file
from nexa_http.session_wrap import session
from nexa_http.shortcuts import abort, redirect, stream_with_context, url_for
from nexa_http.templates_m import render_template

__all__ = [
    "Blueprint",
    "abort",
    "current_app",
    "app_context",
    "flash",
    "g",
    "get_current_app",
    "get_current_request",
    "get_flashed_messages",
    "has_request_context",
    "jsonify",
    "redirect",
    "render_template",
    "request",
    "Response",
    "send_file",
    "session",
    "set_current_app",
    "stream_with_context",
    "url_for",
]
