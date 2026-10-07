/**
 * Global typeahead lookup (Google-style suggestions below the input).
 * Markup: .global-lookup or .odoo-lookup with [data-search-url], __input, __value, __clear.
 * API: GET /api/lookup/<kind>?q=...&limit=6  (customer, category, item, supplier, …)
 */
(function (global) {
    'use strict';

    const SEL = {
        input: '.global-lookup__input, .odoo-lookup__input',
        value: '.global-lookup__value, .odoo-lookup__value',
        clear: '.global-lookup__clear, .odoo-lookup__clear',
        textSearch: '.global-lookup__text-search',
        option: '.global-lookup__option, .odoo-lookup__option',
        empty: '.global-lookup__empty, .odoo-lookup__empty',
        mark: '.global-lookup__mark, .odoo-lookup__mark',
    };

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function highlightLabel(label, term) {
        const text = String(label || '');
        const q = String(term || '').trim();
        if (!q) return esc(text);
        const lower = text.toLowerCase();
        const needle = q.toLowerCase();
        const idx = lower.indexOf(needle);
        if (idx < 0) return esc(text);
        return (
            esc(text.slice(0, idx))
            + '<mark class="global-lookup__mark odoo-lookup__mark">' + esc(text.slice(idx, idx + q.length)) + '</mark>'
            + esc(text.slice(idx + q.length))
        );
    }

    function initOdooLookup(root) {
        if (!root || root.dataset.odooLookupInit === '1') return;
        const searchUrl = (root.dataset.searchUrl || '').trim();
        const input = root.querySelector(SEL.input);
        const hidden = root.querySelector(SEL.value);
        const clearBtn = root.querySelector(SEL.clear);
        const textSearchEl = root.querySelector(SEL.textSearch)
            || (root.dataset.textSearchName
                ? (root.closest('form') || document).querySelector(
                    `[name="${root.dataset.textSearchName}"]`
                )
                : null);
        if (!searchUrl || !input) return;

        root.dataset.odooLookupInit = '1';
        const limit = Math.min(Math.max(parseInt(root.dataset.limit || '6', 10) || 6, 1), 20);
        const minChars = Math.max(parseInt(root.dataset.minChars || '1', 10) || 1, 0);
        const debounceMs = Math.max(parseInt(root.dataset.debounce || '120', 10) || 120, 50);

        let dropdown = root.querySelector('.global-lookup__dropdown, .odoo-lookup__dropdown');
        if (!dropdown) {
            dropdown = document.createElement('div');
            dropdown.className = 'global-lookup__dropdown odoo-lookup__dropdown';
            dropdown.setAttribute('role', 'listbox');
            dropdown.style.display = 'none';
            if (!root.id) {
                root.id = 'global-lookup-' + Math.random().toString(36).slice(2, 9);
            }
            dropdown.dataset.lookupOwner = root.id;
            document.body.appendChild(dropdown);
        }

        input.setAttribute('role', 'combobox');
        input.setAttribute('aria-autocomplete', 'list');
        input.setAttribute('aria-expanded', 'false');

        let timer = null;
        let abortCtrl = null;
        let activeIdx = -1;
        let lastRows = [];
        let listNavActive = false;

        function codeValue() {
            return hidden ? (hidden.value || '').trim() : '';
        }

        function setCodeValue(code) {
            if (hidden) hidden.value = code || '';
        }

        function syncTextSearchFallback(term) {
            if (!textSearchEl) return;
            if (codeValue()) {
                textSearchEl.value = '';
            } else {
                textSearchEl.value = (term || '').trim();
            }
        }

        function setOpen(open) {
            root.classList.toggle('is-open', open);
            input.setAttribute('aria-expanded', open ? 'true' : 'false');
        }

        function getOptions() {
            return dropdown.querySelectorAll(SEL.option);
        }

        function resetListNav() {
            listNavActive = false;
            activeIdx = -1;
            input.removeAttribute('aria-activedescendant');
        }

        function syncClear() {
            if (!clearBtn) return;
            const has = Boolean(codeValue() || (input.value || '').trim());
            clearBtn.hidden = !has;
        }

        function setSelection(code, label, row) {
            setCodeValue(code || '');
            input.value = label || '';
            if (code) syncTextSearchFallback('');
            syncClear();
            closeDropdown();
            const detail = {
                code: code || '',
                label: label || '',
                row: row || null,
            };
            input.dispatchEvent(new CustomEvent('global-lookup:select', { bubbles: true, detail }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }

        function positionDropdown() {
            const rect = input.getBoundingClientRect();
            const minW = Math.max(parseInt(root.dataset.dropdownMinWidth || '320', 10) || 320, rect.width);
            const maxW = Math.min(window.innerWidth - rect.left - 12, 480);
            const w = Math.max(minW, Math.min(rect.width, maxW));
            dropdown.style.position = 'fixed';
            dropdown.style.left = `${rect.left}px`;
            dropdown.style.top = `${rect.bottom + 2}px`;
            dropdown.style.width = `${w}px`;
            dropdown.style.maxWidth = `${maxW}px`;
        }

        function closeDropdown() {
            dropdown.style.display = 'none';
            dropdown.innerHTML = '';
            lastRows = [];
            resetListNav();
            setOpen(false);
        }

        function showDropdown() {
            positionDropdown();
            dropdown.style.display = 'block';
            setOpen(true);
        }

        function renderRows(rows, term) {
            lastRows = rows || [];
            resetListNav();
            if (!lastRows.length) {
                dropdown.innerHTML = '<div class="global-lookup__empty odoo-lookup__empty">No results</div>';
                showDropdown();
                return;
            }
            const owner = root.id || 'lookup';
            dropdown.innerHTML = lastRows.map((row, i) => {
                const code = row.code != null ? String(row.code) : '';
                const label = row.label || row.name || code;
                const line = label || `${code}`;
                const optId = `${owner}-opt-${i}`;
                return (
                    `<button type="button" class="global-lookup__option odoo-lookup__option" role="option" id="${optId}" data-idx="${i}" tabindex="-1">`
                    + '<span class="global-lookup__icon odoo-lookup__icon" aria-hidden="true">⌕</span>'
                    + `<span class="global-lookup__line odoo-lookup__line">${highlightLabel(line, term)}</span>`
                    + '</button>'
                );
            }).join('');
            showDropdown();
        }

        function highlightOption(idx, focusOption) {
            const opts = getOptions();
            if (!opts.length) return;
            const clamped = Math.max(0, Math.min(idx, opts.length - 1));
            activeIdx = clamped;
            opts.forEach((el, i) => {
                el.classList.toggle('is-active', i === clamped);
                el.setAttribute('aria-selected', i === clamped ? 'true' : 'false');
            });
            const active = opts[clamped];
            if (!active) return;
            active.scrollIntoView({ block: 'nearest' });
            input.setAttribute('aria-activedescendant', active.id || '');
            if (focusOption || listNavActive) {
                active.focus({ preventScroll: true });
            }
        }

        function enterListNavigation() {
            const opts = getOptions();
            if (!opts.length) return false;
            listNavActive = true;
            highlightOption(0, true);
            return true;
        }

        function moveList(delta) {
            const opts = getOptions();
            if (!opts.length) return;
            if (!listNavActive) {
                enterListNavigation();
                return;
            }
            const next = activeIdx < 0 ? 0 : activeIdx + delta;
            highlightOption(next, true);
        }

        function selectRow(row) {
            if (!row) return;
            setSelection(
                String(row.code || ''),
                String(row.label || row.name || row.code || ''),
                row
            );
            const advanceSel = (root.dataset.enterFocusNext || '').trim();
            if (advanceSel) {
                const scope = root.closest('tr') || root.closest('form') || document;
                const next = scope.querySelector(advanceSel);
                if (next) {
                    requestAnimationFrame(() => {
                        next.focus({ preventScroll: false });
                        if (typeof next.select === 'function' && next.type !== 'date' && !next.readOnly) {
                            try { next.select(); } catch (err) { /* readonly */ }
                        }
                    });
                    return;
                }
            }
            input.focus();
        }

        function selectActiveRow() {
            if (activeIdx < 0 || !lastRows[activeIdx]) return;
            selectRow(lastRows[activeIdx]);
        }

        function fetchRows(term) {
            const typed = (term || '').trim();
            if (typed.length < minChars) {
                closeDropdown();
                return;
            }
            if (abortCtrl) abortCtrl.abort();
            abortCtrl = new AbortController();
            let u = `${searchUrl}${searchUrl.includes('?') ? '&' : '?'}q=${encodeURIComponent(typed)}&limit=${limit}`;
            const extraFrom = (root.dataset.extraFrom || '').trim();
            if (extraFrom) {
                const src = document.querySelector(extraFrom);
                const param = (root.dataset.extraParam || 'parent_code').trim();
                const val = src ? (src.value || '').trim() : '';
                if (val) {
                    u += `&${encodeURIComponent(param)}=${encodeURIComponent(val)}`;
                }
            }
            dropdown.innerHTML = '<div class="global-lookup__empty odoo-lookup__empty">Loading…</div>';
            showDropdown();
            fetch(u, { credentials: 'same-origin', signal: abortCtrl.signal })
                .then((r) => {
                    if (!r.ok) {
                        return r.json().catch(() => ({})).then((data) => {
                            throw new Error((data && data.error) || `Search failed (${r.status})`);
                        });
                    }
                    return r.json();
                })
                .then((data) => {
                    if (!data || !data.success) throw new Error((data && data.error) || 'Search failed');
                    renderRows(data.rows || [], typed);
                })
                .catch((err) => {
                    if (err.name === 'AbortError') return;
                    dropdown.innerHTML = `<div class="global-lookup__empty odoo-lookup__empty--err">${esc(err.message || 'Search failed')}</div>`;
                    showDropdown();
                });
        }

        function scheduleSearch(term) {
            clearTimeout(timer);
            timer = setTimeout(() => fetchRows(term), debounceMs);
        }

        function trySearch() {
            const term = input.value.trim();
            if (term.length >= minChars) {
                scheduleSearch(term);
            } else {
                closeDropdown();
            }
        }

        input.addEventListener('input', () => {
            const term = input.value;
            setCodeValue('');
            resetListNav();
            syncTextSearchFallback(term);
            syncClear();
            if (term.trim().length < minChars) {
                closeDropdown();
                return;
            }
            scheduleSearch(term.trim());
        });

        input.addEventListener('focus', () => {
            trySearch();
        });

        input.addEventListener('keydown', (e) => {
            const opts = getOptions();
            if (e.key === 'ArrowDown') {
                if (!opts.length) {
                    trySearch();
                    return;
                }
                e.preventDefault();
                moveList(1);
            } else if (e.key === 'ArrowUp') {
                if (!opts.length) return;
                e.preventDefault();
                if (!listNavActive) {
                    enterListNavigation();
                    return;
                }
                moveList(-1);
            } else if (e.key === 'Enter') {
                if (opts.length) {
                    e.preventDefault();
                    if (!listNavActive) {
                        enterListNavigation();
                        return;
                    }
                    selectActiveRow();
                    return;
                }
                const advanceSel = (root.dataset.enterFocusNext || '').trim();
                if (advanceSel) {
                    e.preventDefault();
                    closeDropdown();
                    const scope = root.closest('tr') || root.closest('form') || document;
                    const next = scope.querySelector(advanceSel);
                    if (next) {
                        requestAnimationFrame(() => {
                            next.focus({ preventScroll: false });
                            if (typeof next.select === 'function' && next.type !== 'date' && !next.readOnly) {
                                try { next.select(); } catch (err) { /* readonly */ }
                            }
                        });
                    }
                    return;
                }
                if (textSearchEl && (input.value || '').trim()) {
                    e.preventDefault();
                    syncTextSearchFallback(input.value);
                    closeDropdown();
                    const form = root.closest('form');
                    if (form && typeof form.requestSubmit === 'function') {
                        form.requestSubmit();
                    } else if (form) {
                        form.submit();
                    }
                }
            } else if (e.key === 'Escape') {
                e.preventDefault();
                closeDropdown();
                input.focus();
            }
        });

        dropdown.addEventListener('keydown', (e) => {
            const opts = getOptions();
            if (!opts.length) return;
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                moveList(1);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                moveList(-1);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                selectActiveRow();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                closeDropdown();
                input.focus();
            } else if (e.key === 'Tab') {
                closeDropdown();
            }
        });

        dropdown.addEventListener('mousedown', (e) => {
            const btn = e.target.closest(SEL.option);
            if (!btn) return;
            e.preventDefault();
            const idx = parseInt(btn.dataset.idx || '-1', 10);
            selectRow(lastRows[idx]);
        });

        if (clearBtn) {
            clearBtn.addEventListener('click', (e) => {
                e.preventDefault();
                setSelection('', '');
                syncTextSearchFallback('');
                input.focus();
            });
        }

        const ph = (root.dataset.placeholder || '').trim();
        if (ph && !input.getAttribute('placeholder')) {
            input.setAttribute('placeholder', ph);
        }

        window.addEventListener('resize', () => {
            if (root.classList.contains('is-open')) positionDropdown();
        });
        window.addEventListener('scroll', () => {
            if (root.classList.contains('is-open')) positionDropdown();
        }, true);

        document.addEventListener('mousedown', (e) => {
            if (!root.contains(e.target) && !dropdown.contains(e.target)) closeDropdown();
        });

        syncClear();
        const skipDefault = root.dataset.noDefault === '1' || root.dataset.skipDefault === '1';
        const hiddenCode = codeValue();
        if (!skipDefault && hiddenCode && !(input.value || '').trim()) {
            input.value = hiddenCode;
        }
        if (skipDefault && (hiddenCode === '0' || !hiddenCode)) {
            setCodeValue('');
            input.value = '';
            syncTextSearchFallback('');
            syncClear();
        }
    }

    const LOOKUP_ROOT_SEL = '.global-lookup[data-search-url], .odoo-lookup[data-search-url]';

    function initAllOdooLookups(scope) {
        (scope || document).querySelectorAll(LOOKUP_ROOT_SEL).forEach(initOdooLookup);
    }

    global.initOdooLookup = initOdooLookup;
    global.initGlobalLookup = initOdooLookup;
    global.initAllOdooLookups = initAllOdooLookups;
    global.initAllGlobalLookups = initAllOdooLookups;
    global.GlobalLookup = {
        init: initOdooLookup,
        initAll: initAllOdooLookups,
        lookupUrl: (kind) => `/api/lookup/${encodeURIComponent(kind || 'customer')}`,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => initAllOdooLookups());
    } else {
        initAllOdooLookups();
    }
})(typeof window !== 'undefined' ? window : globalThis);
