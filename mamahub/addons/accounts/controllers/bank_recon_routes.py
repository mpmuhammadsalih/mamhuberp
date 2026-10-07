"""Bank reconciliation routes (registered on accounts blueprint)."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from nexa_http import jsonify, redirect, render_template, request, session, url_for

from addons.accounts.bank_recon_db import (
    delete_recon,
    ensure_bank_recon_tables,
    erp_line_key,
    get_bank_lines,
    get_matches,
    get_recon_header,
    list_recon_headers,
    next_recon_no,
    save_recon,
)
from db import get_account_ledger


def _loc_code() -> int:
    try:
        return int(session.get('location_code') or 1)
    except (TypeError, ValueError):
        return 1


def _build_erp_lines(account_code: str, date_from: str, date_to: str, matches: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    ledger = get_account_ledger(account_code, date_from, date_to)
    match_by_erp = {str(m.get('erp_key') or ''): m for m in matches or []}
    lines: List[Dict[str, Any]] = []
    receipts = 0.0
    payments = 0.0
    for idx, ln in enumerate(ledger.get('lines') or [], 1):
        dr = float(ln.get('debit') or 0)
        cr = float(ln.get('credit') or 0)
        receipts += dr
        payments += cr
        key = erp_line_key(ln.get('voucher_no'), ln.get('line_no') or idx)
        m = match_by_erp.get(key)
        lines.append({
            'erp_key': key,
            'line_no': int(ln.get('line_no') or idx),
            'txn_date': ln.get('voucher_date') or '',
            'reference_no': str(ln.get('reference_no') or ln.get('voucher_no') or ''),
            'description': str(ln.get('narration') or ln.get('remarks') or ''),
            'deposit': round(dr, 2),
            'payment': round(cr, 2),
            'balance': float(ln.get('running_balance') or 0),
            'voucher_no': str(ln.get('voucher_no') or ''),
            'matched': bool(m),
            'bank_line_no': int(m.get('bank_line_no') or 0) if m else 0,
            'match_type': str(m.get('match_type') or '') if m else '',
        })
    totals = {
        'opening': float(ledger.get('opening_balance') or 0),
        'receipts': round(receipts, 2),
        'payments': round(payments, 2),
        'closing': float(ledger.get('closing_balance') or 0),
    }
    return lines, totals


def _bank_totals_from_lines(bank_lines: List[Dict[str, Any]], opening: float = 0.0) -> Dict[str, float]:
    credits = sum(float(b.get('deposit') or 0) for b in bank_lines or [])
    debits = sum(float(b.get('payment') or 0) for b in bank_lines or [])
    closing = round(float(opening or 0) + credits - debits, 2)
    return {
        'opening': round(float(opening or 0), 2),
        'credits': round(credits, 2),
        'debits': round(debits, 2),
        'closing': closing,
    }


def _summary_from_state(erp_lines: List[Dict[str, Any]], bank_lines: List[Dict[str, Any]], matches: List[Dict[str, Any]]) -> Dict[str, float]:
    matched_amt = sum(float(m.get('match_amount') or 0) for m in matches or [])
    erp_unmatched = 0.0
    for e in erp_lines or []:
        if e.get('matched'):
            continue
        erp_unmatched += max(float(e.get('deposit') or 0), float(e.get('payment') or 0))
    bank_matched = {int(m.get('bank_line_no') or 0) for m in matches or []}
    bank_unmatched = 0.0
    for b in bank_lines or []:
        if int(b.get('line_no') or 0) in bank_matched:
            continue
        bank_unmatched += max(float(b.get('deposit') or 0), float(b.get('payment') or 0))
    return {
        'matched_amount': round(matched_amt, 2),
        'unmatched_erp': round(erp_unmatched, 2),
        'unmatched_bank': round(bank_unmatched, 2),
        'difference': round(erp_unmatched - bank_unmatched, 2),
    }


def _auto_match_pairs(erp_lines: List[Dict[str, Any]], bank_lines: List[Dict[str, Any]], existing: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    used_erp = {str(m.get('erp_key') or '') for m in existing or []}
    used_bank = {int(m.get('bank_line_no') or 0) for m in existing or []}
    out = list(existing or [])
    for e in erp_lines or []:
        if e.get('matched') or str(e.get('erp_key') or '') in used_erp:
            continue
        ed = (e.get('txn_date') or '')[:10]
        edr = float(e.get('deposit') or 0)
        ecr = float(e.get('payment') or 0)
        for b in bank_lines or []:
            bln = int(b.get('line_no') or 0)
            if bln in used_bank:
                continue
            bd = (b.get('txn_date') or '')[:10]
            if ed and bd and ed != bd:
                continue
            bdep = float(b.get('deposit') or 0)
            bpay = float(b.get('payment') or 0)
            if edr > 0.005 and abs(edr - bdep) < 0.02:
                amt = edr
            elif ecr > 0.005 and abs(ecr - bpay) < 0.02:
                amt = ecr
            else:
                continue
            out.append({
                'erp_key': str(e.get('erp_key') or ''),
                'bank_line_no': bln,
                'match_amount': round(amt, 2),
                'match_type': 'AUTO',
            })
            used_erp.add(str(e.get('erp_key') or ''))
            used_bank.add(bln)
            e['matched'] = True
            e['bank_line_no'] = bln
            e['match_type'] = 'AUTO'
            break
    return out


def register(bp) -> None:
    """Attach bank reconciliation routes to the accounts blueprint."""

    @bp.route('/accounts/bank-reconciliation')
    def bank_reconciliation():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        from addons.accounts.controllers.routes import _apply_db, _cached_cash_bank_accounts

        if not _apply_db():
            return redirect(url_for('dashboard.index'))
        ensure_bank_recon_tables()
        loc = _loc_code()
        recon_no = int(request.args.get('recon_no') or 0)
        bank_accounts = _cached_cash_bank_accounts()
        suggested_no = recon_no or next_recon_no(loc)
        return render_template(
            'accounts/bank_reconciliation.html',
            recon_no=recon_no,
            suggested_recon_no=suggested_no,
            bank_accounts=bank_accounts,
            location_code=loc,
        )

    @bp.route('/accounts/api/bank-reconciliation/list')
    def api_bank_recon_list():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        ensure_bank_recon_tables()
        rows = list_recon_headers(_loc_code())
        return jsonify({'success': True, 'rows': rows})

    @bp.route('/accounts/api/bank-reconciliation/load')
    def api_bank_recon_load():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        ensure_bank_recon_tables()
        loc = _loc_code()
        recon_no = int(request.args.get('recon_no') or 0)
        account = (request.args.get('bank_account_code') or '').strip()
        date_from = (request.args.get('date_from') or '')[:10]
        date_to = (request.args.get('date_to') or '')[:10]
        if not date_from:
            date_from = f'{datetime.now().year}-01-01'
        if not date_to:
            date_to = datetime.now().strftime('%Y-%m-%d')
        hdr = get_recon_header(recon_no, loc) if recon_no else None
        if hdr:
            account = hdr.get('bank_account_code') or account
            date_from = hdr.get('date_from') or date_from
            date_to = hdr.get('date_to') or date_to
        if not account:
            return jsonify({'success': False, 'error': 'Bank account is required'}, 400)
        matches = get_matches(recon_no, loc) if recon_no else []
        erp_lines, erp_totals = _build_erp_lines(account, date_from, date_to, matches)
        bank_lines = get_bank_lines(recon_no, loc) if recon_no else []
        bank_opening = float(hdr.get('bank_opening') or 0) if hdr else 0.0
        if not bank_lines and recon_no:
            bank_lines = []
        bank_totals = _bank_totals_from_lines(bank_lines, bank_opening)
        summary = _summary_from_state(erp_lines, bank_lines, matches)
        diff = round(float(erp_totals.get('closing', 0)) - float(bank_totals.get('closing', 0)), 2)
        return jsonify({
            'success': True,
            'header': hdr or {
                'recon_no': recon_no or next_recon_no(loc),
                'bank_account_code': account,
                'date_from': date_from,
                'date_to': date_to,
                'status': 'IN_PROGRESS',
            },
            'erp_lines': erp_lines,
            'bank_lines': bank_lines,
            'matches': matches,
            'erp_totals': erp_totals,
            'bank_totals': bank_totals,
            'summary': summary,
            'difference': diff,
        })

    @bp.route('/accounts/api/bank-reconciliation/save', methods=['POST'])
    def api_bank_recon_save():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        data = request.get_json(silent=True) or {}
        loc = _loc_code()
        recon_no = int(data.get('recon_no') or 0)
        if recon_no <= 0:
            recon_no = next_recon_no(loc)
        is_new = get_recon_header(recon_no, loc) is None
        user = str(session.get('user') or 'web')
        try:
            saved = save_recon(
                recon_no=recon_no,
                location_code=loc,
                bank_account_code=str(data.get('bank_account_code') or ''),
                date_from=str(data.get('date_from') or '')[:10],
                date_to=str(data.get('date_to') or '')[:10],
                description=str(data.get('description') or ''),
                erp_totals=data.get('erp_totals') or {},
                bank_totals=data.get('bank_totals') or {},
                status=str(data.get('status') or 'IN_PROGRESS'),
                notes=str(data.get('notes') or ''),
                bank_lines=data.get('bank_lines') or [],
                matches=data.get('matches') or [],
                user=user,
                is_new=is_new,
            )
        except Exception as ex:
            return jsonify({'success': False, 'error': str(ex)}, 400)
        return jsonify({'success': True, 'recon_no': saved})

    @bp.route('/accounts/api/bank-reconciliation/import-statement', methods=['POST'])
    def api_bank_recon_import():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        raw = request.get_data(as_text=True) or ''
        if not raw and request.files.get('file'):
            raw = request.files['file'].read().decode('utf-8', errors='replace')
        if not raw:
            return jsonify({'success': False, 'error': 'No CSV data'}, 400)
        reader = csv.DictReader(io.StringIO(raw))
        lines: List[Dict[str, Any]] = []
        ln = 0
        for row in reader:
            ln += 1
            def _pick(*keys):
                for k in keys:
                    for rk, rv in row.items():
                        if rk and rk.strip().lower() == k.lower():
                            return (rv or '').strip()
                return ''
            dep = _pick('deposit', 'credit', 'cr', 'credit amount')
            pay = _pick('payment', 'debit', 'dr', 'debit amount')
            try:
                dep_f = float(str(dep).replace(',', '') or 0)
            except ValueError:
                dep_f = 0.0
            try:
                pay_f = float(str(pay).replace(',', '') or 0)
            except ValueError:
                pay_f = 0.0
            d_raw = _pick('date', 'txn date', 'transaction date')
            td = d_raw[:10] if d_raw and len(d_raw) >= 10 else ''
            if td and '/' in td:
                try:
                    td = datetime.strptime(td[:10], '%d/%m/%Y').strftime('%Y-%m-%d')
                except ValueError:
                    pass
            lines.append({
                'line_no': ln,
                'txn_date': td,
                'reference_no': _pick('reference', 'ref', 'reference no')[:80],
                'description': _pick('description', 'narration', 'details')[:500],
                'deposit': round(dep_f, 2),
                'payment': round(pay_f, 2),
                'balance': 0,
            })
        run = 0.0
        for bl in lines:
            run = round(run + float(bl['deposit']) - float(bl['payment']), 2)
            bl['balance'] = run
        return jsonify({'success': True, 'bank_lines': lines, 'bank_totals': _bank_totals_from_lines(lines, 0)})

    @bp.route('/accounts/api/bank-reconciliation/auto-match', methods=['POST'])
    def api_bank_recon_auto_match():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        data = request.get_json(silent=True) or {}
        erp_lines = data.get('erp_lines') or []
        bank_lines = data.get('bank_lines') or []
        existing = data.get('matches') or []
        matches = _auto_match_pairs(erp_lines, bank_lines, existing)
        summary = _summary_from_state(erp_lines, bank_lines, matches)
        return jsonify({'success': True, 'matches': matches, 'erp_lines': erp_lines, 'summary': summary})

    @bp.route('/accounts/api/bank-reconciliation/match', methods=['POST'])
    def api_bank_recon_match():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        data = request.get_json(silent=True) or {}
        erp_key = str(data.get('erp_key') or '').strip()
        bank_line_no = int(data.get('bank_line_no') or 0)
        amount = float(data.get('match_amount') or 0)
        matches = list(data.get('matches') or [])
        if not erp_key or bank_line_no <= 0:
            return jsonify({'success': False, 'error': 'Select ERP and bank lines'}, 400)
        matches = [m for m in matches if str(m.get('erp_key') or '') != erp_key and int(m.get('bank_line_no') or 0) != bank_line_no]
        matches.append({'erp_key': erp_key, 'bank_line_no': bank_line_no, 'match_amount': amount, 'match_type': 'MANUAL'})
        erp_lines = data.get('erp_lines') or []
        bank_lines = data.get('bank_lines') or []
        match_erp = {erp_key}
        match_bank = {bank_line_no}
        for m in matches:
            match_erp.add(str(m.get('erp_key') or ''))
            match_bank.add(int(m.get('bank_line_no') or 0))
        for e in erp_lines:
            e['matched'] = str(e.get('erp_key') or '') in match_erp
            if e['matched']:
                for m in matches:
                    if str(m.get('erp_key') or '') == str(e.get('erp_key') or ''):
                        e['bank_line_no'] = int(m.get('bank_line_no') or 0)
                        e['match_type'] = str(m.get('match_type') or 'MANUAL')
        summary = _summary_from_state(erp_lines, bank_lines, matches)
        return jsonify({'success': True, 'matches': matches, 'erp_lines': erp_lines, 'summary': summary})

    @bp.route('/accounts/api/bank-reconciliation/unmatch', methods=['POST'])
    def api_bank_recon_unmatch():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        data = request.get_json(silent=True) or {}
        erp_key = str(data.get('erp_key') or '').strip()
        bank_line_no = int(data.get('bank_line_no') or 0)
        matches = list(data.get('matches') or [])
        if erp_key:
            matches = [m for m in matches if str(m.get('erp_key') or '') != erp_key]
        elif bank_line_no > 0:
            matches = [m for m in matches if int(m.get('bank_line_no') or 0) != bank_line_no]
        erp_lines = data.get('erp_lines') or []
        bank_lines = data.get('bank_lines') or []
        match_erp = {str(m.get('erp_key') or '') for m in matches}
        for e in erp_lines:
            e['matched'] = str(e.get('erp_key') or '') in match_erp
            if not e['matched']:
                e['bank_line_no'] = 0
                e['match_type'] = ''
        summary = _summary_from_state(erp_lines, bank_lines, matches)
        return jsonify({'success': True, 'matches': matches, 'erp_lines': erp_lines, 'summary': summary})

    @bp.route('/accounts/api/bank-reconciliation/delete', methods=['POST'])
    def api_bank_recon_delete():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        data = request.get_json(silent=True) or {}
        recon_no = int(data.get('recon_no') or 0)
        if recon_no <= 0:
            return jsonify({'success': False, 'error': 'Nothing to delete'}, 400)
        delete_recon(recon_no, _loc_code())
        return jsonify({'success': True})
