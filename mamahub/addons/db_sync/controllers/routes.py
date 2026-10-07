"""Oracle new-company / empty-schema data clearance (Setup)."""
from pathlib import Path
from nexa_http import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from save_nonce import clear_ephemeral_session_state
from addons.db_sync.services.data_wipe import (
    new_company_default_extra_protected_names,
    new_company_default_protected_display_csv,
    run_clear_target_data,
    run_reset_sequences_and_document_counters,
)
_ADDON = Path(__file__).resolve().parents[1]
bp = Blueprint('db_sync', __name__, url_prefix='', template_folder=str(_ADDON / 'views' / 'templates'))

def _allowed() -> bool:
    u = (session.get('user') or '').strip().lower()
    if u in ('admin', 'super'):
        return True
    try:
        from permissions import get_role_permissions
        from db import get_user_role_id
        rid = get_user_role_id(session.get('user'))
        if not rid:
            return False
        perms = get_role_permissions(rid) or []
        return 'setup.new_company_setup' in perms or 'utilities.db_structure_sync' in perms
    except Exception:
        return False

def _parse_extra_protected(raw: str) -> list[str]:
    out: list[str] = []
    for part in (raw or '').replace('\n', ',').split(','):
        p = part.strip().upper()
        if p:
            out.append(p)
    return out


def _resolved_extra_protected(raw: str) -> list[str]:
    """Form skip list; empty field uses built-in new-company master defaults."""
    parsed = _parse_extra_protected(raw)
    return parsed if parsed else new_company_default_extra_protected_names()


def _default_wipe_extra_protected_field() -> str:
    return new_company_default_protected_display_csv()


CONSTRAINT_OUTPUT_MAX_LINES = 700
FK_EXECUTE_PHRASE = 'APPLY HEURISTIC FKS'

def _truncate_lines(lines: list[str], max_lines: int=CONSTRAINT_OUTPUT_MAX_LINES) -> str:
    if len(lines) <= max_lines:
        return '\n'.join(lines)
    head = lines[:max_lines]
    return '\n'.join(head) + '\n\n… %s more lines omitted (open terminal + script for full output).' % (len(lines) - max_lines)

def _format_wipe_result(r: dict) -> str:
    lines: list[str] = []
    lines.append('ok=%s dry_run=%s truncated=%s' % (r.get('ok'), r.get('dry_run'), r.get('truncated_count')))
    msgs = r.get('messages') or []
    if msgs:
        lines.append('--- summary ---')
        lines.extend(msgs[:80])
    counter = r.get('counter_reset') or {}
    if counter:
        lines.append('--- sequences / document counters ---')
        lines.append('ok=%s dry_run=%s sequences=%s counter_tables=%s' % (
            counter.get('ok'), counter.get('dry_run'),
            counter.get('sequences_reset'), counter.get('counter_tables_cleared'),
        ))
        for m in (counter.get('messages') or [])[:40]:
            lines.append(m)
        for e in (counter.get('errors') or [])[:40]:
            lines.append('ERROR: ' + e)
    errs = r.get('errors') or []
    if errs:
        lines.append('--- errors ---')
        lines.extend(errs[:80])
    return '\n'.join(lines)

def _render_page(*, wipe_summary=None, wipe_sql=None, constraint_report=None, constraint_sql_hints=None, wipe_phrase_value='', fk_phrase_value='', wipe_extra_protected=None, fk_max_fks=800, target_user='', target_dsn='', session_cleared=False, session_clear_summary=''):
    return render_template(
        'new_company_setup.html',
        title='New Company setup | Nexus Erp',
        wipe_summary=wipe_summary,
        wipe_sql=wipe_sql,
        constraint_report=constraint_report,
        constraint_sql_hints=constraint_sql_hints,
        wipe_phrase_value=wipe_phrase_value,
        fk_phrase_value=fk_phrase_value,
        wipe_extra_protected=wipe_extra_protected if wipe_extra_protected is not None else _default_wipe_extra_protected_field(),
        fk_max_fks=fk_max_fks,
        target_user=target_user,
        target_dsn=target_dsn,
        session_cleared=session_cleared,
        session_clear_summary=session_clear_summary,
    )

@bp.route('/setup/new-company-setup', methods=('GET', 'POST'))
@bp.route('/utilities/db-structure-sync', methods=('GET', 'POST'))
def new_company_setup_page():
    """Primary URL: ``/setup/new-company-setup``. Legacy: ``/utilities/db-structure-sync``."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        tu = (request.form.get('target_user') or '').strip()
        tp = request.form.get('target_password') or ''
        td = (request.form.get('target_dsn') or '').strip()
        wipe_phrase_val = request.form.get('wipe_phrase') or ''
        wipe_extra_raw = request.form.get('wipe_extra_protected') or ''
        extra_prot = _resolved_extra_protected(wipe_extra_raw)
        if action not in ('clear_preview', 'clear_execute', 'clear_session_only', 'reset_counters_only', 'constraints_audit', 'constraints_fk_preview', 'constraints_fk_execute'):
            flash('Unknown action.', 'error')
            return redirect(url_for('db_sync.new_company_setup_page'))
        if action == 'clear_session_only':
            n_cleared, _keys = clear_ephemeral_session_state()
            flash(
                'Browser session state cleared (%s item(s): save tokens, locks, POS counter, form tokens). '
                'Refresh or re-open GRN / Sales / POS tabs before saving. Other logged-in users should log out and back in.'
                % n_cleared,
                'success',
            )
            return _render_page(session_cleared=True, session_clear_summary=str(n_cleared))
        if action == 'reset_counters_only':
            if not tu or not tp or (not td):
                flash('Target user, password, and DSN are required.', 'error')
                return _render_page(target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw)
            try:
                counter_res = run_reset_sequences_and_document_counters(tu, tp, td, dry_run=False)
            except Exception as ex:
                flash(f'Reset sequences/counters: {ex}', 'error')
                return _render_page(target_user=tu, target_dsn=td, wipe_summary=str(ex), wipe_extra_protected=wipe_extra_raw)
            sql_chunk = '\n'.join(counter_res.get('script_lines') or [])
            if counter_res.get('ok'):
                flash(
                    'Sequences and document counters reset (%s sequence(s), %s counter table(s) cleared).'
                    % (counter_res.get('sequences_reset', 0), len(counter_res.get('counter_tables_cleared') or [])),
                    'success',
                )
            else:
                flash((counter_res.get('errors') or ['Reset stopped with errors.'])[0], 'error')
            return _render_page(
                wipe_summary=_format_wipe_result({'ok': counter_res.get('ok'), 'counter_reset': counter_res, 'messages': []}),
                wipe_sql=sql_chunk,
                target_user=tu,
                target_dsn=td,
                wipe_extra_protected=wipe_extra_raw,
            )
        preserve_auth = (request.form.get('wipe_preserve_auth') or '').strip() == 'on'
        fk_phrase_raw = request.form.get('fk_phrase') or ''
        try:
            fk_max = int((request.form.get('fk_max_fks') or '800').strip() or '800')
        except ValueError:
            fk_max = 800
        fk_max = max(1, min(fk_max, 5000))
        if not tu or not tp or (not td):
            flash('Target user, password, and DSN are required.', 'error')
            return _render_page(target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, wipe_phrase_value=wipe_phrase_val, fk_phrase_value=fk_phrase_raw, fk_max_fks=fk_max)
        if action in ('constraints_audit', 'constraints_fk_preview', 'constraints_fk_execute'):
            fk_novalidate = (request.form.get('fk_novalidate_orphans') or '').strip() == 'on'
            if action == 'constraints_audit':
                try:
                    from scripts.oracle_constraint_audit import run_audit_for_connection
                except ImportError as ie:
                    flash(f'Constraint audit requires scripts module: {ie}', 'error')
                    return _render_page(target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, fk_phrase_value=fk_phrase_raw, fk_max_fks=fk_max)
                try:
                    hint_cap = min(fk_max, 800)
                    report_lines, sql_lines = run_audit_for_connection(tu, tp, td, suggest_fk=True, max_fk_hints=hint_cap, include_sql_chunks=True)
                    flash('Constraint audit finished (read output below).', 'success')
                    return _render_page(constraint_report=_truncate_lines(report_lines), constraint_sql_hints=_truncate_lines(sql_lines), target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, fk_max_fks=fk_max)
                except Exception as ex:
                    flash(f'Constraint audit failed: {ex}', 'error')
                    return _render_page(constraint_report=str(ex), target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, fk_max_fks=fk_max)
            if action in ('constraints_fk_preview', 'constraints_fk_execute'):
                try:
                    from scripts.oracle_apply_constraints import run_apply_for_connection
                except ImportError as ie:
                    flash(f'Heuristic FK tools require scripts module: {ie}', 'error')
                    return _render_page(target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, fk_phrase_value=fk_phrase_raw, fk_max_fks=fk_max)
            if action == 'constraints_fk_preview':
                try:
                    stats, lines = run_apply_for_connection(tu, tp, td, execute=False, i_confirm=False, novalidate_orphans=fk_novalidate, max_fks=fk_max)
                    summary = 'Preview (no DDL executed).\n%s\n\n' % stats + _truncate_lines(lines)
                    flash('FK preview generated (DDL not executed). Review carefully — heuristic has false positives.', 'success')
                    return _render_page(constraint_report=summary, target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, fk_max_fks=fk_max)
                except Exception as ex:
                    flash(f'FK preview failed: {ex}', 'error')
                    return _render_page(constraint_report=str(ex), target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, fk_max_fks=fk_max)
            if action == 'constraints_fk_execute':
                if (request.form.get('confirm_fk_execute') or '').strip() != 'on':
                    flash('Check the confirmation box before applying heuristic FK constraints on the target.', 'error')
                    return _render_page(target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, fk_phrase_value=fk_phrase_raw, fk_max_fks=fk_max)
                phrase = fk_phrase_raw.strip().upper()
                if phrase != FK_EXECUTE_PHRASE:
                    flash(f'Type exactly {FK_EXECUTE_PHRASE!r} in the FK phrase field, then submit again.', 'error')
                    return _render_page(target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, fk_phrase_value=fk_phrase_raw, fk_max_fks=fk_max)
                try:
                    stats, lines = run_apply_for_connection(tu, tp, td, execute=True, i_confirm=True, novalidate_orphans=fk_novalidate, max_fks=fk_max)
                    summary = 'Execute finished.\n%s\n\n' % stats + _truncate_lines(lines)
                    errs = stats.get('errors') or 0
                    flash('Heuristic FK apply finished.' + (' Some statements failed — see output.' if errs else ''), 'error' if errs else 'success')
                    return _render_page(constraint_report=summary, target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, fk_phrase_value='', fk_max_fks=fk_max)
                except Exception as ex:
                    flash(f'FK apply failed: {ex}', 'error')
                    return _render_page(constraint_report=str(ex), target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, fk_max_fks=fk_max)
            return redirect(url_for('db_sync.new_company_setup_page'))
        if action == 'clear_execute':
            if (request.form.get('confirm_wipe_execute') or '').strip() != 'on':
                flash('Check the confirmation box before executing a data wipe on the target.', 'error')
                return _render_page(target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, wipe_phrase_value=wipe_phrase_val)
            phrase = wipe_phrase_val.strip().upper()
            if phrase != 'CLEAR ALL DATA':
                flash('Type exactly CLEAR ALL DATA in the phrase field (then submit again).', 'error')
                return _render_page(target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, wipe_phrase_value=wipe_phrase_val)
        dry_wipe = action == 'clear_preview'
        reset_counters = (request.form.get('reset_sequences_counters') or '').strip() == 'on'
        try:
            res = run_clear_target_data(tu, tp, td, preserve_auth_tables=preserve_auth, dry_run=dry_wipe, extra_protected=extra_prot)
        except Exception as ex:
            flash(f'Clear data: {ex}', 'error')
            return _render_page(target_user=tu, target_dsn=td, wipe_summary=str(ex), wipe_extra_protected=wipe_extra_raw, wipe_phrase_value=wipe_phrase_val)
        counter_res = None
        if reset_counters and (dry_wipe or res.get('ok')):
            try:
                counter_res = run_reset_sequences_and_document_counters(tu, tp, td, dry_run=dry_wipe)
            except Exception as ex:
                counter_res = {'ok': False, 'dry_run': dry_wipe, 'errors': [str(ex)], 'messages': [], 'script_lines': [], 'sequences_reset': 0, 'counter_tables_cleared': []}
            res['counter_reset'] = counter_res
            if not counter_res.get('ok'):
                res['ok'] = False
                res.setdefault('errors', []).extend(counter_res.get('errors') or [])
        sql_chunk = '\n'.join(res.get('script_lines') or [])
        if counter_res and counter_res.get('script_lines'):
            sql_chunk = sql_chunk + ('\n\n' if sql_chunk else '') + '\n'.join(counter_res.get('script_lines') or [])
        session_cleared = False
        session_clear_summary = ''
        if res.get('ok') and (not dry_wipe) and (request.form.get('clear_session_state') or '').strip() == 'on':
            n_cleared, _keys = clear_ephemeral_session_state()
            session_cleared = True
            session_clear_summary = str(n_cleared)
        if res.get('ok'):
            if dry_wipe:
                flash('SQL preview generated (no changes).', 'success')
            else:
                extra = ''
                if session_cleared:
                    extra = ' Session state cleared (%s browser session keys + fresh save tokens).' % session_clear_summary
                counter_extra = ''
                if counter_res and counter_res.get('ok'):
                    counter_extra = ' Sequences/counters reset (%s seq, %s counter table(s)).' % (
                        counter_res.get('sequences_reset', 0),
                        len(counter_res.get('counter_tables_cleared') or []),
                    )
                flash('Target business tables truncated.' + extra + counter_extra, 'success')
        else:
            flash((res.get('errors') or ['Clear data stopped with errors.'])[0], 'error')
        return _render_page(wipe_summary=_format_wipe_result(res), wipe_sql=sql_chunk, target_user=tu, target_dsn=td, wipe_extra_protected=wipe_extra_raw, wipe_phrase_value='', session_cleared=session_cleared, session_clear_summary=session_clear_summary)
    return _render_page()
