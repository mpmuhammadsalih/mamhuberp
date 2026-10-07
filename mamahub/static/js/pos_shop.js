(function () {
  'use strict';

  var root = document.getElementById('posShopRoot');
  if (!root) return;

  var cfg = {
    productsUrl: root.dataset.productsUrl || '',
    categoriesUrl: root.dataset.categoriesUrl || '',
    barcodeUrl: root.dataset.barcodeUrl || '',
    customersUrl: root.dataset.customersUrl || '',
    billingUrl: root.dataset.billingUrl || '/pos-billing',
    perPage: 12,
    taxRate: 0
  };

  var state = {
    categories: [],
    activeCategory: null,
    search: '',
    page: 1,
    totalCount: 0,
    products: [],
    cart: [],
    customer: { code: '', name: 'Walk-in Customer' },
    tender: 'CASH',
    loading: false
  };

  var $ = function (sel) { return root.querySelector(sel); };
  var $$ = function (sel) { return root.querySelectorAll(sel); };

  function money(n) {
    var v = Number(n) || 0;
    return v.toFixed(2);
  }

  function fmtDisplay(n) {
    return '$' + money(n);
  }

  function productKey(p) {
    return String(p.itemcode || p.ITEMCODE || '');
  }

  function normProduct(row) {
    var stock = Number(row.currentstock != null ? row.currentstock : row.CURRENTSTOCK) || 0;
    var price = Number(row.retailprice != null ? row.retailprice : row.RETAILPRICE) || 0;
    return {
      itemcode: row.itemcode != null ? row.itemcode : row.ITEMCODE,
      itemname: (row.itemname || row.ITEMNAME || '').trim(),
      manufacturerid: (row.manufacturerid || row.MANUFACTURERID || '').toString().trim(),
      baseuom: (row.baseuom || row.BASEUOM || 'PCS').trim(),
      retailprice: price,
      currentstock: stock,
      categoryname: (row.categoryname || row.CATEGORYNAME || '').trim()
    };
  }

  function stockBadge(stock) {
    if (stock <= 0) return { cls: 'pos-shop__stock--out', text: 'Out of Stock' };
    if (stock <= 5) return { cls: 'pos-shop__stock--low', text: 'Low Stock' };
    return { cls: 'pos-shop__stock--ok', text: 'In Stock' };
  }

  function categoryIcon(name) {
    var n = (name || '').toLowerCase();
    if (n.indexOf('all') >= 0) return 'bi-grid';
    if (n.indexOf('teddy') >= 0 || n.indexOf('bear') >= 0) return 'bi-heart';
    if (n.indexOf('car') >= 0 || n.indexOf('vehicle') >= 0 || n.indexOf('bicycle') >= 0) return 'bi-truck';
    if (n.indexOf('doll') >= 0) return 'bi-person-hearts';
    if (n.indexOf('game') >= 0) return 'bi-controller';
    if (n.indexOf('puzzle') >= 0) return 'bi-puzzle';
    return 'bi-tag';
  }

  function cardEmoji(name, code) {
    var n = (name || '').toLowerCase();
    if (n.indexOf('bear') >= 0 || n.indexOf('teddy') >= 0) return '\uD83D\uDC3B';
    if (n.indexOf('car') >= 0 || n.indexOf('vehicle') >= 0) return '\uD83D\uDE97';
    if (n.indexOf('doll') >= 0) return '\uD83D\uDC67';
    if (n.indexOf('game') >= 0 || n.indexOf('puzzle') >= 0) return '\uD83C\uDFAE';
    if (n.indexOf('ball') >= 0) return '\u26BD';
    var c = Number(code) || 0;
    var icons = ['\uD83C\uDF81', '\uD83E\uDDF8', '\uD83D\uDD79\uFE0F', '\uD83E\uDDE9', '\uD83C\uDFB2'];
    return icons[c % icons.length];
  }

  function cartTotals() {
    var subtotal = 0;
    var qty = 0;
    var lines = 0;
    state.cart.forEach(function (line) {
      var lt = line.qty * line.price - (line.discount || 0);
      subtotal += lt;
      qty += line.qty;
      lines += 1;
    });
    var discount = 0;
    var tax = subtotal * (cfg.taxRate / 100);
    var grand = subtotal - discount + tax;
    return { subtotal: subtotal, discount: discount, tax: tax, grand: grand, qty: qty, lines: lines };
  }

  function findCartLine(itemcode) {
    var key = String(itemcode);
    for (var i = 0; i < state.cart.length; i++) {
      if (String(state.cart[i].itemcode) === key) return state.cart[i];
    }
    return null;
  }

  function addToCart(product) {
    var existing = findCartLine(product.itemcode);
    if (existing) {
      existing.qty += 1;
    } else {
      state.cart.push({
        itemcode: product.itemcode,
        itemname: product.itemname,
        manufacturerid: product.manufacturerid,
        uom: product.baseuom || 'PCS',
        price: product.retailprice,
        qty: 1,
        discount: 0
      });
    }
    renderCart();
    renderFooter();
  }

  function updateCartQty(itemcode, delta) {
    var line = findCartLine(itemcode);
    if (!line) return;
    line.qty += delta;
    if (line.qty <= 0) {
      state.cart = state.cart.filter(function (l) { return String(l.itemcode) !== String(itemcode); });
    }
    renderCart();
    renderFooter();
  }

  function removeFromCart(itemcode) {
    state.cart = state.cart.filter(function (l) { return String(l.itemcode) !== String(itemcode); });
    renderCart();
    renderFooter();
  }

  function renderCategories() {
    var wrap = $('#posShopCategories');
    if (!wrap) return;
    var html = '<button type="button" class="pos-shop__cat-tab' + (state.activeCategory == null ? ' is-active' : '') + '" data-code="">' +
      '<i class="bi bi-grid"></i> All Items</button>';
    state.categories.forEach(function (cat) {
      var active = state.activeCategory === cat.code ? ' is-active' : '';
      var icon = categoryIcon(cat.name);
      html += '<button type="button" class="pos-shop__cat-tab' + active + '" data-code="' + cat.code + '">' +
        '<i class="bi ' + icon + '"></i> ' + escapeHtml(cat.name) + '</button>';
    });
    wrap.innerHTML = html;
    wrap.querySelectorAll('.pos-shop__cat-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var code = btn.dataset.code;
        state.activeCategory = code ? parseInt(code, 10) : null;
        state.page = 1;
        renderCategories();
        loadProducts();
      });
    });
  }

  function renderProducts() {
    var grid = $('#posShopGrid');
    if (!grid) return;
    if (state.loading) {
      grid.innerHTML = '<div class="pos-shop__loading"><i class="bi bi-arrow-repeat"></i> Loading products…</div>';
      return;
    }
    if (!state.products.length) {
      grid.innerHTML = '<div class="pos-shop__empty">No products found. Try another category or search.</div>';
      return;
    }
    var html = '';
    state.products.forEach(function (p) {
      var badge = stockBadge(p.currentstock);
      var codeLabel = p.manufacturerid || ('TOY' + String(p.itemcode).padStart(3, '0'));
      html += '<article class="pos-shop__card" data-itemcode="' + p.itemcode + '" tabindex="0">' +
        '<div class="pos-shop__card-img">' + cardEmoji(p.itemname, p.itemcode) + '</div>' +
        '<div class="pos-shop__card-body">' +
        '<div class="pos-shop__card-name-row">' +
        '<div class="pos-shop__card-name">' + escapeHtml(p.itemname) + '</div>' +
        '<span class="pos-shop__stock ' + badge.cls + '">' + badge.text + '</span>' +
        '</div>' +
        '<div class="pos-shop__card-code">' + escapeHtml(codeLabel) + '</div>' +
        '<div class="pos-shop__card-price">' + fmtDisplay(p.retailprice) + '</div>' +
        '</div></article>';
    });
    grid.innerHTML = html;
    grid.querySelectorAll('.pos-shop__card').forEach(function (card) {
      var code = card.dataset.itemcode;
      var product = state.products.find(function (p) { return String(p.itemcode) === code; });
      if (!product) return;
      card.addEventListener('click', function () { addToCart(product); });
      card.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); addToCart(product); }
      });
    });
  }

  function renderPagination() {
    var wrap = $('#posShopPagination');
    if (!wrap) return;
    var totalPages = Math.max(1, Math.ceil(state.totalCount / cfg.perPage));
    if (state.page > totalPages) state.page = totalPages;
    var html = '';
    html += '<button type="button" class="pos-shop__page-btn" data-page="prev"' + (state.page <= 1 ? ' disabled' : '') + '><i class="bi bi-chevron-left"></i></button>';
    var start = Math.max(1, state.page - 2);
    var end = Math.min(totalPages, start + 4);
    if (end - start < 4) start = Math.max(1, end - 4);
    for (var p = start; p <= end; p++) {
      html += '<button type="button" class="pos-shop__page-btn' + (p === state.page ? ' is-active' : '') + '" data-page="' + p + '">' + p + '</button>';
    }
    if (end < totalPages) {
      html += '<span style="color:#6b7280;padding:0 4px">…</span>';
      html += '<button type="button" class="pos-shop__page-btn" data-page="' + totalPages + '">' + totalPages + '</button>';
    }
    html += '<button type="button" class="pos-shop__page-btn" data-page="next"' + (state.page >= totalPages ? ' disabled' : '') + '><i class="bi bi-chevron-right"></i></button>';
    wrap.innerHTML = html;
    wrap.querySelectorAll('.pos-shop__page-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (btn.disabled) return;
        var dp = btn.dataset.page;
        if (dp === 'prev') state.page -= 1;
        else if (dp === 'next') state.page += 1;
        else state.page = parseInt(dp, 10);
        loadProducts();
      });
    });
  }

  function renderCart() {
    var tbody = $('#posShopCartBody');
    var empty = $('#posShopCartEmpty');
    var payBtn = $('#posShopPayBtn');
    if (!tbody) return;
    if (!state.cart.length) {
      tbody.innerHTML = '';
      if (empty) empty.style.display = 'block';
      if (payBtn) payBtn.disabled = true;
      updateSummaryPanel();
      return;
    }
    if (empty) empty.style.display = 'none';
    if (payBtn) payBtn.disabled = false;
    var html = '';
    state.cart.forEach(function (line, idx) {
      var lineTotal = line.qty * line.price - (line.discount || 0);
      var initial = (line.itemname || '?').charAt(0).toUpperCase();
      html += '<tr>' +
        '<td>' + (idx + 1) + '</td>' +
        '<td><div class="pos-shop__cart-item">' +
        '<div class="pos-shop__cart-thumb">' + initial + '</div>' +
        '<div class="pos-shop__cart-item-text">' +
        '<div class="pos-shop__cart-item-name" title="' + escapeAttr(line.itemname) + '">' + escapeHtml(line.itemname) + '</div>' +
        '<div class="pos-shop__cart-item-code">' + escapeHtml(line.manufacturerid || line.itemcode) + '</div>' +
        '</div></div></td>' +
        '<td><div class="pos-shop__qty-ctrl">' +
        '<button type="button" class="pos-shop__qty-btn" data-action="dec" data-code="' + line.itemcode + '">−</button>' +
        '<span class="pos-shop__qty-val">' + line.qty + '</span>' +
        '<button type="button" class="pos-shop__qty-btn" data-action="inc" data-code="' + line.itemcode + '">+</button>' +
        '</div></td>' +
        '<td>' + money(line.price) + '</td>' +
        '<td>' + money(line.discount || 0) + '</td>' +
        '<td>' + money(lineTotal) + '</td>' +
        '<td><button type="button" class="pos-shop__cart-remove" data-code="' + line.itemcode + '" title="Remove"><i class="bi bi-trash"></i></button></td>' +
        '</tr>';
    });
    tbody.innerHTML = html;
    tbody.querySelectorAll('.pos-shop__qty-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var code = btn.dataset.code;
        updateCartQty(code, btn.dataset.action === 'inc' ? 1 : -1);
      });
    });
    tbody.querySelectorAll('.pos-shop__cart-remove').forEach(function (btn) {
      btn.addEventListener('click', function () { removeFromCart(btn.dataset.code); });
    });
    updateSummaryPanel();
  }

  function updateSummaryPanel() {
    var t = cartTotals();
    setText('#posShopSubtotal', money(t.subtotal));
    setText('#posShopDiscount', money(t.discount));
    setText('#posShopTax', money(t.tax));
    setText('#posShopGrandTotal', fmtDisplay(t.grand));
    setText('#posShopTotalItems', String(t.lines));
    setText('#posShopTotalQty', String(t.qty));
  }

  function renderFooter() {
    var t = cartTotals();
    setText('#posShopFooterGrand', fmtDisplay(t.grand));
    setText('#posShopFooterDiscount', money(t.discount));
    setText('#posShopFooterNet', fmtDisplay(t.grand));
    setText('#posShopFooterPoints', '0');
    updateSummaryPanel();
  }

  function setText(sel, val) {
    var el = $(sel);
    if (el) el.textContent = val;
  }

  function escapeHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, '&#39;');
  }

  function loadCategories() {
    if (!cfg.categoriesUrl) return Promise.resolve();
    return fetch(cfg.categoriesUrl, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j && j.success) state.categories = j.categories || [];
        renderCategories();
      })
      .catch(function () { renderCategories(); });
  }

  function loadProducts() {
    if (!cfg.productsUrl) return;
    state.loading = true;
    renderProducts();
    var params = new URLSearchParams();
    params.set('page', String(state.page));
    params.set('per_page', String(cfg.perPage));
    if (state.search) params.set('search', state.search);
    if (state.activeCategory != null) params.set('category_code', String(state.activeCategory));
    fetch(cfg.productsUrl + '?' + params.toString(), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        state.loading = false;
        if (j && j.success) {
          state.products = (j.products || []).map(normProduct);
          state.totalCount = Number(j.total_count) || 0;
        } else {
          state.products = [];
          state.totalCount = 0;
        }
        renderProducts();
        renderPagination();
      })
      .catch(function () {
        state.loading = false;
        state.products = [];
        state.totalCount = 0;
        renderProducts();
        renderPagination();
      });
  }

  function searchBarcode(query) {
    if (!cfg.barcodeUrl || !query) return;
    fetch(cfg.barcodeUrl + '?search=' + encodeURIComponent(query) + '&limit=1', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j && j.success && j.items && j.items.length) {
          var it = j.items[0];
          addToCart(normProduct({
            itemcode: it.itemcode,
            itemname: it.itemname,
            manufacturerid: it.barcode,
            baseuom: it.uom,
            retailprice: it.price,
            currentstock: 99
          }));
          var inp = $('#posShopSearch');
          if (inp) inp.value = '';
          state.search = '';
        } else {
          state.search = query;
          state.page = 1;
          loadProducts();
        }
      })
      .catch(function () {
        state.search = query;
        state.page = 1;
        loadProducts();
      });
  }

  var customerTimer = null;
  function searchCustomers(q) {
    if (!cfg.customersUrl) return;
    var suggest = $('#posShopCustomerSuggest');
    if (!suggest) return;
    if (!q) {
      suggest.classList.remove('is-open');
      suggest.innerHTML = '';
      return;
    }
    fetch(cfg.customersUrl + '?q=' + encodeURIComponent(q) + '&limit=20', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (!j || !j.success || !j.customers || !j.customers.length) {
          suggest.classList.remove('is-open');
          return;
        }
        var html = '';
        j.customers.forEach(function (c) {
          var code = c.code != null ? c.code : c.CODE;
          var name = (c.name || c.NAME || '').trim();
          html += '<button type="button" data-code="' + escapeAttr(code) + '" data-name="' + escapeAttr(name) + '">' +
            escapeHtml(code) + ' — ' + escapeHtml(name) + '</button>';
        });
        suggest.innerHTML = html;
        suggest.classList.add('is-open');
        suggest.querySelectorAll('button').forEach(function (btn) {
          btn.addEventListener('click', function () {
            state.customer = { code: btn.dataset.code, name: btn.dataset.name };
            setText('#posShopCustomerDisplay', state.customer.name);
            var inp = $('#posShopCustomerSearch');
            if (inp) inp.value = '';
            suggest.classList.remove('is-open');
          });
        });
      });
  }

  function initClock() {
    var el = $('#posShopDateTime');
    if (!el) return;
    function tick() {
      var d = new Date();
      var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      var h = d.getHours();
      var ampm = h >= 12 ? 'PM' : 'AM';
      h = h % 12 || 12;
      var min = String(d.getMinutes()).padStart(2, '0');
      el.textContent = String(d.getDate()).padStart(2, '0') + ' ' + months[d.getMonth()] + ' ' + d.getFullYear() +
        ' ' + h + ':' + min + ' ' + ampm;
    }
    tick();
    setInterval(tick, 30000);
  }

  function initSearch() {
    var inp = $('#posShopSearch');
    if (!inp) return;
    var timer = null;
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        var q = inp.value.trim();
        if (q) searchBarcode(q);
      }
    });
    inp.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        state.search = inp.value.trim();
        state.page = 1;
        loadProducts();
      }, 350);
    });
    inp.addEventListener('focus', function () {
      inp.select();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'F1') {
        e.preventDefault();
        inp.focus();
      }
    });
  }

  function initCustomer() {
    var inp = $('#posShopCustomerSearch');
    if (!inp) return;
    inp.addEventListener('input', function () {
      clearTimeout(customerTimer);
      customerTimer = setTimeout(function () { searchCustomers(inp.value.trim()); }, 300);
    });
    document.addEventListener('click', function (e) {
      var suggest = $('#posShopCustomerSuggest');
      if (suggest && !suggest.contains(e.target) && e.target !== inp) {
        suggest.classList.remove('is-open');
      }
    });
  }

  function initTenders() {
    $$('.pos-shop__tender').forEach(function (btn) {
      btn.addEventListener('click', function () {
        state.tender = (btn.dataset.tender || 'CASH').toUpperCase();
        $$('.pos-shop__tender').forEach(function (b) { b.classList.remove('is-selected'); });
        btn.classList.add('is-selected');
      });
    });
    var cash = $('.pos-shop__tender--cash');
    if (cash) cash.classList.add('is-selected');
  }

  function transferToBilling() {
    if (!state.cart.length) return;
    try {
      sessionStorage.setItem('pos_shop_transfer', JSON.stringify({
        items: state.cart,
        customer: state.customer,
        tender: state.tender,
        ts: Date.now()
      }));
    } catch (e) { /* ignore */ }
    window.location.href = cfg.billingUrl + '?shop_transfer=1';
  }

  function initPayment() {
    var payBtn = $('#posShopPayBtn');
    if (payBtn) payBtn.addEventListener('click', transferToBilling);
    $$('[data-shop-action="payment"]').forEach(function (btn) {
      btn.addEventListener('click', transferToBilling);
    });
  }

  function initCounterDisplay() {
    var counterEl = $('#posShopCounter');
    var whEl = $('#posShopWarehouse');
    if (counterEl) {
      var code = root.dataset.counterCode || '';
      var name = (root.dataset.counterName || '').trim();
      if (name && /^POS/i.test(name)) {
        counterEl.textContent = name + ' Counter';
      } else if (code && name) {
        counterEl.textContent = code + ' — ' + name;
      } else if (name) {
        counterEl.textContent = name;
      } else if (code) {
        counterEl.textContent = code + ' Counter';
      } else {
        counterEl.textContent = '—';
      }
    }
    if (whEl) {
      whEl.textContent = root.dataset.warehouseCode || '—';
    }
  }

  initClock();
  initSearch();
  initCustomer();
  initTenders();
  initPayment();
  initCounterDisplay();
  renderCart();
  renderFooter();
  loadCategories().then(loadProducts);
})();
