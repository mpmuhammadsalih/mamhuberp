/**
 * GRN-style compact item picker (list rows) for Sales / Sales Return modals.
 */
(function (global) {
    function escAttr(value) {
        return String(value == null ? '' : value).replace(/"/g, '&quot;');
    }

    function formatStock(value) {
        const n = Number(value);
        if (!Number.isFinite(n)) return '0.000';
        return n.toFixed(3);
    }

    function dedupeList(list) {
        const seen = new Set();
        const out = [];
        (list || []).forEach((row) => {
            const key = [
                String(row.code != null ? row.code : ''),
                String(row.barcode || '').trim().toUpperCase(),
                String(row.uom || '').trim().toUpperCase(),
            ].join('|');
            if (seen.has(key)) return;
            seen.add(key);
            out.push(row);
        });
        return out;
    }

    function rowMatchesTokens(row, tokens) {
        if (!tokens.length) return true;
        const hay = (
            String(row.code || '') + ' '
            + String(row.barcode || '') + ' '
            + String(row.name || '')
        ).toLowerCase();
        return tokens.every((t) => hay.indexOf(t) !== -1);
    }

    function searchTokens(term) {
        return String(term || '').toLowerCase().split(/\s+/).filter(Boolean);
    }

    function filterCacheList(list, term) {
        const tokens = searchTokens(term);
        if (!tokens.length) return dedupeList(list || []);
        return dedupeList(list || []).filter((i) => rowMatchesTokens(i, tokens));
    }

    function renderList(bodyEl, searchEl, list) {
        if (!bodyEl) return;
        list = dedupeList(list);
        const tokens = searchTokens(searchEl && searchEl.value ? searchEl.value : '');
        const filtered = tokens.length
            ? list.filter((i) => rowMatchesTokens(i, tokens))
            : list;
        if (!filtered.length) {
            const hint = (searchEl && String(searchEl.value || '').trim())
                ? 'No matching items with stock. Try another code or name.'
                : 'No items with stock > 0. Switch warehouse or search by code.';
            bodyEl.innerHTML = '<div class="item-row item-empty">' + hint + '</div>';
            return;
        }
        bodyEl.innerHTML = filtered.map((i) => {
            const code = escAttr(i.code);
            const name = escAttr(i.name);
            const barcodeAttr = escAttr(i.barcode);
            const uomAttr = escAttr(i.uom || 'NOS');
            const cost = Number(i.cost != null ? i.cost : 0);
            const retail = Number(i.retail != null ? i.retail : 0);
            const modeRate = Number(i.rate != null ? i.rate : retail);
            const line1 = (i.code || '') + (i.name ? ' · ' + (i.name || '') : '');
            const stock = Number(i.stock != null ? i.stock : 0);
            const line2 = [
                String(i.barcode || '').trim(),
                i.uom || 'NOS',
                'S:' + formatStock(stock),
                'C:' + cost.toFixed(2),
                'R:' + modeRate.toFixed(2),
            ].filter(Boolean).join(' | ');
            const ownCls = String(i.ownproduct || '').toUpperCase() === 'Y' ? ' item-row--own' : '';
            return '<div class="item-row' + ownCls + '" tabindex="0"'
                + ' data-code="' + code + '"'
                + ' data-name="' + name + '"'
                + ' data-barcode="' + barcodeAttr + '"'
                + ' data-uom="' + uomAttr + '"'
                + ' data-cost="' + cost + '"'
                + ' data-retail="' + retail + '"'
                + ' data-rate="' + modeRate + '"'
                + ' data-wholesale="' + Number(i.wholesale || 0) + '"'
                + ' data-third="' + Number(i.third || 0) + '"'
                + ' data-branch="' + Number(i.branch || 0) + '"'
                + '><div class="item-line1">' + (line1 || '—') + '</div>'
                + '<div class="item-line2">' + (line2 || '—') + '</div></div>';
        }).join('');
    }

    function initSiItemPicker(config) {
        const modal = config.modalEl || document.getElementById(config.modalId || 'itemModal');
        const searchEl = config.searchEl || document.getElementById(config.searchId || 'itemSearch');
        const bodyEl = config.bodyEl || document.getElementById(config.bodyId || 'itemBody');
        if (!modal || !bodyEl) {
            return { openModal: function () {} };
        }

        let cache = [];
        let fullCache = [];
        let fetchAbort = null;
        let searchDebounce = null;
        let suppressSearch = false;

        function minSearchLen() {
            return config.minSearchLen != null ? config.minSearchLen : 2;
        }

        function selectRow(row) {
            if (!row || !row.dataset || !row.dataset.code) return;
            if (typeof config.onSelect === 'function') {
                Promise.resolve(config.onSelect(row)).then((result) => {
                    if (result === false) return;
                    modal.classList.add('hidden');
                }).catch(() => {});
                return;
            }
            modal.classList.add('hidden');
        }

        async function fetchItems(filterKey, searchTerm, signal) {
            if (typeof config.fetchItems !== 'function') return [];
            return config.fetchItems(filterKey, searchTerm, signal);
        }

        async function loadItems(searchTerm, showLoading, keepCacheOnError) {
            const term = String(searchTerm || '').trim();
            if (showLoading && bodyEl) {
                bodyEl.innerHTML = '<div class="item-row item-empty">' + (term ? 'Searching…' : 'Loading…') + '</div>';
            }
            if (fetchAbort) fetchAbort.abort();
            fetchAbort = new AbortController();
            const signal = fetchAbort.signal;
            const timeoutMs = config.fetchTimeoutMs || 25000;
            let timeoutId = null;
            try {
                const fetchPromise = fetchItems(config.getFilterKey ? config.getFilterKey() : 'all', searchTerm, signal);
                const items = await Promise.race([
                    fetchPromise,
                    new Promise(function (_, reject) {
                        timeoutId = setTimeout(function () { reject(new Error('timeout')); }, timeoutMs);
                    }),
                ]);
                if (timeoutId) clearTimeout(timeoutId);
                if (signal.aborted) return;
                cache = items || [];
                if (!term) {
                    fullCache = cache.slice();
                }
                renderList(bodyEl, searchEl, cache);
            } catch (err) {
                if (timeoutId) clearTimeout(timeoutId);
                if (err && err.name === 'AbortError') return;
                if (keepCacheOnError && cache.length) {
                    renderList(bodyEl, searchEl, cache);
                    return;
                }
                if (term && fullCache.length) {
                    cache = fullCache.slice();
                    renderList(bodyEl, searchEl, cache);
                    return;
                }
                cache = [];
                if (bodyEl) {
                    const msg = err && err.message === 'timeout'
                        ? 'Search timed out. Try a more specific code or name.'
                        : 'Failed to load items. Try searching by code or name.';
                    bodyEl.innerHTML = '<div class="item-row item-empty">' + msg + '</div>';
                }
            }
        }

        function openModal() {
            if (modal.classList.contains('hidden')) {
                if (typeof config.beforeOpen === 'function' && config.beforeOpen() === false) {
                    return;
                }
                modal.classList.remove('hidden');
                if (searchEl) {
                    suppressSearch = true;
                    searchEl.value = '';
                    suppressSearch = false;
                    searchEl.focus();
                }
                if (fullCache.length) {
                    cache = fullCache.slice();
                    renderList(bodyEl, searchEl, cache);
                } else {
                    loadItems('', true);
                }
                return;
            }
            if (searchEl) searchEl.focus();
        }

        modal.addEventListener('click', (e) => {
            if (e.target.dataset.close === modal.id || e.target.classList.contains('modal__close')) {
                modal.classList.add('hidden');
                if (typeof config.onClose === 'function') config.onClose();
            }
        });

        if (searchEl) {
            searchEl.addEventListener('input', () => {
                if (suppressSearch) return;
                const term = (searchEl.value || '').trim();
                const minLen = minSearchLen();
                if (searchDebounce) clearTimeout(searchDebounce);
                if (!term) {
                    if (fullCache.length) {
                        cache = fullCache.slice();
                        renderList(bodyEl, searchEl, cache);
                    } else {
                        loadItems('', !cache.length);
                    }
                    return;
                }
                if (term.length < minLen) {
                    renderList(bodyEl, searchEl, cache);
                    return;
                }
                const localHits = filterCacheList(cache, term);
                if (localHits.length) {
                    renderList(bodyEl, searchEl, cache);
                    return;
                }
                searchDebounce = setTimeout(function () {
                    searchDebounce = null;
                    loadItems(term, true, false);
                }, config.searchDebounceMs || 400);
            });
            searchEl.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    const first = bodyEl && bodyEl.querySelector('.item-row[data-code]');
                    if (first) first.focus();
                }
            });
        }

        if (bodyEl) {
            bodyEl.addEventListener('click', (e) => {
                const row = e.target.closest('.item-row');
                if (row && row.dataset.code) selectRow(row);
            });
            bodyEl.addEventListener('keydown', (e) => {
                const row = e.target.closest('.item-row');
                if (e.key === 'Enter') {
                    if (row && row.dataset.code) {
                        e.preventDefault();
                        selectRow(row);
                    }
                } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                    if (!row || !row.dataset.code) return;
                    const rows = Array.prototype.slice.call(bodyEl.querySelectorAll('.item-row[data-code]'));
                    const idx = rows.indexOf(row);
                    if (idx === -1) return;
                    e.preventDefault();
                    if (e.key === 'ArrowDown' && idx < rows.length - 1) rows[idx + 1].focus();
                    if (e.key === 'ArrowUp' && idx > 0) rows[idx - 1].focus();
                }
            });
        }

        modal.openModal = openModal;

        return {
            openModal,
            refresh: (searchTerm) => loadItems(searchTerm || '', false),
            renderCache: () => renderList(bodyEl, searchEl, cache),
        };
    }

    global.initSiItemPicker = initSiItemPicker;
})(typeof window !== 'undefined' ? window : globalThis);
