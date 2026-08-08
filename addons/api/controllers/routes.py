"""API blueprint - handles all API endpoints"""
from pathlib import Path
from nexa_http import Blueprint, jsonify, request, session
from db import verify_user, get_location_info_by_dbkey, get_user_employeecode, get_user_tenant_id, get_customers_list, get_salesmen_for_customer, create_user, get_categories, get_departments_by_maincategory_code, get_categories_by_department_code, get_suppliers, update_user_role
from global_lookup import LOOKUP_KINDS, apply_session_db_connection, search_lookup
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('api', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

@bp.route('/api/login', methods=['POST'])
def api_login():
    """API endpoint for login"""
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password required'}, 400)
    if verify_user(username, password):
        from config.settings import is_multi_db_mode
        from db import PRIVILEGED_USERS
        if is_multi_db_mode() and username not in PRIVILEGED_USERS:
            tenant_id = get_user_tenant_id(username)
            if not tenant_id:
                return jsonify({'success': False, 'error': 'No tenant assigned. Please contact IT.'}, 403)
        session.clear()
        session.permanent = True
        session['user'] = username
        session['employeecode'] = get_user_employeecode(username)
        tenant_id = get_user_tenant_id(username) if is_multi_db_mode() else None
        if tenant_id:
            session['tenant_id'] = tenant_id
            try:
                from nexa_http import g
                g.current_tenant_id = tenant_id
            except RuntimeError:
                pass
        try:
            loc_info = get_location_info_by_dbkey(None)
            if loc_info and loc_info.get('locationcode') is not None:
                session['location_code'] = loc_info['locationcode']
            if loc_info and loc_info.get('locationname'):
                session['location_name'] = loc_info['locationname']
        except Exception:
            pass
        return jsonify({'success': True, 'user': username, 'location_code': session.get('location_code'), 'tenant_id': session.get('tenant_id')})
    return jsonify({'success': False, 'error': 'Invalid username or password'}, 401)

@bp.route('/api/logout', methods=['POST'])
def api_logout():
    """API endpoint for logout"""
    session.clear()
    return jsonify({'success': True})

@bp.route('/api/customers', methods=['GET'])
def api_customers():
    """API endpoint for customers list"""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    try:
        customers = get_customers_list()
        return jsonify({'success': True, 'data': customers})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/api/lookup/<kind>', methods=['GET'])
def global_lookup(kind: str):
    """Global typeahead search: customer, category, supplier, … Returns { success, rows: [{code, name, label}] }."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not logged in'}, 401)
    kind_norm = (kind or '').strip().lower()
    if kind_norm not in LOOKUP_KINDS:
        return jsonify({'success': False, 'error': f'Unknown lookup kind: {kind}'}, 400)
    q = (request.args.get('q') or request.args.get('search') or '').strip()
    try:
        lim = int(request.args.get('limit', 8))
    except (TypeError, ValueError):
        lim = 8
    lim = max(1, min(lim, 30))
    parent_code = (request.args.get('parent_code') or '').strip()
    try:
        apply_session_db_connection()
        rows = search_lookup(kind_norm, q, limit=lim, parent_code=parent_code)
        return jsonify({'success': True, 'rows': rows, 'kind': kind_norm})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/api/locations', methods=['GET'])
def api_locations():
    """API endpoint for locations list"""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    try:
        return jsonify({'success': True, 'data': []})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/api/locations/switch', methods=['POST'])
def api_switch_location():
    """API endpoint for switching location"""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    data = request.get_json() or {}
    location_code = data.get('locationcode', '').strip()
    return jsonify({'success': False, 'error': 'Location switching not available (single database)'}, 400)

@bp.route('/api/users', methods=['GET', 'POST'])
def api_users():
    """API endpoint for user management"""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    if request.method == 'GET':
        return jsonify({'success': True, 'data': {'username': session.get('user'), 'location_code': session.get('location_code')}})
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    employeecode = data.get('employeecode', '').strip()
    role_id = (data.get('role_id') or '').strip() or None
    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password required'}, 400)
    if not employeecode:
        return jsonify({'success': False, 'error': 'Employee Code is required'}, 400)
    if not employeecode.isdigit():
        return jsonify({'success': False, 'error': 'Employee Code must be numeric'}, 400)
    try:
        create_user(username, password, employeecode)
        if role_id:
            update_user_role(username, role_id)
        return jsonify({'success': True, 'message': 'User created successfully'})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}, 400)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/api/salesmen', methods=['GET'])
def api_salesmen():
    """API endpoint for salesmen list for a customer"""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    customer_code = request.args.get('customercode', '').strip()
    if not customer_code:
        return jsonify({'success': False, 'error': 'Customer code required'}, 400)
    try:
        salesmen = get_salesmen_for_customer(customer_code)
        return jsonify({'success': True, 'data': salesmen})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/api/location/<db_key>', methods=['GET'])
def api_get_location_by_dbkey(db_key: str):
    return jsonify({'status': 'error', 'message': 'Single database mode'}, 404)

@bp.route('/api/filters/brands', methods=['GET'])
def api_get_brands():
    """API endpoint for brands list"""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    try:
        brands = get_categories(flag='B')
        return jsonify({'success': True, 'data': brands})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/api/filters/categories', methods=['GET'])
def api_get_categories():
    """API endpoint for categories list"""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    try:
        categories = get_categories(flag='C')
        return jsonify({'success': True, 'data': categories})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/api/filters/suppliers', methods=['GET'])
def api_get_suppliers():
    """API endpoint for suppliers list"""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    try:
        suppliers = get_suppliers()
        return jsonify({'success': True, 'data': suppliers})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/api/filters/departments', methods=['GET'])
def api_get_departments():
    """
    API endpoint for departments list, optionally filtered by main category CODE.
    The maincategorycode parameter should be the Main Category's CODE.
    Filter: Department.ID = Main Category.CODE
    """
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    maincategorycode = request.args.get('maincategorycode', '').strip()
    maincategory_code_int = None
    if maincategorycode and maincategorycode.isdigit():
        maincategory_code_int = int(maincategorycode)
    try:
        if maincategory_code_int is None:
            departments = get_categories(flag='D')
        else:
            departments = get_departments_by_maincategory_code(maincategory_code_int)
        return jsonify({'success': True, 'data': departments})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/api/filters/categories-filtered', methods=['GET'])
def api_get_categories_filtered():
    """
    API endpoint for categories list, optionally filtered by department CODE.
    The departmentcode parameter should be the Department's CODE.
    Filter: Category.ID = Department.CODE
    """
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    departmentcode = request.args.get('departmentcode', '').strip()
    departmentcode_int = None
    if departmentcode and departmentcode.isdigit():
        departmentcode_int = int(departmentcode)
    try:
        if departmentcode_int is None:
            categories = get_categories(flag='C')
        else:
            categories = get_categories_by_department_code(departmentcode_int)
        return jsonify({'success': True, 'data': categories})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)
