from pathlib import Path

p = Path("addons/sales/views/templates/sales/sales_credit_note_form.html")
t = p.read_text(encoding="utf-8")

# Jinja header: credit note (posted style, like debit note post)
t = t.replace("{% set _is_dn = return_type_value == 'D' %}", "{% set _is_cn = true %}")
t = t.replace("{% set _is_vn = _is_dn %}", "{% set _is_vn = _is_cn %}")
t = t.replace(
    "{% set _is_dn_post = _is_dn and show_load_return_order is defined and show_load_return_order %}",
    "{% set _is_cn_post = _is_cn %}",
)
t = t.replace("{% set _is_vn_post = _is_dn_post %}", "{% set _is_vn_post = _is_cn_post %}")
t = t.replace("{% if _is_dn_post %}", "{% if _is_cn_post %}")
t = t.replace("{% elif _is_dn %}", "{% elif false %}")
t = t.replace("{% elif _is_dn and not _is_dn_post %}", "{% elif false %}")
t = t.replace("{% elif _is_dn_post %}", "{% elif false %}")

# Labels: supplier -> customer in UI
t = t.replace('for="supplierDisplay">Supplier</', 'for="supplierDisplay">Customer</')
t = t.replace("F1 supplier list", "F1 customer list")
t = t.replace("supplier list", "customer list")
t = t.replace('id="supplierModalTitle">Supplier</', 'id="supplierModalTitle">Customer</')
t = t.replace("No suppliers found", "No customers found")
t = t.replace('<label>Receipt No</label>', '<label>Invoice / Bill No</label>')
t = t.replace('placeholder="Receipt no"', 'placeholder="Optional invoice or bill no"')

# Remove load request row block
old_load = """    {% if show_load_return_order is not defined or show_load_return_order %}
    <div class="form-group">
      <label>{% if _is_dn %}Load debit note request{% else %}Load return order{% endif %}</label>
      <span class="search-field">
        <input type="number" class="input" id="returnOrderNoLoad" placeholder="Request no" min="0" value="{{ initial_return_order_no or '' }}" {% if query_mode %}readonly{% endif %} />
        {% if not query_mode %}<button type="button" class="search-picker" id="btnLoadReturnOrder">Load</button>{% endif %}
      </span>
    </div>
    {% endif %}"""
t = t.replace(old_load, "")

# Toolbar: remove debit PDF / edit links
t = t.replace(
    """        {% if query_mode and can_edit_request is defined and can_edit_request and return_no and _is_dn %}
        <a class="im-btn-secondary po-toolbar-btn" href="{{ url_for('purchase.purchase_debit_note_request_edit', goods_return_no=return_no) }}">Edit</a>
        {% endif %}
        {% if query_mode and _is_dn and not _is_dn_post and return_no %}
        <a class="im-btn-secondary po-toolbar-btn" target="_blank" rel="noopener"
           href="{{ url_for('purchase.api_debit_note_request_pdf', goods_return_no=return_no) }}">Print PDF</a>
        {% elif query_mode and _is_dn_post and return_no %}
        <a class="im-btn-secondary po-toolbar-btn" target="_blank" rel="noopener"
           href="{{ url_for('purchase.api_debit_note_pdf', dr_no=return_no) }}">Print PDF</a>
        {% endif %}
""",
    """        {% if query_mode and return_no %}
        <a class="im-btn-secondary po-toolbar-btn" href="{{ url_for('sales.sales_credit_note_edit', cr_no=return_no) }}">Edit</a>
        {% endif %}
""",
)

t = t.replace(
    "{{ list_url or url_for('purchase.purchase_return_list') }}",
    "{{ list_url or url_for('sales.sales_credit_note_list') }}",
)

# JS API endpoints
replacements = [
    ("(save_api_url or url_for('purchase.api_purchase_return_save'))", "(save_api_url or url_for('sales.sales_credit_note_save'))"),
    ("(next_no_api_url or url_for('purchase.api_purchase_return_next_no'))", "(next_no_api_url or url_for('sales.sales_credit_note_next_no_api'))"),
    ("url_for('purchase.api_purchase_return_load_from_order', goods_return_no=0)", "url_for('sales.sales_credit_note_list')"),
    ("(refresh_save_nonce_url or url_for('purchase.api_purchase_debit_note_refresh_save_nonce'))", "(refresh_save_nonce_url or url_for('sales.sales_credit_note_refresh_save_nonce'))"),
    ("(return_type_value or 'P')", "'S'"),
    ("(doc_label or 'Purchase Return')", "(doc_label or 'Sales Credit Note')"),
    ("url_for('purchase.api_purchase_return_receive_locations', itemcode='0')", "url_for('sales.sales_credit_note_list')"),
    ("url_for('purchase.api_lpo_item_uoms', item_code=0)", "url_for('sales.sales_credit_note_item_uoms', item_code=0)"),
    ("url_for('purchase.api_grn_warehouse_bins')", "''"),
    ("url_for('purchase.api_purchase_return_item_lots', itemcode=0)", "''"),
    ("(url_for('purchase.api_lpo_warehouses') if warehouse_enabled else '')", "''"),
    ("url_for('purchase.api_lpo_items')", "url_for('sales.sales_credit_note_items')"),
]
for a, b in replacements:
    t = t.replace(a, b)

# Party list + customer fetch API
t = t.replace(
    "let suppliersList = {{ suppliers|tojson if suppliers else '[]' }};",
    "let suppliersList = [];",
)
t = t.replace(
    "const suppliers = suppliersList;",
    "const suppliers = suppliersList;\n  const apiCustomers = {{ url_for('sales.sales_customers_picker')|tojson }};\n  let customersLoaded = false;",
)

# renderSuppliers: fetch customers when needed
old_render = """  function renderSuppliers() {
    if (!supplierBody) return;
    const q = (supplierSearch && supplierSearch.value || '').toLowerCase();
    const list = q ? (suppliersList || []).filter(function (s) {
      return String(s.code || '').toLowerCase().includes(q) || String(s.name || '').toLowerCase().includes(q);
    }) : (suppliersList || []);
    supplierBody.innerHTML = list.length ? list.map(function (s) {
      return '<tr tabindex="0" data-code="' + (s.code || '') + '" data-name="' + String(s.name || '').replace(/"/g, '&quot;') + '"><td>' + (s.code || '') + '</td><td>' + (s.name || '') + '</td></tr>';
    }).join('') : '<tr><td colspan="2">No customers found</td></tr>';
  }"""
new_render = """  function renderSuppliers() {
    if (!supplierBody) return;
    const q = (supplierSearch && supplierSearch.value || '').trim();
    const list = (suppliersList || []).filter(function (s) {
      if (!q) return true;
      const hay = (String(s.code || '') + ' ' + String(s.name || '')).toLowerCase();
      return hay.indexOf(q.toLowerCase()) !== -1;
    });
    supplierBody.innerHTML = list.length ? list.map(function (s) {
      return '<tr tabindex="0" data-code="' + (s.code || '') + '" data-name="' + String(s.name || '').replace(/"/g, '&quot;') + '"><td>' + (s.code || '') + '</td><td>' + (s.name || '') + '</td></tr>';
    }).join('') : '<tr><td colspan="2">No customers found</td></tr>';
  }
  function ensureCustomersLoaded(done) {
    if (customersLoaded && suppliersList.length) {
      if (typeof done === 'function') done();
      return;
    }
    const url = apiCustomers + '?limit=300' + ((supplierSearch && supplierSearch.value) ? '&q=' + encodeURIComponent(supplierSearch.value.trim()) : '');
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        suppliersList = (d && d.customers) ? d.customers.map(function (c) {
          return { code: c.code || c.customercode || c.CODE, name: c.name || c.customername || c.NAME || '' };
        }) : [];
        customersLoaded = true;
        if (typeof done === 'function') done();
      })
      .catch(function () { if (typeof done === 'function') done(); });
  }"""
t = t.replace(old_render, new_render)

t = t.replace(
    """  function openSupplierModal() {
    if (queryMode) return;
    renderSuppliers();
    if (supplierSearch) supplierSearch.value = '';
    if (supplierModal) supplierModal.classList.remove('hidden');
    if (supplierSearch) supplierSearch.focus();
  }""",
    """  function openSupplierModal() {
    if (queryMode) return;
    if (supplierModal) supplierModal.classList.remove('hidden');
    if (supplierBody) supplierBody.innerHTML = '<tr><td colspan="2">Loading…</td></tr>';
    if (supplierSearch) supplierSearch.focus();
    ensureCustomersLoaded(function () { renderSuppliers(); });
  }""",
)

# supplier search debounce
t = t.replace(
    "if (supplierSearch) supplierSearch.addEventListener('input', renderSuppliers);",
    "if (supplierSearch) supplierSearch.addEventListener('input', function () {\n    customersLoaded = false;\n    ensureCustomersLoaded(renderSuppliers);\n  });",
)

# Item fetch: map sales popup items
t = t.replace(
    "let url = apiItems + '?limit=' + (limit || 200);",
    "let url = apiItems + '?limit=' + (limit || 200) + '&filter=all';",
)
t = t.replace(
    "if (d.items) itemsList = d.items;",
    """if (d.items) {
          itemsList = d.items.map(function (i) {
            return {
              code: i.code || i.itemcode || i.ITEMCODE,
              name: i.name || i.itemname || i.ITEMNAME || i.description || '',
              barcode: i.barcode || i.manufacturerid || '',
              uom: i.uom || i.unit || 'NOS',
              cost: i.cost != null ? i.cost : (i.costprice != null ? i.costprice : (i.retailprice || 0))
            };
          });
        }""",
)

# UOM API path - purchase uses /item_code appended
t = t.replace(
    "fetch(apiItemUoms + '/' + encodeURIComponent(itemcode))",
    "fetch(apiItemUoms.replace(/\\/0\\/?$/, '') + '/' + encodeURIComponent(itemcode))",
)

# Add sales item-uoms response adapter in openUomModalForRow - patch uom mapping
t = t.replace(
    """        uomBody.innerHTML = d.uoms.map((u) => {
          const uomVal = String(u.uom || '').replace(/"/g, '&quot;');
          const costVal = (u.cost != null ? Number(u.cost) : 0);
          const factorVal = (u.factor != null ? Number(u.factor) : 1);""",
    """        uomBody.innerHTML = d.uoms.map((u) => {
          const uomVal = String(u.uom || u.code || '').replace(/"/g, '&quot;');
          const costVal = (u.cost != null ? Number(u.cost) : (u.costprice != null ? Number(u.costprice) : 0));
          const factorVal = (u.factor != null ? Number(u.factor) : (u.conversion_factor != null ? Number(u.conversion_factor) : 1));""",
)

# Save payload + confirm
t = t.replace("const isDebitNote = String(returnTypeValue || '') === 'D';", "const isCreditNote = true;")
t = t.replace("const isVendorNote = isDebitNote;", "const isVendorNote = isCreditNote;")
t = t.replace(
    """      var postConfirm = 'Save and post this Purchase Debit Note to DRHDR and GL?';
      if (sourceReturnOrderNo > 0) {
        postConfirm = 'Post debit note #' + goodsreturnno + ' from request #' + sourceReturnOrderNo + '?\n\nThis writes DRHDR/DRDTL and GL entries.';
      }""",
    """      var postConfirm = 'Save and post this Sales Credit Note to CRHDR and GL? Customer receivable will be reduced.';""",
)
t = t.replace(
    """        body: JSON.stringify({
          goodsreturnno: goodsreturnno,
          returndate: returnDateEl.value,
          returntype: returnTypeValue,
          suppliercode: parseInt(supplierCode.value || '0', 10) || 0,
          receiptno: parseInt(refInvoiceNo.value || '0', 10) || 0,
          returnamount: parseFloat(totalAmount.value || '0') || 0,
          remarks: (remarksEl.value || ''),
          return_order_no: sourceReturnOrderNo,
          save_nonce: nonce,
          lines: lines
        })""",
    """        body: JSON.stringify({
          crno: goodsreturnno,
          crdate: returnDateEl.value,
          customercode: parseInt(supplierCode.value || '0', 10) || 0,
          remarks: (remarksEl.value || ''),
          cramount: parseFloat(totalAmount.value || '0') || 0,
          save_nonce: nonce,
          lines: lines.map(function (ln) {
            return {
              itemcode: ln.itemcode,
              uom: ln.uom,
              quantity: ln.quantity,
              rate: ln.rate,
              amount: ln.amount
            };
          })
        })""",
)
t = t.replace(
    "if (n.success && n.goodsreturnno) returnNoEl.value = n.goodsreturnno;",
    "if (n.success && n.crno) returnNoEl.value = n.crno;",
)
t = t.replace(
    "var nextUrl = (d && d.list_url) ? String(d.list_url) : {{ (list_url or url_for('purchase.purchase_return_list'))|tojson }};",
    "var nextUrl = (d && d.list_url) ? String(d.list_url) : {{ (list_url or url_for('sales.sales_credit_note_list'))|tojson }};",
)

# load header customer
t = t.replace(
    "if (loadHeader.suppliercode != null) {",
    "if (loadHeader.customercode != null || loadHeader.suppliercode != null) {",
)
t = t.replace(
    "const sCode = String(loadHeader.suppliercode);",
    "const sCode = String(loadHeader.customercode != null ? loadHeader.customercode : loadHeader.suppliercode);",
)

# Disable receive locations / lots when APIs empty
t = t.replace(
    "function fetchReceiveLocationCodes(itemcode) {\n    return fetch(apiReceiveLocationsBase + '/' + encodeURIComponent(itemcode))",
    "function fetchReceiveLocationCodes(itemcode) {\n    if (!apiReceiveLocationsBase || apiReceiveLocationsBase.indexOf('credit-note') >= 0) return Promise.resolve([]);\n    return fetch(apiReceiveLocationsBase + '/' + encodeURIComponent(itemcode))",
)

p.write_text(t, encoding="utf-8")
print("patched", p)
