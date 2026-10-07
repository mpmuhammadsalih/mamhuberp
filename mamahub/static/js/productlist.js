// Product List JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('itemSearch');
    const searchClear = document.getElementById('searchClear');
    const itemTable = document.getElementById('itemTable');
    const pageRoot = document.querySelector('.im-productlist-page');
    const itemsApi = (pageRoot && pageRoot.dataset && pageRoot.dataset.itemsApi) ? pageRoot.dataset.itemsApi : '/productlist/api/items';
    const kpisApi = (pageRoot && pageRoot.dataset && pageRoot.dataset.kpisApi) ? pageRoot.dataset.kpisApi : '/productlist/api/kpis';
    const exportApi = (pageRoot && pageRoot.dataset && pageRoot.dataset.exportUrl) ? pageRoot.dataset.exportUrl : '/productlist/export';
    const itemmasterBaseUrl = (pageRoot && pageRoot.dataset && pageRoot.dataset.itemmasterUrl) ? pageRoot.dataset.itemmasterUrl : '/itemmaster';
    const itemListMeta = document.getElementById('itemListMeta');
    const infiniteScrollStatus = document.getElementById('itemInfiniteScrollStatus');
    const infiniteScrollSentinel = document.getElementById('itemInfiniteScrollSentinel');
    const filterBtn = document.getElementById('filterBtn');
    const exportBtn = document.getElementById('exportBtn');
    const exportBtnInline = document.getElementById('exportBtnInline');
    const itemSearchBtn = document.getElementById('itemSearchBtn');
    const itemListResetInline = document.getElementById('itemListResetInline');
    const itemListClearFilters = document.getElementById('itemListClearFilters');
    const filterModal = document.getElementById('filterModal');
    const closeFilterModal = document.getElementById('closeFilterModal');
    const applyFilters = document.getElementById('applyFilters');
    const clearFilters = document.getElementById('clearFilters');
    let lastSearchValue = '';
    let infiniteScrollLoading = false;
    let infiniteScrollDone = false;
    let infiniteScrollLoaded = itemTable ? itemTable.querySelectorAll('tbody tr.item-row').length : 0;
    let infiniteScrollPage = Number(pageRoot?.dataset?.currentPage || '1') || 1;
    let infiniteScrollTotalPages = Number(pageRoot?.dataset?.totalPages || '1') || 1;
    // Must match SSR page size so page=2 does not skip rows.
    const infiniteScrollPerPage = Number(pageRoot?.dataset?.itemsPerPage || '50') || 50;
    let infiniteScrollTotalCount = Number(pageRoot?.dataset?.totalCount || String(infiniteScrollLoaded)) || infiniteScrollLoaded;

    function formatKpiInt(n) {
        const v = Number(n);
        if (!Number.isFinite(v)) return '0';
        return Math.round(v).toLocaleString();
    }
    function formatKpiMoney(n) {
        const v = Number(n);
        if (!Number.isFinite(v)) return '0.00';
        return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    async function loadDeferredKpis() {
        const grid = document.getElementById('imStatGrid');
        if (!grid || grid.dataset.kpisDeferred !== '1') return;
        try {
            const url = `${kpisApi}?${new URLSearchParams(window.location.search).toString()}`;
            const res = await fetch(url, {
                credentials: 'same-origin',
                headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success || !data.kpis) return;
            const k = data.kpis;
            const set = (key, text) => {
                const el = grid.querySelector(`[data-kpi="${key}"]`);
                if (el) el.textContent = text;
            };
            if (k.total_items != null) set('total_items', formatKpiInt(k.total_items));
            if (k.active_items != null) set('active_items', formatKpiInt(k.active_items));
            if (k.inactive_items != null) set('inactive_items', formatKpiInt(k.inactive_items));
            if (k.low_stock_items != null) set('low_stock_items', formatKpiInt(k.low_stock_items));
            if (k.inventory_value != null) set('inventory_value', formatKpiMoney(k.inventory_value));
            grid.dataset.kpisDeferred = '0';
        } catch (e) {
            /* keep placeholders */
        }
    }
    // Fill KPI cards after first paint (inventory value aggregate is expensive).
    setTimeout(loadDeferredKpis, 0);
    
    // Get current sort parameters from URL
    const urlParams = new URLSearchParams(window.location.search);
    const currentSort = urlParams.get('sort') || '';
    const currentOrder = urlParams.get('order') || '';
    
    // Initialize sort indicators
    initializeSortIndicators();

    function itemUrl(itemCode, edit) {
        const params = new URLSearchParams();
        params.set('item_code', itemCode || '');
        if (edit) params.set('edit', '1');
        return `${itemmasterBaseUrl}?${params.toString()}`;
    }

    function clean(value, fallback = '-') {
        const text = String(value ?? '').trim();
        return text || fallback;
    }

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, function(ch) {
            return {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;',
            }[ch];
        });
    }

    function itemEditUrl(itemCode, edit) {
        return itemUrl(itemCode, edit);
    }

    function rowText(value, fallback = '-') {
        return escapeHtml(clean(value, fallback));
    }

    function rowNumber(value, decimals) {
        const n = Number(String(value ?? '').replace(/,/g, ''));
        return Number.isFinite(n) ? n.toFixed(decimals) : (0).toFixed(decimals);
    }

    function itemStatusHtml(item) {
        const stockQty = Number(String(item?.currentstock ?? '0').replace(/,/g, ''));
        if (String(item?.itemflag || 'Y').toUpperCase() === 'N') {
            return '<span class="co-status co-status--inactive">Inactive</span>';
        }
        if (Number.isFinite(stockQty) && stockQty <= 0) {
            return '<span class="co-status co-status--low">Low Stock</span>';
        }
        return '<span class="co-status">Active</span>';
    }

    function stockClass(value) {
        const stockQty = Number(String(value ?? '0').replace(/,/g, ''));
        if (!Number.isFinite(stockQty)) return 'im-stock-low';
        if (stockQty < 0) return 'im-stock-negative';
        if (stockQty === 0) return 'im-stock-low';
        return 'im-stock-positive';
    }

    function createItemRow(item, absoluteIndex) {
        const row = document.createElement('tr');
        row.className = 'item-row';
        row.dataset.itemCode = item?.itemcode || '';
        row.dataset.locationcode = item?.locationcode || '';
        row.dataset.manufacturerid = item?.manufacturerid || '';
        row.dataset.itemname = item?.itemname || '';
        row.dataset.baseuom = item?.baseuom || '';
        row.dataset.costprice = item?.costprice || '0';
        row.dataset.averagecost = item?.averagecost || '0';
        row.dataset.currentstock = item?.currentstock || '0';
        row.dataset.retailprice = item?.retailprice || '0';
        row.dataset.wholesaleprice = item?.wholesaleprice || '0';
        row.dataset.categoryname = item?.categoryname || '';
        row.dataset.brandname = item?.brandname || '';
        row.dataset.suppliername = item?.suppliername || '';
        row.dataset.itemflag = item?.itemflag || 'Y';

        const code = row.dataset.itemCode;
        const viewHref = escapeHtml(itemEditUrl(code, false));
        const editHref = escapeHtml(itemEditUrl(code, true));
        row.innerHTML = `
            <td class="sl-no">${absoluteIndex}</td>
            <td><a href="${viewHref}" class="grn-link im-item-code-link" onclick="event.stopPropagation();">${rowText(code)}</a></td>
            <td class="col-manufacturerid">${rowText(item?.manufacturerid)}</td>
            <td class="col-itemname" title="${rowText(item?.itemname)}">${rowText(item?.itemname)}</td>
            <td class="col-uom">${rowText(item?.baseuom)}</td>
            <td class="col-costprice num">${rowNumber(item?.costprice, 2)}</td>
            <td class="num">${rowNumber(item?.averagecost, 2)}</td>
            <td class="num">${rowNumber(item?.retailprice, 2)}</td>
            <td class="num ${stockClass(item?.currentstock)}">${rowNumber(item?.currentstock, 3)}</td>
            <td>${itemStatusHtml(item)}</td>
            <td style="text-align:center;">
                <span class="im-row-actions">
                    <a href="${viewHref}" class="btn-view im-row-action" title="View" onclick="event.stopPropagation();">View</a>
                    <a href="${editHref}" class="btn-view im-row-action" title="Edit" onclick="event.stopPropagation();">Edit</a>
                </span>
            </td>
        `;
        return row;
    }

    function updateInfiniteScrollStatus(message, isError) {
        if (!infiniteScrollStatus) return;
        infiniteScrollStatus.textContent = message || `Showing ${infiniteScrollLoaded} of ${infiniteScrollTotalCount} items.`;
        infiniteScrollStatus.classList.toggle('is-error', Boolean(isError));
        infiniteScrollStatus.style.cursor = (!infiniteScrollDone && !infiniteScrollLoading) ? 'pointer' : 'default';
    }

    function redirectToLoginAfterAuthFailure() {
        infiniteScrollDone = true;
        var nextPath = window.location.pathname + window.location.search;
        window.location.href = '/auth/login?next=' + encodeURIComponent(nextPath);
    }

    function handleListApiAuthFailure(res, data) {
        if (res && res.status === 401) {
            redirectToLoginAfterAuthFailure();
            return true;
        }
        var errText = String((data && (data.error || data.message)) || '').trim().toLowerCase();
        if (errText === 'unauthorized' || errText === 'not authenticated') {
            redirectToLoginAfterAuthFailure();
            return true;
        }
        if (res && res.status === 403) {
            infiniteScrollDone = true;
            updateInfiniteScrollStatus('You do not have permission to load more items.', true);
            return true;
        }
        return false;
    }

    function buildItemsApiUrl(nextPage) {
        const params = new URLSearchParams(window.location.search);
        params.set('page', String(nextPage));
        params.set('per_page', String(infiniteScrollPerPage));
        return `${itemsApi}?${params.toString()}`;
    }

    async function loadNextItemsPage() {
        if (!itemTable || infiniteScrollLoading || infiniteScrollDone) return;
        if (infiniteScrollPage >= infiniteScrollTotalPages) {
            infiniteScrollDone = true;
            updateInfiniteScrollStatus(`All ${infiniteScrollTotalCount} items loaded.`);
            return;
        }

        const tbody = itemTable.querySelector('tbody');
        if (!tbody) return;
        infiniteScrollLoading = true;
        const nextPage = infiniteScrollPage + 1;
        const started = performance.now();
        updateInfiniteScrollStatus(`Loading more items... (${infiniteScrollLoaded} of ${infiniteScrollTotalCount})`);

        try {
            const res = await fetch(buildItemsApiUrl(nextPage), {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
            });
            const data = await res.json().catch(() => ({}));
            if (handleListApiAuthFailure(res, data)) return;
            if (!res.ok || !data.success) {
                throw new Error(data.error || data.message || `Load failed (${res.status})`);
            }

            const items = Array.isArray(data.items) ? data.items : [];
            const noDataRow = document.getElementById('itemNoData');
            if (noDataRow) noDataRow.remove();
            items.forEach((item, idx) => {
                tbody.appendChild(createItemRow(item, infiniteScrollLoaded + idx + 1));
            });
            infiniteScrollLoaded += items.length;
            infiniteScrollPage = Number(data.page || nextPage) || nextPage;
            infiniteScrollTotalPages = Number(data.total_pages || infiniteScrollTotalPages) || infiniteScrollTotalPages;
            infiniteScrollTotalCount = Number(data.total_count || infiniteScrollTotalCount) || infiniteScrollTotalCount;

            if (itemListMeta) {
                itemListMeta.textContent = `${infiniteScrollTotalCount} records`;
            }
            const elapsed = performance.now() - started;
            console.info(`[TIMING productlist scroll] page=${infiniteScrollPage} rows=${items.length} loaded=${infiniteScrollLoaded}/${infiniteScrollTotalCount} elapsed_ms=${elapsed.toFixed(1)}`);

            if (infiniteScrollPage >= infiniteScrollTotalPages || items.length === 0) {
                infiniteScrollDone = true;
                updateInfiniteScrollStatus(`All ${infiniteScrollLoaded} items loaded.`);
            } else {
                updateInfiniteScrollStatus(`Showing ${infiniteScrollLoaded} of ${infiniteScrollTotalCount} items. Scroll down or click here to load more.`);
            }
        } catch (err) {
            updateInfiniteScrollStatus(err && err.message ? err.message : 'Could not load more items.', true);
        } finally {
            infiniteScrollLoading = false;
        }
    }

    function initializeInfiniteScroll() {
        if (!infiniteScrollSentinel || !itemTable || infiniteScrollTotalPages <= infiniteScrollPage) {
            infiniteScrollDone = true;
            updateInfiniteScrollStatus(`All ${infiniteScrollLoaded} items loaded.`);
            return;
        }
        const pagination = document.querySelector('.im-productlist-page .im-pagination');
        if (pagination) pagination.style.display = 'none';
        updateInfiniteScrollStatus(`Showing ${infiniteScrollLoaded} of ${infiniteScrollTotalCount} items. Scroll down or click here to load more.`);
        if ('IntersectionObserver' in window) {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) loadNextItemsPage();
                });
            }, { rootMargin: '500px 0px' });
            observer.observe(infiniteScrollSentinel);
        } else {
            window.addEventListener('scroll', function() {
                const remaining = document.documentElement.scrollHeight - window.innerHeight - window.scrollY;
                if (remaining < 500) loadNextItemsPage();
            }, { passive: true });
        }
        infiniteScrollStatus?.addEventListener('click', function() {
            loadNextItemsPage();
        });
    }

    function openItemRow(row) {
        if (!row || !row.dataset.itemCode) return;
        window.location.href = itemUrl(row.dataset.itemCode, false);
    }

    if (itemTable) {
        itemTable.addEventListener('click', function(e) {
            if (e.target.closest('a, button')) return;
            const row = e.target.closest('tr.item-row');
            if (!row) return;
            openItemRow(row);
        });
    }
    initializeInfiniteScroll();
    
    if (itemListClearFilters) {
        itemListClearFilters.addEventListener('click', function() {
            window.location.href = '/productlist';
        });
    }
    if (itemListResetInline) {
        itemListResetInline.addEventListener('click', function() {
            window.location.href = '/productlist';
        });
    }
    if (searchClear && searchInput && searchInput.value.trim()) {
        searchClear.style.display = 'block';
    }
    if (itemSearchBtn && searchInput) {
        itemSearchBtn.addEventListener('click', function() {
            const query = searchInput.value.trim();
            if (query) {
                window.location.href = `/productlist?search=${encodeURIComponent(query)}`;
            } else {
                window.location.href = '/productlist';
            }
        });
    }

    // Search functionality — Space debounced client filter; Enter submits server search
    if (searchInput) {
        let searchTimeout;
        
        searchInput.addEventListener('keydown', function(e) {
            // Trigger search on Space key (after space is added)
            if (e.key === ' ') {
                // Clear any pending timeout
                clearTimeout(searchTimeout);
                
                // Allow space to be added first, then search with debounce
                searchTimeout = setTimeout(() => {
                    const query = this.value.trim();
                    if (query !== lastSearchValue) {
                        lastSearchValue = query;
                        
                        // Show/hide clear button
                        if (searchClear) {
                            searchClear.style.display = query ? 'block' : 'none';
                        }
                        
                        // Filter table client-side (only if we have items loaded)
                        if (itemTable && itemTable.querySelectorAll('tbody tr').length > 0) {
                            filterTable(query.toLowerCase());
                        }
                    }
                }, 100); // Small delay to allow space to be added
            }
            
            // Enter key to submit search to server
            if (e.key === 'Enter') {
                e.preventDefault();
                clearTimeout(searchTimeout);
                const query = this.value.trim();
                if (query) {
                    window.location.href = `/productlist?search=${encodeURIComponent(query)}`;
                } else {
                    window.location.href = '/productlist';
                }
            }
        });

        // Show/hide clear button and reset table when text is cleared
        searchInput.addEventListener('input', function() {
            const query = this.value.trim();
            
            // Show/hide clear button
            if (searchClear) {
                searchClear.style.display = query ? 'block' : 'none';
            }
            
            // If search is cleared, reset table to show all rows
            if (!query) {
                lastSearchValue = '';
                if (itemTable) {
                    const rows = itemTable.querySelectorAll('tbody tr');
                    rows.forEach((row) => {
                        row.style.display = '';
                    });
                }
            }
        });
    }

    // Clear search
    if (searchClear) {
        searchClear.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            if (searchInput) {
                searchInput.value = '';
                lastSearchValue = '';
                this.style.display = 'none';
                
                // Reset table to show all rows immediately
                if (itemTable) {
                    const rows = itemTable.querySelectorAll('tbody tr');
                    rows.forEach((row) => {
                        row.style.display = '';
                    });
                }
                
                // Redirect to clear server-side search parameter
                window.location.href = '/productlist';
            }
        });
    }

    function filterTable(query) {
        if (!itemTable) return;

        const tbody = itemTable.querySelector('tbody');
        if (!tbody) return;

        // Use requestAnimationFrame for better performance
        requestAnimationFrame(() => {
            const rows = tbody.querySelectorAll('tr');
            if (rows.length === 0) return;

            let visibleCount = 0;
            const queryLower = query.toLowerCase();

            rows.forEach((row) => {
                const cells = row.querySelectorAll('td');
                if (cells.length < 4) {
                    row.style.display = '';
                    visibleCount++;
                    return;
                }

                const locationCode = (row.dataset.locationcode || '').toLowerCase();
                const itemCode = (row.dataset.itemCode || cells[1]?.textContent || '').toLowerCase();
                const manufacturerId = (row.dataset.manufacturerid || '').toLowerCase();
                const itemName = (row.dataset.itemname || cells[2]?.textContent || '').toLowerCase();
                const categoryName = (row.dataset.categoryname || cells[3]?.textContent || '').toLowerCase();

                if (!query.trim()) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    let matches = false;
                    
                    // If query contains *, treat it as a single pattern (e.g., "chilly*star" matches "chilly five star")
                    if (query.includes('*')) {
                        // Convert * to regex pattern: * becomes .* (matches any characters)
                        // Escape other regex special characters but keep * as wildcard
                        let pattern = queryLower;
                        // Escape regex special characters except *
                        pattern = pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
                        // Convert * to .* for regex wildcard matching
                        pattern = pattern.replace(/\\\*/g, '.*');
                        const regex = new RegExp(pattern, 'i');
                        
                        matches = regex.test(locationCode) ||
                                 regex.test(itemCode) ||
                                 regex.test(manufacturerId) ||
                                 regex.test(itemName) ||
                                 regex.test(categoryName);
                    } else {
                        // If no *, split by spaces and check if all tokens match (AND logic)
                        const tokens = queryLower.split(/\s+/).filter(Boolean);
                        matches = tokens.length === 0 || tokens.every((token) =>
                            locationCode.includes(token) ||
                            itemCode.includes(token) ||
                            manufacturerId.includes(token) ||
                            itemName.includes(token) ||
                            categoryName.includes(token)
                        );
                    }
                    
                    row.style.display = matches ? '' : 'none';
                    if (matches) visibleCount++;
                }
            });

            // Filtering applied (no server round-trip for client-side filter)
        });
    }
    
    if (filterBtn) {
        filterBtn.addEventListener('click', function() {
            ensureFilterOptionsLoaded().finally(function() {
                if (filterModal) {
                    filterModal.style.display = 'flex';
                }
            });
        });
    }
    document.querySelectorAll('.im-open-filter').forEach(function(btn) {
        btn.addEventListener('click', function() {
            ensureFilterOptionsLoaded().finally(function() {
                if (filterModal) {
                    filterModal.style.display = 'flex';
                }
            });
        });
    });
    
    if (closeFilterModal) {
        closeFilterModal.addEventListener('click', function() {
            if (filterModal) {
                filterModal.style.display = 'none';
            }
        });
    }
    
    // Close modal when clicking outside
    if (filterModal) {
        filterModal.addEventListener('click', function(e) {
            if (e.target === filterModal) {
                filterModal.style.display = 'none';
            }
        });
    }
    
    // Store filter data
    let brandsData = [];
    let categoriesData = [];
    let suppliersData = [];
    
    let filterOptionsLoaded = false;
    let filterOptionsLoadPromise = null;

    function ensureFilterOptionsLoaded() {
        if (filterOptionsLoaded) {
            return Promise.resolve();
        }
        if (filterOptionsLoadPromise) {
            return filterOptionsLoadPromise;
        }
        filterOptionsLoadPromise = Promise.all([
            fetch('/api/filters/brands').then(function(r) { return r.json(); }),
            fetch('/api/filters/categories').then(function(r) { return r.json(); }),
            fetch('/api/filters/suppliers').then(function(r) { return r.json(); }),
        ]).then(function(results) {
            var b = results[0];
            var c = results[1];
            var s = results[2];
            if (b.success && b.data) {
                brandsData = b.data;
                populateModalTable('brandModalTable', brandsData);
                initializeFilterPopup('brand', brandsData);
            }
            if (c.success && c.data) {
                categoriesData = c.data;
                populateModalTable('categoryModalTable', categoriesData);
                initializeFilterPopup('category', categoriesData);
            }
            if (s.success && s.data) {
                suppliersData = s.data;
                populateModalTable('supplierModalTable', suppliersData);
                initializeFilterPopup('supplier', suppliersData);
            }
            filterOptionsLoaded = true;
            filterOptionsLoadPromise = null;
        }).catch(function(err) {
            console.error('Error loading filter options:', err);
            filterOptionsLoadPromise = null;
        });
        return filterOptionsLoadPromise;
    }
    
    // Populate modal table with data
    function populateModalTable(tableId, data) {
        const table = document.getElementById(tableId);
        if (!table) return;
        
        const tbody = table.querySelector('tbody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        data.forEach(item => {
            const row = document.createElement('tr');
            row.dataset.code = item.code;
            row.dataset.name = item.name;
            row.dataset.text = `${item.code} ${item.name}`.toLowerCase();
            row.innerHTML = `
                <td>${item.code}</td>
                <td>${item.name}</td>
            `;
            tbody.appendChild(row);
        });
    }
    
    // Initialize filter popup functionality
    function initializeFilterPopup(type, data) {
        const input = document.getElementById(`${type}Filter`);
        const picker = document.getElementById(`${type}Picker`);
        const clear = document.getElementById(`${type}Clear`);
        const modal = document.getElementById(`${type}Modal`);
        const modalSearch = document.getElementById(`${type}ModalSearch`);
        const modalClear = document.getElementById(`${type}ModalClear`);
        const modalTable = document.getElementById(`${type}ModalTable`);
        const codeInput = document.getElementById(`${type}Code`);
        
        if (!input || !picker || !modal || !modalTable) return;
        
        // Open modal
        picker.addEventListener('click', () => {
            modal.classList.remove('hidden');
            if (modalSearch) {
                modalSearch.value = '';
                filterModalRows(modalTable, '');
                modalSearch.focus();
            }
        });
        
        input.addEventListener('click', () => {
            modal.classList.remove('hidden');
            if (modalSearch) {
                modalSearch.value = '';
                filterModalRows(modalTable, '');
                modalSearch.focus();
            }
        });
        
        // Close modal
        modal.addEventListener('click', (e) => {
            if (e.target.dataset.close === `${type}Modal` || e.target.classList.contains('modal__close')) {
                modal.classList.add('hidden');
            }
        });
        
        // Search in modal
        if (modalSearch) {
            modalSearch.addEventListener('input', (e) => {
                filterModalRows(modalTable, e.target.value.toLowerCase());
            });
        }
        
        // Clear search
        if (modalClear) {
            modalClear.addEventListener('click', () => {
                if (modalSearch) {
                    modalSearch.value = '';
                    filterModalRows(modalTable, '');
                    modalSearch.focus();
                }
            });
        }
        
        // Select from table
        modalTable.addEventListener('click', (e) => {
            const row = e.target.closest('tr');
            if (!row || !row.dataset.code) return;
            
            const code = row.dataset.code;
            const name = row.dataset.name;
            
            input.value = `${code} - ${name}`;
            if (codeInput) {
                codeInput.value = code;
            }
            if (clear) {
                clear.style.display = 'block';
            }
            
            modal.classList.add('hidden');
        });
        
        // Clear selection
        if (clear) {
            clear.addEventListener('click', () => {
                input.value = '';
                if (codeInput) {
                    codeInput.value = '';
                }
                clear.style.display = 'none';
            });
        }
    }
    
    // Filter modal table rows
    function filterModalRows(table, searchTerm) {
        if (!table) return;
        const rows = table.querySelectorAll('tbody tr');
        rows.forEach(row => {
            const text = (row.dataset.text || '').toLowerCase();
            if (!searchTerm || text.includes(searchTerm)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    }
    
    // Apply filters
    if (applyFilters) {
        applyFilters.addEventListener('click', function() {
            const form = document.getElementById('filterForm');
            if (!form) return;
            
            const formData = new FormData(form);
            const params = new URLSearchParams();
            
            // Preserve current sort parameters
            if (currentSort) {
                params.append('sort', currentSort);
            }
            if (currentOrder) {
                params.append('order', currentOrder);
            }
            
            // Get stock filter
            const stockFilter = formData.get('stockFilter');
            if (stockFilter && stockFilter !== 'all') {
                params.append('stockFilter', stockFilter);
            }
            
            // Get brand filter
            const brandCodeInput = document.getElementById('brandCode');
            if (brandCodeInput && brandCodeInput.value) {
                params.append('brandCode', brandCodeInput.value);
            }
            
            // Get category filter
            const categoryCodeInput = document.getElementById('categoryCode');
            if (categoryCodeInput && categoryCodeInput.value) {
                params.append('categoryCode', categoryCodeInput.value);
            }
            
            // Get supplier filter
            const supplierCodeInput = document.getElementById('supplierCode');
            if (supplierCodeInput && supplierCodeInput.value) {
                params.append('supplierCode', supplierCodeInput.value);
            }
            
            // Get item codes filter
            const itemCodes = formData.get('itemCodesFilter');
            if (itemCodes && itemCodes.trim()) {
                params.append('itemCodes', itemCodes.trim());
            }
            
            // Get current search value
            if (searchInput && searchInput.value.trim()) {
                params.append('search', searchInput.value.trim());
            }
            
            // Redirect with filter parameters
            const queryString = params.toString();
            window.location.href = `/productlist${queryString ? '?' + queryString : ''}`;
        });
    }
    
    // Clear filters
    if (clearFilters) {
        clearFilters.addEventListener('click', function() {
            const form = document.getElementById('filterForm');
            if (form) {
                form.reset();
                // Set stock filter to 'all'
                const stockAll = form.querySelector('input[value="all"]');
                if (stockAll) {
                    stockAll.checked = true;
                }
            }
            
            // Redirect to productlist without filters
            const searchParam = searchInput && searchInput.value.trim() 
                ? `?search=${encodeURIComponent(searchInput.value.trim())}` 
                : '';
            window.location.href = `/productlist${searchParam}`;
        });
    }
    
    // Initialize sort indicators based on current URL parameters
    function initializeSortIndicators() {
        if (currentSort && currentOrder) {
            const sortableHeader = document.querySelector(`th.sortable[data-sort="${currentSort}"]`);
            if (sortableHeader) {
                sortableHeader.classList.add(`sort-${currentOrder}`);
            }
        }
        
        // Add click handlers to sortable headers
        const sortableHeaders = document.querySelectorAll('th.sortable');
        sortableHeaders.forEach(header => {
            header.addEventListener('click', function() {
                const sortColumn = this.getAttribute('data-sort');
                if (!sortColumn) return;
                
                // Determine new sort order
                let newOrder = 'asc';
                if (currentSort === sortColumn && currentOrder === 'asc') {
                    newOrder = 'desc';
                }
                
                // Build new URL with sort parameters, preserving existing filters
                const params = new URLSearchParams(window.location.search);
                params.set('sort', sortColumn);
                params.set('order', newOrder);
                
                // Redirect with new sort parameters
                window.location.href = `/productlist?${params.toString()}`;
            });
        });
    }
    
    // Export to Excel functionality
    [exportBtn, exportBtnInline].forEach(function(btn) {
        if (!btn) return;
        btn.addEventListener('click', function() {
            exportToExcel();
        });
    });
    
    function exportToExcel() {
        const params = new URLSearchParams(window.location.search);
        params.delete('page');
        const url = `${exportApi}?${params.toString()}`;
        window.location.href = url;
    }
});
