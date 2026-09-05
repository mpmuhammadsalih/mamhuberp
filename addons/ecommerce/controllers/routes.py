"""Flask routes for the ecommerce addon."""
from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path

from nexa_http import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for

from addons.ecommerce import media_db
from addons.ecommerce import orders_db
from addons.ecommerce import settings_db
from addons.ecommerce import settings_store
from addons.ecommerce import promotions_db
from addons.ecommerce.services import catalog as catalog_svc
from addons.ecommerce.services import customers as customers_svc
from addons.ecommerce.services import dashboard as dash_svc
from addons.ecommerce.services import orders as orders_svc
from addons.ecommerce.services import cms_admin as cms_svc
from addons.ecommerce.services import media as media_svc
from addons.ecommerce.services import promotions as promotions_svc
from addons.ecommerce.services import reports as reports_svc
from addons.ecommerce.services import reviews as reviews_svc
from addons.ecommerce.services import product_edit as product_edit_svc
from addons.ecommerce.services import product_images as product_images_svc
from addons.ecommerce.services import arabic_translate as arabic_translate_svc
from addons.ecommerce.services import settings as settings_svc

_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint(
    'ecommerce',
    __name__,
    url_prefix='/ecommerce',
    template_folder=str(_ADDON_ROOT / 'views' / 'templates'),
    static_folder=str(_ADDON_ROOT / 'static'),
)

ECOMMERCE_PAGES = (
    'dashboard',
    'orders',
    'products',
    'categories',
    'customers',
    'promotions',
    'reviews',
    'media',
    'cms',
    'inventory',
    'reports',
    'settings',
)


def _int_query(name: str, default: int = 1) -> int:
    raw = request.args.get(name, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


@bp.before_request
def _require_login():
    if not session.get('user'):
        return redirect(url_for('auth.login'))


@bp.route('/')
def dashboard():
    data = dash_svc.get_dashboard_data()
    return render_template(
        'ecommerce/dashboard.html',
        title='Ecommerce — Dashboard',
        **data,
    )


@bp.route('/orders')
def orders():
    page = _int_query('page', 1)
    status = (request.args.get('status') or '').strip() or None
    search = (request.args.get('q') or '').strip() or None
    data = orders_svc.list_orders_page(page=page, page_size=20, status=status, search=search)
    return render_template(
        'ecommerce/orders.html',
        title='Ecommerce — Orders',
        **data,
    )


@bp.route('/orders/<int:order_id>')
def order_detail(order_id: int):
    order = orders_svc.get_order_detail(order_id)
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('ecommerce.orders'))
    return render_template(
        'ecommerce/order_detail.html',
        title=f"Order {order.get('order_number') or order_id}",
        order=order,
        status_options=sorted(orders_db.ALLOWED_STATUSES),
    )


@bp.route('/orders/<int:order_id>/status', methods=['POST'])
def order_status(order_id: int):
    status = (request.form.get('status') or '').strip()
    notes = (request.form.get('notes') or '').strip() or None
    updated_by = session.get('user_id')
    try:
        updated_by = int(updated_by) if updated_by is not None else None
    except (TypeError, ValueError):
        updated_by = None
    ok, message = orders_svc.change_order_status(
        order_id,
        status,
        notes=notes,
        updated_by=updated_by,
    )
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.order_detail', order_id=order_id))


@bp.route('/products')
def products():
    page = _int_query('page', 1)
    search = (request.args.get('q') or '').strip()
    sort_column = (request.args.get('sort') or '').strip().lower()
    sort_order = (request.args.get('order') or '').strip().lower()
    if sort_order not in ('asc', 'desc'):
        sort_order = ''
    items, total, loc = catalog_svc.list_products(
        page=page,
        per_page=50,
        search=search or None,
        order_by=sort_column or None,
        order_direction=sort_order or None,
    )
    return render_template(
        'ecommerce/products.html',
        title='Ecommerce — Products',
        items=items,
        total=total,
        page=page,
        search=search,
        sort_column=sort_column,
        sort_order=sort_order,
        location_code=loc,
        show_all_items_on_web=settings_store.show_all_items_on_web(),
    )


@bp.route('/products/<int:item_code>', methods=['GET'])
def product_edit(item_code: int):
    product = catalog_svc.get_product_for_edit(item_code)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('ecommerce.products'))
    return render_template(
        'ecommerce/product_edit.html',
        title=f'Edit product {item_code}',
        product=product,
        back_q=(request.args.get('q') or '').strip(),
        back_page=_int_query('page', 1),
        back_sort=(request.args.get('sort') or '').strip(),
        back_order=(request.args.get('order') or '').strip(),
    )


@bp.route('/products/<int:item_code>/update', methods=['POST'])
def products_update_row(item_code: int):
    """Save product edits from the list or detail form."""
    remove_image = str(request.form.get('remove_image') or '').strip().lower() in (
        '1',
        'true',
        'yes',
        'on',
    )
    ok, message = product_edit_svc.update_product_row(
        item_code=item_code,
        item_name=request.form.get('item_name'),
        description=request.form.get('description'),
        specifications=request.form.get('specifications'),
        description_ar=request.form.get('description_ar'),
        specifications_ar=request.form.get('specifications_ar'),
        retail_price=request.form.get('retail_price'),
        offer_price=request.form.get('offer_price'),
        image_upload=request.files.get('product_image'),
        remove_image=remove_image,
        gallery_uploads=request.files.getlist('gallery_images'),
        remove_gallery_ids=request.form.getlist('remove_gallery'),
    )
    flash(message, 'message' if ok else 'error')
    return_to = (request.form.get('return_to') or '').strip().lower()
    if return_to == 'edit':
        return redirect(url_for('ecommerce.product_edit', item_code=item_code))
    page = request.form.get('page') or request.args.get('page') or 1
    sort_column = (request.form.get('sort') or request.args.get('sort') or '').strip()
    sort_order = (request.form.get('order') or request.args.get('order') or '').strip()
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    return redirect(
        url_for(
            'ecommerce.products',
            q=request.form.get('q') or request.args.get('q') or None,
            page=page if page > 1 else None,
            sort=sort_column or None,
            order=sort_order if sort_order in ('asc', 'desc') else None,
        )
    )


@bp.route('/products/<int:item_code>/translate-arabic', methods=['POST'])
def product_translate_arabic(item_code: int):
    """Translate description and/or specifications to Arabic for the edit form."""
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    payload = request.get_json(silent=True) or {}
    target = str(payload.get('target') or 'both').strip().lower()
    result: dict = {'ok': True, 'item_code': item_code}

    if target in ('description', 'both'):
        description = str(payload.get('description') or '').strip()
        if not description:
            if target == 'description':
                return jsonify({'ok': False, 'error': 'Description is empty.'}), 400
        else:
            ara, source = arabic_translate_svc.translate_to_arabic(
                description,
                context='product_description',
            )
            if not ara:
                return jsonify({'ok': False, 'error': 'Could not translate description.'}), 400
            result['description_ar'] = ara
            result['description_source'] = source

    if target in ('specifications', 'both'):
        specifications = str(payload.get('specifications') or '').strip()
        if not specifications:
            if target == 'specifications':
                return jsonify({'ok': False, 'error': 'Specifications are empty.'}), 400
        else:
            ara, source = arabic_translate_svc.translate_to_arabic(
                specifications,
                context='product_specs',
            )
            if not ara:
                return jsonify({'ok': False, 'error': 'Could not translate specifications.'}), 400
            result['specifications_ar'] = ara
            result['specifications_source'] = source

    if 'description_ar' not in result and 'specifications_ar' not in result:
        return jsonify({'ok': False, 'error': 'Nothing to translate.'}), 400

    return jsonify(result)


@bp.route('/products/web-catalog', methods=['POST'])
def products_web_catalog():
    ok, message = settings_svc.save_web_catalog_settings(request.form.to_dict())
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.products', q=request.form.get('q') or None))


@bp.route('/products/images/template.xlsx', methods=['GET'])
def products_image_import_template():
    """Download Excel template for bulk product image import."""
    try:
        from openpyxl import Workbook
    except ImportError:
        flash('Excel template requires openpyxl (pip install openpyxl).', 'error')
        return redirect(url_for('ecommerce.products'))
    wb = Workbook()
    ws = wb.active
    ws.title = 'Product Images'
    ws.append(['ItemCode', 'Barcode', 'LocationCode', 'ImageURL', 'ImageFileName', 'Image'])
    ws.append([1001, '', '', '', '', ''])
    ws.append(['', '1234567890123', '', '', 'photo-1001.jpg', ''])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f'product_images_import_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
    return Response(
        bio.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'},
    )


@bp.route('/products/images/import', methods=['POST'])
def products_image_import():
    """Bulk assign ITEMMASTER.IMAGE_PATH from Excel (+ optional ZIP of image files)."""
    excel = request.files.get('excel_file') or request.files.get('file')
    if not excel or not getattr(excel, 'filename', None):
        flash('Choose an Excel file (.xlsx).', 'error')
        return redirect(url_for('ecommerce.products', q=request.form.get('q') or None))
    fname = str(excel.filename or '').lower()
    if not fname.endswith(('.xlsx', '.xlsm')):
        flash('Please upload a .xlsx or .xlsm file.', 'error')
        return redirect(url_for('ecommerce.products', q=request.form.get('q') or None))
    excel_raw = excel.read()
    if not isinstance(excel_raw, bytes):
        excel_raw = bytes(excel_raw) if excel_raw else b''

    zip_raw = b''
    zip_file = request.files.get('images_zip')
    if zip_file and getattr(zip_file, 'filename', None):
        zip_name = str(zip_file.filename or '').lower()
        if zip_name.endswith('.zip'):
            zip_raw = zip_file.read()
            if not isinstance(zip_raw, bytes):
                zip_raw = bytes(zip_raw) if zip_raw else b''

    download_urls = str(request.form.get('download_urls') or '1').strip().lower() in ('1', 'true', 'yes', 'on')
    result = product_images_svc.import_product_images_from_excel(
        excel_raw,
        zip_raw=zip_raw or None,
        download_urls=download_urls,
    )
    if not result.get('ok'):
        flash(result.get('error') or result.get('message') or 'Import failed.', 'error')
        return redirect(url_for('ecommerce.products', q=request.form.get('q') or None))

    message = str(result.get('message') or 'Import completed.')
    errs = result.get('errors') or []
    if errs:
        preview = '; '.join(errs[:3])
        if len(errs) > 3:
            preview += f' … and {len(errs) - 3} more'
        message = f'{message}. {preview}'
    flash(message, 'message' if result.get('partial') or result.get('updated') else 'warning')
    return redirect(url_for('ecommerce.products', q=request.form.get('q') or None))


@bp.route('/products/images/fetch-web', methods=['POST'])
def products_image_fetch_web():
    """Fetch product images from the web for items missing IMAGE_PATH."""
    try:
        limit = int(request.form.get('limit') or 25)
    except (TypeError, ValueError):
        limit = 25
    download_images = str(request.form.get('download_images') or '1').strip().lower() in ('1', 'true', 'yes', 'on')
    result = product_images_svc.fetch_missing_product_images_from_web(
        limit=limit,
        download_images=download_images,
    )
    if not result.get('ok') and not result.get('updated'):
        flash(result.get('error') or result.get('message') or 'Web fetch failed.', 'error')
        return redirect(url_for('ecommerce.products', q=request.form.get('q') or None))

    message = str(result.get('message') or 'Web fetch completed.')
    errs = result.get('errors') or []
    if errs and result.get('failed'):
        preview = '; '.join(errs[:3])
        if len(errs) > 3:
            preview += f' … and {len(errs) - 3} more'
        message = f'{message}. {preview}'
    flash(message, 'message' if result.get('updated') else 'warning')
    return redirect(url_for('ecommerce.products', q=request.form.get('q') or None))


@bp.route('/products/<int:item_code>/fetch-image-web', methods=['POST'])
def products_item_fetch_image_web(item_code: int):
    """Fetch a web image for one product row (JSON for inline table button)."""
    download_images = str(request.form.get('download_images') or '1').strip().lower() in (
        '1', 'true', 'yes', 'on',
    )
    result = product_images_svc.fetch_product_image_from_web(
        item_code=item_code,
        download_images=download_images,
    )
    wants_json = (
        'application/json' in (request.headers.get('Accept') or '').lower()
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    )
    if wants_json:
        status = 200 if result.get('ok') else 422
        return Response(
            json.dumps(result, default=str),
            status=status,
            mimetype='application/json',
        )
    if not result.get('ok'):
        flash(result.get('error') or result.get('message') or 'Web fetch failed.', 'error')
    else:
        flash(result.get('message') or 'Image fetched.', 'message')
    return redirect(url_for('ecommerce.products', q=request.form.get('q') or request.args.get('q') or None))


@bp.route('/categories')
def categories():
    tree, loc = catalog_svc.get_category_tree()
    return render_template(
        'ecommerce/categories.html',
        title='Ecommerce — Categories',
        tree=tree,
        location_code=loc,
        itemmaster_categories_url=url_for('itemmaster.category_master_list'),
    )


@bp.route('/customers')
def customers():
    page = _int_query('page', 1)
    search = (request.args.get('q') or '').strip() or None
    data = customers_svc.list_customers_page(page=page, page_size=20, search=search)
    return render_template(
        'ecommerce/customers.html',
        title='Ecommerce — Customers',
        **data,
    )


@bp.route('/customers/<int:user_id>')
def customer_detail(user_id: int):
    customer = customers_svc.get_customer_detail(user_id)
    if not customer:
        flash('Customer not found.', 'error')
        return redirect(url_for('ecommerce.customers'))
    return render_template(
        'ecommerce/customer_detail.html',
        title=f"Customer {customer.get('first_name')} {customer.get('last_name')}",
        customer=customer,
    )


@bp.route('/customers/<int:user_id>/status', methods=['POST'])
def customer_status(user_id: int):
    status = (request.form.get('status') or '').strip()
    ok, message = customers_svc.change_customer_account_status(user_id, status)
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.customer_detail', user_id=user_id))


@bp.route('/promotions')
def promotions():
    search = (request.args.get('q') or '').strip() or None
    data = promotions_svc.list_promotions_page(search=search)
    return render_template(
        'ecommerce/promotions.html',
        title='Ecommerce — Promotions',
        **data,
    )


@bp.route('/promotions/new', methods=['GET', 'POST'])
def promotion_new():
    if request.method == 'POST':
        ok, message = promotions_svc.create_promotion(request.form)
        flash(message, 'message' if ok else 'error')
        if ok:
            return redirect(url_for('ecommerce.promotions'))
    form = promotions_svc.get_create_form()
    if request.method == 'POST':
        form = {**form, **request.form.to_dict()}
    return render_template(
        'ecommerce/promotion_form.html',
        title='New promotion',
        mode='create',
        form=form,
        promotion_types=sorted(promotions_db.PROMOTION_TYPES),
    )


@bp.route('/promotions/<int:promotion_id>/edit', methods=['GET', 'POST'])
def promotion_edit(promotion_id: int):
    if request.method == 'POST':
        ok, message = promotions_svc.update_promotion(promotion_id, request.form)
        flash(message, 'message' if ok else 'error')
        if ok:
            return redirect(url_for('ecommerce.promotions'))
    form = promotions_svc.get_edit_form(promotion_id)
    if not form:
        flash('Promotion not found.', 'error')
        return redirect(url_for('ecommerce.promotions'))
    if request.method == 'POST':
        form = {**form, **request.form.to_dict()}
    return render_template(
        'ecommerce/promotion_form.html',
        title=f"Edit {form.get('coupon_code')}",
        mode='edit',
        form=form,
        promotion_types=sorted(promotions_db.PROMOTION_TYPES),
    )


@bp.route('/promotions/<int:promotion_id>/toggle', methods=['POST'])
def promotion_toggle(promotion_id: int):
    ok, message = promotions_svc.toggle_promotion(promotion_id)
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.promotions'))


@bp.route('/reviews')
def reviews():
    page = _int_query('page', 1)
    status = request.args.get('status', 'PENDING')
    search = (request.args.get('q') or '').strip() or None
    data = reviews_svc.list_reviews_page(
        page=page,
        page_size=20,
        status=status,
        search=search,
    )
    return render_template(
        'ecommerce/reviews.html',
        title='Ecommerce — Reviews',
        **data,
    )


@bp.route('/reviews/<int:review_id>/status', methods=['POST'])
def review_status(review_id: int):
    status = (request.form.get('status') or '').strip()
    ok, message = reviews_svc.moderate_review(review_id, status)
    flash(message, 'message' if ok else 'error')
    return redirect(request.referrer or url_for('ecommerce.reviews'))


@bp.route('/media/search-from-web', methods=['POST'])
def media_search_from_web():
    """Search the web for multiple image options by title (JSON for media form)."""
    payload = request.get_json(silent=True) or request.form
    title = (payload.get('title') or '').strip()
    subtitle = (payload.get('subtitle') or '').strip()
    ref_key = (payload.get('ref_key') or '').strip()
    placement = (payload.get('placement') or '').strip()
    result = media_svc.search_images_from_web_by_title(
        title,
        subtitle=subtitle,
        ref_key=ref_key,
        placement=placement,
    )
    wants_json = (
        'application/json' in (request.headers.get('Accept') or '').lower()
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    )
    if wants_json:
        status = 200 if result.get('ok') else 422
        return Response(
            json.dumps(result, default=str),
            status=status,
            mimetype='application/json',
        )
    if not result.get('ok'):
        flash(result.get('error') or result.get('message') or 'Web search failed.', 'error')
    else:
        flash(result.get('message') or 'Images found.', 'message')
    return redirect(request.referrer or url_for('ecommerce.media'))


@bp.route('/media/fetch-from-web', methods=['POST'])
def media_fetch_from_web():
    """Download a chosen web image into storefront media (JSON for media form)."""
    payload = request.get_json(silent=True) or request.form
    title = (payload.get('title') or '').strip()
    subtitle = (payload.get('subtitle') or '').strip()
    ref_key = (payload.get('ref_key') or '').strip()
    placement = (payload.get('placement') or '').strip()
    source_url = (payload.get('source_url') or '').strip()
    result = media_svc.fetch_image_from_web_by_title(
        title,
        subtitle=subtitle,
        ref_key=ref_key,
        placement=placement,
        source_url=source_url or None,
    )
    wants_json = (
        'application/json' in (request.headers.get('Accept') or '').lower()
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    )
    if wants_json:
        status = 200 if result.get('ok') else 422
        return Response(
            json.dumps(result, default=str),
            status=status,
            mimetype='application/json',
        )
    if not result.get('ok'):
        flash(result.get('error') or result.get('message') or 'Web fetch failed.', 'error')
    else:
        flash(result.get('message') or 'Image fetched.', 'message')
    return redirect(request.referrer or url_for('ecommerce.media'))


@bp.route('/media')
def media():
    placement = (request.args.get('placement') or '').strip() or None
    data = media_svc.list_media_page(placement=placement)
    return render_template(
        'ecommerce/media.html',
        title='Ecommerce — Media',
        **data,
    )


@bp.route('/media/logo', methods=['GET', 'POST'])
def media_logo():
    logo_rows, _ = media_db.list_media(placement='storefront_logo', active_only=False)
    logo_item = logo_rows[0] if logo_rows else None
    if request.method == 'POST':
        ok, message = media_svc.save_storefront_logo(
            request.form.to_dict(),
            file_storage=request.files.get('image_file'),
        )
        flash(message, 'message' if ok else 'error')
        if ok:
            return redirect(url_for('ecommerce.media'))
    form = media_svc.media_to_form(logo_item) if logo_item else {
        **media_svc.get_create_form(),
        'placement': 'storefront_logo',
        'ref_key': 'header',
        'title': 'MamaHub logo',
        'alt_text': 'MamaHub',
    }
    if request.method == 'POST':
        form = {**form, **request.form.to_dict()}
    return render_template(
        'ecommerce/media_logo.html',
        title='Storefront logo',
        form=form,
        logo_item=logo_item,
    )


@bp.route('/media/new', methods=['GET', 'POST'])
def media_new():
    if request.method == 'POST':
        ok, message = media_svc.save_media(
            request.form.to_dict(),
            file_storage=request.files.get('image_file'),
            poster_storage=request.files.get('poster_file'),
        )
        flash(message, 'message' if ok else 'error')
        if ok:
            return redirect(url_for('ecommerce.media'))
    form = media_svc.get_create_form()
    if request.method == 'GET':
        q_placement = (request.args.get('placement') or '').strip()
        if q_placement in media_db.PLACEMENTS:
            form = {**form, 'placement': q_placement}
        q_ref = (request.args.get('ref_key') or '').strip()
        if q_ref:
            form = {**form, 'ref_key': q_ref}
        q_title = (request.args.get('title') or '').strip()
        if q_title:
            form = {**form, 'title': q_title}
    if request.method == 'POST':
        form = {**form, **request.form.to_dict()}
    return render_template(
        'ecommerce/media_form.html',
        title='New media',
        form=form,
        placements=media_db.PLACEMENTS,
        placement_labels=media_svc.PLACEMENT_LABELS,
    )


@bp.route('/media/<int:media_id>/edit', methods=['GET', 'POST'])
def media_edit(media_id: int):
    if request.method == 'POST':
        ok, message = media_svc.save_media(
            request.form.to_dict(),
            file_storage=request.files.get('image_file'),
            poster_storage=request.files.get('poster_file'),
        )
        flash(message, 'message' if ok else 'error')
        if ok:
            return redirect(url_for('ecommerce.media'))
    form = media_svc.get_edit_form(media_id)
    if not form:
        flash('Media not found.', 'error')
        return redirect(url_for('ecommerce.media'))
    if request.method == 'POST':
        form = {**form, **request.form.to_dict()}
    return render_template(
        'ecommerce/media_form.html',
        title=f"Edit media #{media_id}",
        form=form,
        placements=media_db.PLACEMENTS,
        placement_labels=media_svc.PLACEMENT_LABELS,
    )


@bp.route('/media/<int:media_id>/deactivate', methods=['POST'])
def media_deactivate(media_id: int):
    ok, message = media_svc.deactivate_media(media_id)
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.media'))


@bp.route('/media/files/<filename>')
def media_file(filename: str):
    path = media_svc.resolve_file_path(filename)
    if not path:
        abort(404)
    return send_file(str(path), mimetype=media_svc.media_content_type(filename))


@bp.route('/cms')
def cms():
    data = cms_svc.list_cms_page()
    return render_template(
        'ecommerce/cms.html',
        title='Ecommerce — CMS pages',
        **data,
    )


@bp.route('/cms/new', methods=['GET', 'POST'])
def cms_new():
    if request.method == 'POST':
        ok, message = cms_svc.save_page(request.form.to_dict())
        flash(message, 'message' if ok else 'error')
        if ok:
            return redirect(url_for('ecommerce.cms'))
    form = cms_svc.get_create_form()
    if request.method == 'POST':
        form = {**form, **request.form.to_dict()}
    return render_template(
        'ecommerce/cms_form.html',
        title='New CMS page',
        form=form,
    )


@bp.route('/cms/<int:cms_page_id>/edit', methods=['GET', 'POST'])
def cms_edit(cms_page_id: int):
    if request.method == 'POST':
        ok, message = cms_svc.save_page(request.form.to_dict())
        flash(message, 'message' if ok else 'error')
        if ok:
            return redirect(url_for('ecommerce.cms'))
    form = cms_svc.get_edit_form(cms_page_id)
    if not form:
        flash('CMS page not found.', 'error')
        return redirect(url_for('ecommerce.cms'))
    if request.method == 'POST':
        form = {**form, **request.form.to_dict()}
    return render_template(
        'ecommerce/cms_form.html',
        title=f"Edit CMS page #{cms_page_id}",
        form=form,
    )


@bp.route('/inventory')
def inventory():
    page = _int_query('page', 1)
    search = (request.args.get('q') or '').strip() or None
    stock_filter = (request.args.get('stock') or 'issues').strip().lower()
    if stock_filter not in ('issues', 'out', 'low'):
        stock_filter = 'issues'
    snap = catalog_svc.inventory_snapshot()
    items, total, loc = catalog_svc.list_inventory_items(
        page=page,
        per_page=50,
        search=search,
        stock_filter=stock_filter,
    )
    per_page = 50
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    return render_template(
        'ecommerce/inventory.html',
        title='Ecommerce — Inventory',
        snap=snap,
        items=items,
        total=total,
        page=page,
        total_pages=total_pages,
        search=search or '',
        stock_filter=stock_filter,
        location_code=loc,
    )


@bp.route('/reports')
def reports():
    data = reports_svc.get_reports_data()
    return render_template(
        'ecommerce/reports.html',
        title='Ecommerce — Reports',
        **data,
    )


@bp.route('/settings')
def settings():
    section = (request.args.get('section') or 'general').strip()
    data = settings_svc.get_settings_page(section=section)
    return render_template(
        'ecommerce/settings.html',
        title='Ecommerce — Settings',
        **data,
    )


@bp.route('/settings/general', methods=['POST'])
def settings_general():
    ok, message = settings_svc.save_general_settings(request.form.to_dict())
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.settings', section='general'))


@bp.route('/settings/zones/<int:zone_id>', methods=['POST'])
def settings_zone(zone_id: int):
    ok, message = settings_svc.save_delivery_zone(zone_id, request.form.to_dict())
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.settings', section='delivery'))


@bp.route('/settings/slots/<int:slot_id>/toggle', methods=['POST'])
def settings_slot_toggle(slot_id: int):
    ok, message = settings_db.toggle_delivery_slot(slot_id)
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.settings', section='slots'))


@bp.route('/settings/pickup/<int:store_id>/toggle', methods=['POST'])
def settings_pickup_toggle(store_id: int):
    ok, message = settings_db.toggle_pickup_store(store_id)
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.settings', section='pickup'))


@bp.route('/settings/zones/new', methods=['POST'])
def settings_zone_new():
    ok, message = settings_svc.create_delivery_zone(request.form.to_dict())
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.settings', section='delivery'))


@bp.route('/settings/slots/new', methods=['POST'])
def settings_slot_new():
    ok, message = settings_svc.create_delivery_slot(request.form.to_dict())
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.settings', section='slots'))


@bp.route('/settings/pickup/new', methods=['POST'])
def settings_pickup_new():
    ok, message = settings_svc.create_pickup_store(request.form.to_dict())
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.settings', section='pickup'))
