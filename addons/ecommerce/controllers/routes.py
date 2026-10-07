"""Flask routes for the ecommerce addon."""
from __future__ import annotations

import io
import json
import os
import tempfile
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
from addons.ecommerce.services import assist as assist_svc
from addons.ecommerce.services import reviews as reviews_svc
from addons.ecommerce.services import product_edit as product_edit_svc
from addons.ecommerce.services import product_images as product_images_svc
from addons.ecommerce.services import product_page_import as product_page_import_svc
from addons.ecommerce.services import snoonu as snoonu_svc
from addons.ecommerce.services import product_compare as product_compare_svc
from addons.ecommerce.services import product_compare_find as product_compare_find_svc
from addons.ecommerce.services import product_web_meta as web_meta_svc
from addons.ecommerce import compare_stores_db
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
    'live_orders',
    'products',
    'categories',
    'customers',
    'assist',
    'promotions',
    'reviews',
    'media',
    'cms',
    'inventory',
    'reports',
    'settings',
    'compare_stores',
    'snoonu',
)


def _int_query(name: str, default: int = 1) -> int:
    raw = request.args.get(name, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _web_filter(raw: str | None = None) -> str:
    value = (raw if raw is not None else request.args.get('web') or request.form.get('web') or '').strip().lower()
    if value in ('hidden', 'featured', 'on'):
        return value
    return 'all'


def _image_filter(raw: str | None = None) -> str:
    value = (
        raw
        if raw is not None
        else request.args.get('image') or request.form.get('image') or ''
    ).strip().lower()
    if value in ('missing', 'none', 'no', 'without'):
        return 'missing'
    if value in ('has', 'with', 'ok'):
        return 'has'
    return 'all'


def _as_form_bool(name: str) -> bool:
    return str(request.form.get(name) or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _product_edit_query() -> dict:
    sort_column = (request.form.get('sort') or request.args.get('sort') or '').strip()
    sort_order = (request.form.get('order') or request.args.get('order') or '').strip()
    search = (request.form.get('q') or request.args.get('q') or '').strip()
    page = request.form.get('page') or request.args.get('page') or 1
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    web = _web_filter()
    image = _image_filter()
    return {
        'q': search or None,
        'page': page if page > 1 else None,
        'sort': sort_column or None,
        'order': sort_order if sort_order in ('asc', 'desc') else None,
        'web': web if web != 'all' else None,
        'image': image if image != 'all' else None,
    }


def _products_redirect_kwargs() -> dict:
    page = request.form.get('page') or request.args.get('page') or 1
    sort_column = (request.form.get('sort') or request.args.get('sort') or '').strip()
    sort_order = (request.form.get('order') or request.args.get('order') or '').strip()
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    web = _web_filter()
    image = _image_filter()
    return {
        'q': request.form.get('q') or request.args.get('q') or None,
        'page': page if page > 1 else None,
        'sort': sort_column or None,
        'order': sort_order if sort_order in ('asc', 'desc') else None,
        'web': web if web != 'all' else None,
        'image': image if image != 'all' else None,
    }


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


def _orders_filter_args() -> dict:
    period = (request.args.get('period') or 'today').strip().lower() or 'today'
    if period not in ('today', 'yesterday', 'last_7', 'last_30', 'last_180', 'custom', 'all'):
        period = 'today'
    tab = (request.args.get('tab') or 'all').strip().lower() or 'all'
    if tab not in ('all', 'preparing', 'ready', 'delivered', 'cancelled'):
        tab = 'all'
    channel = (request.args.get('channel') or 'all').strip().lower() or 'all'
    if channel not in ('all', 'web', 'whatsapp'):
        channel = 'all'
    return {
        'status': (request.args.get('status') or '').strip() or None,
        'tab': tab,
        'search': (request.args.get('q') or '').strip() or None,
        'period': period,
        'date_from': (request.args.get('date_from') or '').strip() or None,
        'date_to': (request.args.get('date_to') or '').strip() or None,
        'channel': channel,
    }


@bp.route('/orders')
def orders():
    page = _int_query('page', 1)
    data = orders_svc.list_orders_page(page=page, page_size=20, **_orders_filter_args())
    return render_template(
        'ecommerce/orders.html',
        title='Ecommerce — Order history',
        **data,
    )


@bp.route('/orders/export.xlsx')
def orders_export():
    data = orders_svc.list_orders_page(page=1, page_size=2000, **_orders_filter_args())
    try:
        from openpyxl import Workbook
    except ImportError:
        flash('Excel export requires openpyxl.', 'error')
        return redirect(url_for('ecommerce.orders', **{k: v for k, v in _orders_filter_args().items() if v}))
    wb = Workbook()
    ws = wb.active
    ws.title = 'Order history'
    ws.append(['Order ID', 'Channel', 'Status', 'Order total', 'Branch', 'Customer', 'Payment', 'Created'])
    for row in data.get('orders') or []:
        ws.append([
            row.get('order_number') or '',
            row.get('channel_label') or row.get('created_by_name') or 'Web',
            row.get('display_status') or row.get('order_status') or '',
            float(row.get('grand_total') or 0),
            row.get('branch_name') or '',
            row.get('customer_name') or row.get('customer_email') or '',
            row.get('payment_status') or '',
            str(row.get('created_at') or '')[:19],
        ])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f"order_history_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return Response(
        bio.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'},
    )


@bp.route('/orders/latest-alert')
def orders_latest_alert():
    data = orders_db.latest_order_alert()
    return jsonify({'ok': True, **data})


@bp.route('/live-orders')
def live_orders():
    data = orders_svc.live_orders_payload()
    return render_template(
        'ecommerce/live_orders.html',
        title='Ecommerce — Live orders',
        **data,
    )


@bp.route('/live-orders/feed')
def live_orders_feed():
    search = (request.args.get('q') or '').strip() or None
    return jsonify({'ok': True, **orders_svc.live_orders_payload(search=search)})


@bp.route('/live-orders/<int:order_id>/status', methods=['POST'])
def live_order_status(order_id: int):
    payload = request.get_json(silent=True) or {}
    status = (payload.get('status') or request.form.get('status') or '').strip()
    notes = (payload.get('notes') or request.form.get('notes') or '').strip() or None
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
    return jsonify({'ok': ok, 'message': message}), (200 if ok else 400)


@bp.route('/orders/<int:order_id>')
def order_detail(order_id: int):
    order = orders_svc.get_order_detail(order_id)
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('ecommerce.orders'))
    invoice_pdf_url = ''
    billno = str(order.get('erp_billno') or '').strip()
    if billno:
        try:
            invoice_pdf_url = url_for(
                'reports.crystal_reports_open_report',
                report_name='cashbilldup',
                billno=billno,
            )
        except Exception:
            invoice_pdf_url = url_for('sales.sales_invoice_list', tab='invoice', q=billno)
    return render_template(
        'ecommerce/order_detail.html',
        title=f"Order {order.get('order_number') or order_id}",
        order=order,
        status_options=sorted(orders_db.ALLOWED_STATUSES),
        invoice_pdf_url=invoice_pdf_url,
    )


@bp.route('/orders/<int:order_id>/receipt')
def order_receipt(order_id: int):
    order = orders_svc.get_order_receipt(order_id)
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('ecommerce.orders'))
    return render_template(
        'ecommerce/order_receipt.html',
        title=f"Receipt {order.get('order_number') or order_id}",
        order=order,
        auto_print=(request.args.get('print') or '').strip() == '1',
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


@bp.route('/orders/<int:order_id>/create-sales-invoice', methods=['POST'])
def order_create_sales_invoice(order_id: int):
    """Post this web order to ERP Sales Invoice (BILLHDR) and deduct stock."""
    updated_by = session.get('user_id')
    try:
        updated_by = int(updated_by) if updated_by is not None else None
    except (TypeError, ValueError):
        updated_by = None
    result = orders_svc.create_sales_invoice(
        order_id,
        created_by=session.get('user'),
        updated_by=updated_by,
    )
    flash(result.get('message') or result.get('error') or 'Invoice action failed.', 'message' if result.get('ok') else 'error')
    return redirect(url_for('ecommerce.order_detail', order_id=order_id))


@bp.route('/orders/<int:order_id>/remove', methods=['POST'])
def order_remove(order_id: int):
    """Delete a website/WhatsApp order only if no ERP bill exists yet."""
    ok, message = orders_svc.remove_uninvoiced_order(order_id)
    flash(message, 'message' if ok else 'error')
    if ok:
        return redirect(url_for('ecommerce.orders'))
    return redirect(url_for('ecommerce.order_detail', order_id=order_id))


@bp.route('/products')
def products():
    page = _int_query('page', 1)
    search = (request.args.get('q') or '').strip()
    sort_column = (request.args.get('sort') or '').strip().lower()
    sort_order = (request.args.get('order') or '').strip().lower()
    if not sort_column:
        sort_column = 'itemcode'
        sort_order = 'asc'
    if sort_order not in ('asc', 'desc'):
        sort_order = 'asc'
    web = _web_filter()
    image = _image_filter()
    items, total, loc = catalog_svc.list_products(
        page=page,
        per_page=50,
        search=search or None,
        order_by=sort_column or None,
        order_direction=sort_order or None,
        web_filter=web,
        image_filter=image,
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
        web_filter=web,
        image_filter=image,
        location_code=loc,
        show_all_items_on_web=settings_store.show_all_items_on_web(),
        pending_image_skus=product_images_svc.count_items_missing_images(loc),
        product_image_skus=product_images_svc.count_items_with_images(loc),
        product_gallery_skus=product_images_svc.count_product_gallery_images(),
    )


@bp.route('/products/<int:item_code>', methods=['GET'])
def product_edit(item_code: int):
    product = catalog_svc.get_product_for_edit(item_code)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('ecommerce.products'))
    back_q = (request.args.get('q') or '').strip()
    back_sort = (request.args.get('sort') or '').strip()
    back_order = (request.args.get('order') or '').strip()
    back_web = _web_filter()
    back_image = _image_filter()
    descending = (back_sort or 'itemcode') == 'itemcode' and back_order == 'desc'
    prev_item_code, next_item_code = catalog_svc.adjacent_product_codes(
        item_code,
        search=back_q or None,
        web_filter=back_web,
        image_filter=back_image,
        descending=descending,
    )
    nav_kwargs = _product_edit_query()
    return render_template(
        'ecommerce/product_edit.html',
        title=f'Edit product {item_code}',
        product=product,
        back_q=back_q,
        back_page=_int_query('page', 1),
        back_sort=back_sort,
        back_order=back_order,
        back_web=back_web,
        back_image=back_image,
        prev_item_code=prev_item_code,
        next_item_code=next_item_code,
        nav_kwargs=nav_kwargs,
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
        remove_all_gallery=_as_form_bool('remove_all_gallery'),
        age_group_ids=request.form.getlist('age_group_id'),
        seo_title=request.form.get('seo_title'),
        seo_description=request.form.get('seo_description'),
        touch_seo='seo_title' in request.form or 'seo_description' in request.form,
        show_on_web=_as_form_bool('show_on_web'),
        is_featured=_as_form_bool('is_featured'),
        is_addon=_as_form_bool('is_addon'),
        touch_web_flags='touch_web_flags' in request.form,
        import_page_url=request.form.get('import_page_url'),
        touch_import_page_url='import_page_url' in request.form,
    )
    flash(message, 'message' if ok else 'error')
    if not ok:
        return redirect(url_for('ecommerce.product_edit', item_code=item_code, **_product_edit_query()))
    return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))


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
    return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))


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
    ws.append([
        'ItemCode',
        'Barcode',
        'LocationCode',
        'FolderName',
        'ImageURL',
        'ImageFileName',
        'Image',
        'Description',
        'DescriptionArabic',
        'Specifications',
        'ProductPageURL',
    ])
    ws.append([1001, '', '', 'rattle-set', '', '', '', 'Soft baby rattle set for newborns.', 'طقم خشخيشة ناعم للمواليد.', 'Age: 0-12 months\nPieces: 8', ''])
    ws.append(['', '1234567890123', '', '', '', 'photo-1001.jpg', '', '', '', '', ''])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f'product_images_import_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
    return Response(
        bio.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'},
    )


def _wants_json_response() -> bool:
    if str(request.form.get('ajax') or request.args.get('ajax') or '').strip() == '1':
        return True
    accept = ''
    try:
        accept = str(request.headers.get('accept') or request.headers.get('Accept') or '')
    except Exception:
        accept = ''
    return 'application/json' in accept.lower()


def _folder_uploads_from_request() -> list:
    uploads = []
    for storage in request.files.getlist('image_files'):
        name = product_images_svc.safe_upload_relpath(getattr(storage, 'filename', '') or '')
        if not name:
            continue
        data = storage.read()
        if not isinstance(data, bytes):
            data = bytes(data) if data else b''
        if not data:
            continue
        uploads.append((name, data))
    return uploads


def _image_import_payload(result: dict, message: str) -> dict:
    return {
        'ok': bool(result.get('ok')),
        'partial': bool(result.get('partial')),
        'message': message,
        'processed': int(result.get('processed') or 0),
        'updated': int(result.get('updated') or 0),
        'failed': int(result.get('failed') or 0),
        'errors': (result.get('errors') or [])[:10],
        'redirect': url_for('ecommerce.products', **_products_redirect_kwargs()),
    }


@bp.route('/products/images/import/progress', methods=['GET'])
def products_image_import_progress():
    """Live folder count for a bulk ZIP import (polled while the upload request runs)."""
    data = product_images_svc.read_import_progress(request.args.get('job_id'))
    if not data:
        return jsonify(
            {
                'ok': True,
                'phase': 'waiting',
                'processed': 0,
                'updated': 0,
                'failed': 0,
                'total': 0,
                'current': '',
                'done': False,
            }
        )
    return jsonify(data)


@bp.route('/products/images/import', methods=['POST'])
def products_image_import():
    """Bulk assign ITEMMASTER.IMAGE_PATH from Excel (+ optional ZIP of image files)."""
    wants_json = _wants_json_response()
    job_id = product_images_svc.safe_import_job_id(request.form.get('import_job_id'))

    def on_progress(payload):
        product_images_svc.write_import_progress(job_id, payload)

    excel = request.files.get('excel_file') or request.files.get('file')
    excel_raw = b''
    if excel and getattr(excel, 'filename', None):
        fname = str(excel.filename or '').lower()
        if not fname.endswith(('.xlsx', '.xlsm')):
            if wants_json:
                return jsonify({'ok': False, 'message': 'Please upload a .xlsx or .xlsm file.'}, 400)
            flash('Please upload a .xlsx or .xlsm file.', 'error')
            return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))
        excel_raw = excel.read()
        if not isinstance(excel_raw, bytes):
            excel_raw = bytes(excel_raw) if excel_raw else b''

    zip_raw = b''
    zip_path = None
    zip_file = request.files.get('images_zip')
    if zip_file and getattr(zip_file, 'filename', None):
        zip_name = str(zip_file.filename or '').lower()
        if zip_name.endswith('.zip'):
            fd, zip_path = tempfile.mkstemp(suffix='.zip', prefix='mh-img-')
            os.close(fd)
            zip_file.save(zip_path)

    folder_uploads = _folder_uploads_from_request()
    if not excel_raw and not zip_path and not folder_uploads:
        if wants_json:
            return jsonify(
                {'ok': False, 'message': 'Choose an Excel file, a ZIP, or a folder of barcode images.'},
                400,
            )
        flash('Choose an Excel file, a ZIP, or a folder of barcode images.', 'error')
        return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))

    download_urls = str(request.form.get('download_urls') or '1').strip().lower() in ('1', 'true', 'yes', 'on')
    existing_mode = str(request.form.get('existing_images') or 'keep').strip().lower()
    replace_existing = existing_mode in ('replace', 'remove', 'overwrite', '1', 'true', 'yes')
    result = {'ok': False, 'error': 'Import failed.'}
    try:
        if job_id:
            product_images_svc.write_import_progress(
                job_id,
                {
                    'phase': 'preparing',
                    'total': 0,
                    'processed': 0,
                    'updated': 0,
                    'failed': 0,
                    'current': '',
                    'done': False,
                },
            )
        if excel_raw:
            if zip_path:
                with open(zip_path, 'rb') as zip_in:
                    zip_raw = zip_in.read()
            result = product_images_svc.import_product_images_from_excel(
                excel_raw,
                zip_raw=zip_raw or None,
                download_urls=download_urls,
                replace_existing=replace_existing,
            )
        elif folder_uploads:
            result = product_images_svc.import_product_images_from_folder_uploads(
                folder_uploads,
                progress_cb=on_progress if job_id else None,
                replace_existing=replace_existing,
            )
        else:
            result = product_images_svc.import_product_images_from_barcode_zip_path(
                zip_path,
                progress_cb=on_progress if job_id else None,
                replace_existing=replace_existing,
            )
    finally:
        if zip_path:
            try:
                os.unlink(zip_path)
            except OSError:
                pass
    if not result.get('ok'):
        message = str(result.get('error') or result.get('message') or 'Import failed.')
        if job_id:
            product_images_svc.write_import_progress(
                job_id,
                {
                    'phase': 'done',
                    'done': True,
                    'ok': False,
                    'message': message,
                    'processed': int(result.get('processed') or 0),
                    'updated': int(result.get('updated') or 0),
                    'failed': int(result.get('failed') or 0),
                    'total': int(result.get('processed') or 0),
                },
            )
        if wants_json:
            return jsonify(_image_import_payload(result, message), 400)
        flash(message, 'error')
        return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))

    message = str(result.get('message') or 'Import completed.')
    errs = result.get('errors') or []
    if errs:
        preview = '; '.join(errs[:3])
        if len(errs) > 3:
            preview += f' … and {len(errs) - 3} more'
        message = f'{message}. {preview}'
    if wants_json:
        return jsonify(_image_import_payload(result, message))
    flash(message, 'message' if result.get('partial') or result.get('updated') else 'warning')
    return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))


def _run_drive_image_import(
    *,
    item_code: Optional[int] = None,
    fallback_barcode: str = '',
):
    wants_json = _wants_json_response()
    drive_url = str(request.form.get('drive_url') or request.form.get('google_drive_url') or '').strip()
    job_id = product_images_svc.safe_import_job_id(request.form.get('import_job_id'))
    existing_mode = str(request.form.get('existing_images') or 'keep').strip().lower()
    replace_existing = existing_mode in ('replace', 'remove', 'overwrite', '1', 'true', 'yes')
    if item_code:
        replace_existing = False

    def redirect_back():
        if item_code:
            return redirect(url_for('ecommerce.product_edit', item_code=item_code, **_product_edit_query()))
        return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))

    if not drive_url:
        message = 'Paste a Google Drive folder or file link.'
        if wants_json:
            return jsonify({'ok': False, 'message': message}, 400)
        flash(message, 'error')
        return redirect_back()

    def on_progress(payload):
        product_images_svc.write_import_progress(job_id, payload)

    if job_id:
        product_images_svc.write_import_progress(
            job_id,
            {
                'phase': 'preparing',
                'total': 0,
                'processed': 0,
                'updated': 0,
                'failed': 0,
                'current': 'Reading Google Drive…',
                'done': False,
            },
        )
    result = product_images_svc.import_product_images_from_drive_url(
        drive_url,
        replace_existing=replace_existing,
        only_item_code=int(item_code) if item_code else None,
        fallback_barcode=fallback_barcode,
        progress_cb=on_progress if job_id else None,
    )
    if not result.get('ok'):
        message = str(result.get('error') or result.get('message') or 'Could not fetch Drive images.')
        if job_id:
            product_images_svc.write_import_progress(
                job_id,
                {
                    'phase': 'done',
                    'done': True,
                    'ok': False,
                    'message': message,
                    'processed': int(result.get('processed') or 0),
                    'updated': int(result.get('updated') or 0),
                    'failed': int(result.get('failed') or 0),
                    'total': int(result.get('processed') or 0),
                },
            )
        if wants_json:
            return jsonify(_image_import_payload(result, message), 400)
        flash(message, 'error')
        return redirect_back()
    message = str(result.get('message') or 'Images fetched from Google Drive.')
    kept = int(result.get('kept') or 0)
    if item_code and kept and not int(result.get('gallery_total') or 0):
        message = 'This product already has an image. Existing photo was kept.'
    if wants_json:
        return jsonify(_image_import_payload(result, message))
    flash(message, 'warning' if item_code and kept else 'message')
    return redirect_back()


@bp.route('/products/images/from-drive', methods=['POST'])
def products_images_from_drive():
    """Fetch barcode-named images from a public Google Drive folder or file."""
    return _run_drive_image_import()


@bp.route('/products/<int:item_code>/images/from-drive', methods=['POST'])
def product_images_from_drive(item_code: int):
    """Fetch Drive images for one product if it has no photo yet."""
    product = catalog_svc.get_product_for_edit(item_code)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))
    return _run_drive_image_import(
        item_code=int(item_code),
        fallback_barcode=str(product.get('barcode') or ''),
    )


@bp.route('/products/<int:item_code>/images/from-folder', methods=['POST'])
def product_images_from_folder(item_code: int):
    """Upload images only. Folder name is the barcode. Fills the photo if this SKU has none."""
    product = catalog_svc.get_product_for_edit(item_code)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))
    uploads = _folder_uploads_from_request()
    if not uploads:
        flash('Choose a folder of images. Name the folder with the barcode.', 'error')
        return redirect(url_for('ecommerce.product_edit', item_code=item_code, **_product_edit_query()))
    result = product_images_svc.import_product_images_from_folder_uploads(
        uploads,
        replace_existing=False,
        only_item_code=int(item_code),
        fallback_barcode=str(product.get('barcode') or ''),
    )
    if not result.get('ok'):
        flash(str(result.get('error') or result.get('message') or 'Could not save images.'), 'error')
        return redirect(url_for('ecommerce.product_edit', item_code=item_code, **_product_edit_query()))
    kept = int(result.get('kept') or 0)
    if kept and not int(result.get('gallery_total') or 0):
        flash('This product already has an image. Existing photo was kept.', 'warning')
    else:
        flash(str(result.get('message') or 'Images saved.'), 'message')
    return redirect(url_for('ecommerce.product_edit', item_code=item_code, **_product_edit_query()))


@bp.route('/products/images/remove-all', methods=['POST'])
def products_images_remove_all():
    """Clear Item Master images (and optional gallery images) for this location."""
    confirm_remove = str(request.form.get('confirm_remove') or '').strip().lower() in (
        '1',
        'true',
        'yes',
        'on',
    )
    if not confirm_remove:
        flash('Tick the confirmation box to remove all product images.', 'error')
        return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))
    remove_gallery = str(request.form.get('remove_gallery') or '').strip().lower() in (
        '1',
        'true',
        'yes',
        'on',
    )
    result = product_images_svc.remove_all_product_images(remove_gallery=remove_gallery)
    if not result.get('ok'):
        flash(result.get('error') or result.get('message') or 'Could not remove images.', 'error')
        return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))
    flash(result.get('message') or 'Product images removed.', 'message')
    return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))


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
        return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))

    message = str(result.get('message') or 'Web fetch completed.')
    errs = result.get('errors') or []
    if errs and result.get('failed'):
        preview = '; '.join(errs[:3])
        if len(errs) > 3:
            preview += f' … and {len(errs) - 3} more'
        message = f'{message}. {preview}'
    flash(message, 'message' if result.get('updated') else 'warning')
    return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))


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
    return redirect(url_for('ecommerce.products', **_products_redirect_kwargs()))


@bp.route('/products/<int:item_code>/import-from-url', methods=['POST'])
def products_import_from_url(item_code: int):
    """Fill description, features, and images from a public product page URL."""
    page_url = (request.form.get('page_url') or request.args.get('page_url') or '').strip()
    payload = request.get_json(silent=True) or {}
    if not page_url:
        page_url = str(payload.get('page_url') or '').strip()
    save_images_raw = (
        request.form.get('save_images')
        if request.form.get('save_images') is not None
        else payload.get('save_images')
    )
    if save_images_raw is None:
        save_images = True
    else:
        save_images = str(save_images_raw).strip().lower() not in ('0', 'false', 'no', 'off')
    result = product_page_import_svc.import_from_page_url(
        item_code=item_code,
        page_url=page_url,
        save_images=save_images,
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
    flash(result.get('message') or result.get('error') or 'Import failed.', 'message' if result.get('ok') else 'error')
    return redirect(url_for('ecommerce.product_edit', item_code=item_code))


@bp.route('/products/<int:item_code>/compare', methods=['GET', 'POST'])
def product_compare(item_code: int):
    """Save compare URLs and show image, description, and price from each page."""
    extra_entries = None
    if request.method == 'POST':
        extra_entries = web_meta_svc.compare_entries_from_form(
            request.form.getlist('compare_url'),
            request.form.getlist('compare_store_id'),
            request.form.getlist('compare_store'),
        )
        save_only = (request.form.get('compare_action') or '').strip().lower() == 'save'
        if save_only and not extra_entries:
            flash('Enter a product URL first.', 'error')
            return redirect(url_for('ecommerce.product_compare', item_code=item_code, **_product_edit_query()))
        ok, message = product_compare_svc.save_compare_urls(item_code, extra_entries)
        if not ok:
            flash(message or 'Could not save compare URLs.', 'error')
            return redirect(url_for('ecommerce.product_edit', item_code=item_code, **_product_edit_query()))
        if save_only:
            flash(f'Saved {len(extra_entries)} comparison URL{"s" if len(extra_entries) != 1 else ""}.', 'message')
            return redirect(url_for('ecommerce.product_compare', item_code=item_code, **_product_edit_query()))
    result = product_compare_svc.compare_product(item_code, extra_entries)
    if not result.get('ok'):
        flash(result.get('error') or 'Product not found.', 'error')
        return redirect(url_for('ecommerce.products'))
    return render_template(
        'ecommerce/product_compare.html',
        title=f'Compare product {item_code}',
        product=result.get('product'),
        rows=result.get('rows') or [],
        entries=result.get('entries') or [],
        compare_stores=compare_stores_db.list_compare_stores(active_only=True),
        lowest_price=result.get('lowest_price'),
        highest_price=result.get('highest_price'),
        nav_kwargs=_product_edit_query(),
        find_urls_url=url_for('ecommerce.product_compare_find_urls', item_code=item_code),
        search_query=product_compare_find_svc.default_search_name(result.get('product')),
    )


@bp.route('/products/<int:item_code>/compare/find-urls', methods=['POST'])
def product_compare_find_urls(item_code: int):
    """Find competitor product URLs from the editable product name."""
    payload = request.get_json(silent=True) or {}
    search_query = (
        request.form.get('search_query')
        or payload.get('search_query')
        or request.args.get('search_query')
        or ''
    )
    result = product_compare_find_svc.find_compare_urls(item_code, search_query=str(search_query or ''))
    return Response(
        json.dumps(result, default=str),
        status=200 if result.get('ok') else 422,
        mimetype='application/json',
    )


def _safe_compare_next(raw: str) -> str:
    value = str(raw or '').strip()
    if value.startswith('/ecommerce/') and '//' not in value and '\n' not in value:
        return value.split('#', 1)[0]
    return ''


@bp.route('/compare-stores', methods=['GET'])
def compare_stores():
    stores = compare_stores_db.list_compare_stores(active_only=False)
    return render_template(
        'ecommerce/compare_stores.html',
        title='Compare store master',
        stores=stores,
        next_url=_safe_compare_next(request.args.get('next') or ''),
    )


@bp.route('/compare-stores/new', methods=['POST'])
def compare_store_new():
    ok, message, _row = compare_stores_db.create_compare_store(
        store_name=request.form.get('store_name') or '',
        website_url=request.form.get('website_url') or '',
    )
    flash(message, 'message' if ok else 'error')
    next_url = _safe_compare_next(request.form.get('next') or request.args.get('next') or '')
    if ok and next_url:
        return redirect(next_url)
    return redirect(url_for('ecommerce.compare_stores', next=next_url or None))


@bp.route('/compare-stores/<int:store_id>', methods=['POST'])
def compare_store_update(store_id: int):
    ok, message = compare_stores_db.update_compare_store(
        store_id,
        store_name=request.form.get('store_name') or '',
        website_url=request.form.get('website_url') or '',
    )
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.compare_stores'))


@bp.route('/compare-stores/<int:store_id>/toggle', methods=['POST'])
def compare_store_toggle(store_id: int):
    ok, message = compare_stores_db.toggle_compare_store(store_id)
    flash(message, 'message' if ok else 'error')
    return redirect(url_for('ecommerce.compare_stores'))


@bp.route('/snoonu', methods=['GET', 'POST'])
def snoonu():
    search = (request.values.get('q') or '').strip()
    page = _int_query('page', 1)
    selected_code = 0
    try:
        selected_code = int(request.values.get('item_code') or 0)
    except (TypeError, ValueError):
        selected_code = 0
    page_url = (request.values.get('page_url') or '').strip()
    listing = snoonu_svc.list_missing_image_items(page=page, search=search)
    selected = snoonu_svc.get_catalog_item(selected_code) if selected_code else None
    item_name = (request.values.get('item_name') or '').strip()
    if selected and not item_name:
        item_name = selected.get('item_name') or ''
    if selected and not page_url:
        page_url = selected.get('snoonu_url') or ''
    result: dict | None = None
    error = ''
    should_fetch = bool(
        request.method == 'POST'
        or request.values.get('fetch')
        or snoonu_svc.is_full_snoonu_url(page_url)
    )
    if should_fetch and (page_url or item_name):
        try:
            result = snoonu_svc.fetch_snoonu_listing(page_url=page_url, item_name=item_name)
            page_url = str(result.get('page_url') or page_url)
        except ValueError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001
            error = f'Could not read that Snoonu page. {exc}'
        if error:
            flash(error, 'error')
    pages = max(1, (int(listing.get('total') or 0) + int(listing.get('per_page') or 40) - 1) // int(listing.get('per_page') or 40))
    return render_template(
        'ecommerce/snoonu.html',
        title='Ecommerce — Snoonu',
        page_url=page_url,
        item_name=item_name,
        result=result,
        error=error,
        selected=selected,
        items=listing.get('items') or [],
        items_total=listing.get('total') or 0,
        items_page=listing.get('page') or 1,
        items_pages=pages,
        items_search=listing.get('search') or '',
    )


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


@bp.route('/assist')
def assist():
    data = assist_svc.get_assist_board()
    return render_template(
        'ecommerce/assist.html',
        title='Ecommerce — Assist',
        **data,
    )


@bp.route('/assist/notify', methods=['POST'])
def assist_notify():
    try:
        user_id = int(request.form.get('user_id') or 0)
    except (TypeError, ValueError):
        user_id = 0
    message = (request.form.get('message') or '').strip()
    ok, msg = assist_svc.send_assist_notification(user_id, message)
    flash(msg, 'message' if ok else 'error')
    return redirect(request.referrer or url_for('ecommerce.assist'))


@bp.route('/assist/chat', methods=['POST'])
def assist_chat():
    try:
        user_id = int(request.form.get('user_id') or 0)
    except (TypeError, ValueError):
        user_id = 0
    message = (request.form.get('message') or '').strip()
    staff = (session.get('user') or '').strip()
    ok, msg, conversation_id = assist_svc.open_assist_chat(staff, user_id, message)
    if ok and conversation_id:
        return redirect(f'/chat?c={int(conversation_id)}')
    flash(msg, 'error')
    return redirect(request.referrer or url_for('ecommerce.assist'))


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
