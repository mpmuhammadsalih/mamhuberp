import asyncio
import logging
import html as html_escape
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from config.bootstrap_env import bootstrap_dotenv
bootstrap_dotenv()
from addons.register import register_addon_routers
from config.settings import is_multi_db_mode
from database_setup import bp as database_setup_router
from db import bootstrap_application_schema, get_location_info_by_dbkey, get_user_allowed_tenant_ids, get_user_multilocations_view, get_tenant_list, warm_sales_save_caches
from nexa_http import context as ctx
from nexa_http.lifecycle import http403_handler, nexa_security_after_route_match
from nexa_http.middleware import NexaHttpMiddleware
from nexa_http.templates_m import init_templates, register_context_processor
from save_nonce import get_or_issue_global_save_nonce, get_or_issue_pos_save_nonce

def _setup_file_logging(app: FastAPI) -> None:
    logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, 'app.log')
    log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(log_formatter)
    app.state.logger = logging.getLogger('nexa')
    app.state.logger.setLevel(logging.INFO)
    app.state.logger.addHandler(file_handler)
    logging.getLogger('uvicorn.error').addHandler(file_handler)
    grn_save_logger = logging.getLogger('nexa.grn_save')
    grn_save_logger.setLevel(logging.INFO)
    grn_save_logger.handlers.clear()
    grn_handler = RotatingFileHandler(os.path.join(logs_dir, 'grn_save.log'), maxBytes=5 * 1024 * 1024, backupCount=10, encoding='utf-8')
    grn_handler.setLevel(logging.INFO)
    grn_handler.setFormatter(log_formatter)
    grn_save_logger.addHandler(grn_handler)
    grn_save_logger.propagate = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    log = app.state.logger
    loop = asyncio.get_running_loop()
    bootstrap_blocking = (os.getenv('BOOTSTRAP_BLOCKING') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    bootstrap_timeout = float(os.getenv('BOOTSTRAP_STARTUP_TIMEOUT') or '90')

    def _bootstrap_sync() -> None:
        bootstrap_application_schema(app)

    def _audit_sync() -> None:
        from addons.transaction_recording_audit.controllers.routes import run_startup_maintenance
        run_startup_maintenance(getattr(app.state, 'root_path', None))

    async def _run_bootstrap() -> None:
        await loop.run_in_executor(None, _bootstrap_sync)

    async def _run_audit_maintenance() -> None:
        await loop.run_in_executor(None, _audit_sync)

    if bootstrap_blocking:
        try:
            await asyncio.wait_for(_run_bootstrap(), timeout=bootstrap_timeout)
        except asyncio.TimeoutError:
            log.warning(
                'Database bootstrap timed out after %ss — app starting anyway (check Oracle / ORACLE_TCP_CONNECT_TIMEOUT)',
                bootstrap_timeout,
            )
        except Exception as e:
            log.warning('Database bootstrap skipped or failed (configure DB at /database-setup): %s', e)
        try:
            await asyncio.wait_for(_run_audit_maintenance(), timeout=30.0)
        except asyncio.TimeoutError:
            log.warning('Transaction recording audit startup maintenance timed out — continuing')
        except Exception as e:
            log.warning('Transaction recording audit startup maintenance skipped: %s', e)
        try:
            await loop.run_in_executor(None, warm_sales_save_caches)
        except Exception as e:
            log.warning('Sales save cache warm skipped: %s', e)
    else:
        def _bg(label: str, fn) -> None:
            try:
                fn()
            except Exception as e:
                log.warning('%s skipped or failed: %s', label, e)

        loop.run_in_executor(None, lambda: _bg('Database bootstrap', _bootstrap_sync))
        loop.run_in_executor(None, lambda: _bg('Transaction recording audit startup maintenance', _audit_sync))
        loop.run_in_executor(None, lambda: _bg('Sales save cache warm', warm_sales_save_caches))
    yield

def create_app() -> FastAPI:
    root = Path(__file__).resolve().parent
    app = FastAPI(title='Nexus Erp', lifespan=lifespan, dependencies=[Depends(nexa_security_after_route_match)])
    _setup_file_logging(app)
    ctx.set_current_app(app)
    ctx.install_root_application(app)
    app.state.instance_path = str(root / 'instance')
    app.state.root_path = str(root)
    secret = os.getenv('FLASK_SECRET_KEY', 'change-me')
    app.add_middleware(NexaHttpMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=secret, max_age=int(timedelta(hours=8).total_seconds()), same_site='lax', https_only=False)
    app.include_router(database_setup_router)

    @register_context_processor
    def inject_location_name():
        from nexa_http.session_wrap import session
        location_name = session.get('location_name', '')
        location_code = session.get('location_code')
        if session.get('user') and (location_name or location_code is not None):
            # Location is set at login; skip a cloud DB round-trip on every page.
            pass
        elif session.get('user'):
            try:
                location_info = get_location_info_by_dbkey(None)
                if location_info:
                    if not location_name:
                        location_name = location_info.get('locationname', '') or ''
                        if location_name:
                            session['location_name'] = location_name
                    loc_code = location_info.get('locationcode')
                    if loc_code is not None:
                        try:
                            location_code = int(loc_code) if isinstance(loc_code, (int, float)) else int(float(str(loc_code).strip()))
                        except (ValueError, TypeError):
                            location_code = loc_code
                        session['location_code'] = location_code
            except Exception as e:
                print(f'[DEBUG inject_location_name] Error fetching location: {e}')
        app_locationcode = location_code if location_code is not None else ''
        current_tenant = session.get('tenant_id') or ''
        dbkeys_list = []
        show_tenant_switcher = False
        if session.get('user') and is_multi_db_mode():
            if session.get('user') == 'admin':
                show_tenant_switcher = True
            elif get_user_multilocations_view(session.get('user')) == 'Y':
                show_tenant_switcher = True
            if show_tenant_switcher:
                try:
                    tenants = get_tenant_list()
                    u = session.get('user') or ''
                    if u and str(u).strip().lower() != 'admin':
                        allowed = get_user_allowed_tenant_ids(u)
                        if allowed:
                            allow_l = {a.lower() for a in allowed}
                            tenants = [t for t in tenants if str(t.get('tenant_id') or '').strip().lower() in allow_l]
                    dbkeys_list = [{'code': t.get('tenant_id') or '', 'name': t.get('display_name') or t.get('tenant_id') or ''} for t in tenants]
                except Exception:
                    dbkeys_list = []
        return {'location_name': location_name, 'location_code': location_code, 'dbkeys_list': dbkeys_list, 'current_dbkey': current_tenant, 'app_dbkey': current_tenant, 'app_locationcode': app_locationcode, 'show_tenant_switcher': show_tenant_switcher, 'is_admin_user': str(session.get('user') or '').strip().lower() == 'admin'}

    @register_context_processor
    def inject_global_save_nonce():
        from nexa_http.session_wrap import session
        if not session.get('user'):
            return {'global_save_nonce': '', 'pos_save_nonce': ''}
        try:
            return {'global_save_nonce': get_or_issue_global_save_nonce(), 'pos_save_nonce': get_or_issue_pos_save_nonce()}
        except Exception:
            return {'global_save_nonce': '', 'pos_save_nonce': ''}

    @register_context_processor
    def inject_menu_permissions():
        from nexa_http.session_wrap import session
        from nexa_http.layout_cache import get_layout_cache
        user = session.get('user')
        if not user:
            return {
                'menu_permissions': [],
                'allow_all_permissions': False,
                'has_menu_permission': lambda menu_path: False,
                'has_any_menu_permission': lambda menu_paths: False,
                'quick_access_items': [],
                'outstanding_due_count': 0,
                'user_transit_only': False,
                'user_customer_creation': False,
                'cr_alert_poll_enabled': True,
                'tx_recording_enabled': True,
                'is_pdt_user': False,
            }
        cached = get_layout_cache(session, user)
        if cached:
            menu_permissions = list(cached.get('menu_permissions') or [])
            quick_access_paths = list(cached.get('quick_access_paths') or [])
            allow_all_permissions = bool(cached.get('allow_all_permissions'))
            outstanding_due_count = int(cached.get('outstanding_due_count') or 0)
            user_transit_only = bool(cached.get('user_transit_only'))
            user_customer_creation = bool(cached.get('user_customer_creation'))
            cr_alert_poll_enabled = bool(cached.get('cr_alert_poll_enabled', True))
            tx_recording_enabled = bool(cached.get('tx_recording_enabled', True))
        else:
            menu_permissions = []
            quick_access_paths = []
            allow_all_permissions = str(user or '').strip().lower() == 'admin'
            outstanding_due_count = 0
            user_transit_only = False
            user_customer_creation = False
            cr_alert_poll_enabled = True
            tx_recording_enabled = True

        from permissions import is_menu_path_allowed

        def has_menu_permission(menu_path: str) -> bool:
            if allow_all_permissions:
                return True
            return is_menu_path_allowed(menu_path, menu_permissions)

        def has_any_menu_permission(menu_paths) -> bool:
            if allow_all_permissions:
                return True
            return any(is_menu_path_allowed(path, menu_permissions) for path in menu_paths)
        quick_access_items = []
        try:
            from permissions import resolve_quick_access_items
            quick_access_items = resolve_quick_access_items(
                quick_access_paths,
                menu_permissions,
                allow_all=allow_all_permissions,
            )
        except Exception:
            pass
        return {
            'menu_permissions': menu_permissions,
            'allow_all_permissions': allow_all_permissions,
            'has_menu_permission': has_menu_permission,
            'has_any_menu_permission': has_any_menu_permission,
            'quick_access_items': quick_access_items,
            'outstanding_due_count': outstanding_due_count,
            'user_transit_only': user_transit_only,
            'user_customer_creation': user_customer_creation,
            'cr_alert_poll_enabled': cr_alert_poll_enabled,
            'tx_recording_enabled': tx_recording_enabled,
            'is_pdt_user': False,
        }
    register_addon_routers(app)
    from mobile_backend.bootstrap import install_mobile_api
    install_mobile_api(app)

    @app.api_route('/login', methods=['GET', 'HEAD', 'POST'], include_in_schema=False)
    async def _compat_root_login_alias(request: Request) -> RedirectResponse:
        """Auth routes live under ``/auth``; keep ``/login`` working for old bookmarks and forms."""
        if request.method == 'POST':
            return RedirectResponse(url='/auth/login', status_code=307)
        return RedirectResponse(url='/auth/login', status_code=302)

    @app.get('/favicon.ico', include_in_schema=False)
    async def _favicon() -> Response:
        """Avoid JSON ``404`` in the browser network log for every page load."""
        icon = root / 'static' / 'favicon.ico'
        if icon.is_file():
            return FileResponse(icon)
        return Response(status_code=204)

    init_templates(str(root / 'templates'))
    static_dir = root / 'static'
    if static_dir.is_dir():
        app.mount('/static', StaticFiles(directory=str(static_dir)), name='static')

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code == 403:
            return await http403_handler(request, exc)
        return await http_exception_handler(request, exc)

    @app.exception_handler(StarletteHTTPException)
    async def _starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Routing raises Starlette ``HTTPException`` (e.g. 404); FastAPI deps use a different class."""
        if exc.status_code == 403:
            return await http403_handler(request, HTTPException(status_code=403, detail=exc.detail))
        if exc.status_code == 404:
            accept = (request.headers.get('accept') or '').lower()
            path = request.url.path or ''
            api_like = path.startswith('/api') or '/api/' in path
            if not api_like and 'text/html' in accept:
                home = (request.scope.get('root_path') or '').rstrip('/') + '/'
                return HTMLResponse(
                    '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Not found</title></head><body>'
                    '<h1>Page not found</h1><p>No route for <code>'
                    + html_escape.escape(path)
                    + '</code>.</p><p><a href="'
                    + html_escape.escape(home or '/')
                    + '">Home</a> · <a href="/auth/login">Sign in</a> · <a href="/dashboard">Dashboard</a></p></body></html>',
                    status_code=404,
                )
        return await http_exception_handler(request, HTTPException(status_code=exc.status_code, detail=exc.detail))
    return app
app = create_app()
if __name__ == '__main__':
    import uvicorn
    _port_raw = (os.getenv('FLASK_PORT') or os.getenv('PORT') or '5002').strip()
    try:
        port = int(_port_raw)
    except ValueError:
        port = 5002
    from nexa_http.network_util import resolve_lan_ip

    local_ip = resolve_lan_ip()
    print(f'\n  App running on:')
    print(f'    http://127.0.0.1:{port}')
    print(f'    http://{local_ip}:{port}  (network)\n')
    _reload = (os.getenv('NEXA_UVICORN_RELOAD') or '0').strip().lower() in ('1', 'true', 'yes', 'on')
    uvicorn.run('app:app', host='0.0.0.0', port=port, reload=_reload)
