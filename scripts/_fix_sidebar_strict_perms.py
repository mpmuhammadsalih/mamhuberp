"""One-off: remove cross-menu OR guards in base.html sidebar (strict role permissions)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "templates" / "base.html"
text = path.read_text(encoding="utf-8")

replacements = [
    (
        "{% if allow_all_permissions or has_menu_permission('system_config.system_config_list') or has_menu_permission('setup.company_profile') %}\n                  <a href=\"{{ url_for('company_profile.company_list') }}\"",
        "{% if has_menu_permission('setup.company_profile') or allow_all_permissions %}\n                  <a href=\"{{ url_for('company_profile.company_list') }}\"",
    ),
    (
        "{% if allow_all_permissions or has_menu_permission('system_config.system_config_list') or has_menu_permission('setup.menu_price_points') or has_menu_permission('setup.company_profile') %}\n                  <a href=\"{{ url_for('menu_price_setup.menu_price_points_page') }}\"",
        "{% if has_menu_permission('setup.menu_price_points') or allow_all_permissions %}\n                  <a href=\"{{ url_for('menu_price_setup.menu_price_points_page') }}\"",
    ),
    (
        "{% if has_menu_permission('setup.new_company_setup') or has_menu_permission('utilities.db_structure_sync') or session.get('user','').strip().lower() in ('admin','super') %}",
        "{% if has_menu_permission('setup.new_company_setup') or has_menu_permission('utilities.db_structure_sync') or allow_all_permissions %}",
    ),
    (
        "                <a href=\"{{ url_for('tasveek.tasveek_api_rawabi_data') }}\" data-icon=\"TW\">Tasveek API data</a>",
        "                {% if has_menu_permission('tasveek.tasveek_api_rawabi_data') or allow_all_permissions %}\n                <a href=\"{{ url_for('tasveek.tasveek_api_rawabi_data') }}\" data-icon=\"TW\">Tasveek API data</a>\n                {% endif %}",
    ),
    (
        "{% if has_menu_permission('customer.missing_customer_recovery') or has_menu_permission('customer.missing_customer_visit_tasks') %}\n                  <a href=\"{{ url_for('customer.missing_customer_recovery_tasks') }}\"",
        "{% if has_menu_permission('customer.missing_customer_visit_tasks') or allow_all_permissions %}\n                  <a href=\"{{ url_for('customer.missing_customer_recovery_tasks') }}\"",
    ),
    (
        "{% if has_menu_permission('sales.sales_order') or has_menu_permission('sales.sales_order_list') or allow_all_permissions %}",
        "{% if has_menu_permission('sales.sales_order_list') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('purchase.purchase_order_new') or has_menu_permission('purchase.purchase_order_list') or allow_all_permissions %}",
        "{% if has_menu_permission('purchase.purchase_order_list') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('purchase.purchase_return_list') or has_menu_permission('purchase.purchase_return_order') or has_menu_permission('purchase.purchase_return_request_list') or allow_all_permissions %}",
        "{% if has_menu_permission('purchase.purchase_return_list') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('purchase.stock_adjustment') or has_menu_permission('purchase.stock_adjustment_list') or allow_all_permissions %}",
        "{% if has_menu_permission('purchase.stock_adjustment_list') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('purchase.repacking') or has_menu_permission('purchase.repacking_list') or allow_all_permissions %}",
        "{% if has_menu_permission('purchase.repacking_list') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('purchase.batch_lot_operator_checklist') or has_menu_permission('purchase.batch_lot_inquiry') or allow_all_permissions %}",
        "{% if has_menu_permission('purchase.batch_lot_operator_checklist') or allow_all_permissions %}",
    ),
    (
                "<a href=\"{{ url_for('accounts.chart_of_accounts_list') }}\" data-icon=\"CA\">Chart of Accounts</a>",
                "{% if has_menu_permission('accounts.chart_of_accounts_list') or allow_all_permissions %}\n                <a href=\"{{ url_for('accounts.chart_of_accounts_list') }}\" data-icon=\"CA\">Chart of Accounts</a>\n                {% endif %}",
    ),
    (
        "{% if has_menu_permission('accounts.account_ledger_page') or has_menu_permission('accounts.chart_of_accounts_list') or allow_all_permissions %}",
        "{% if has_menu_permission('accounts.account_ledger_page') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('accounts.main_account_ledger') or has_menu_permission('accounts.account_ledger_page') or allow_all_permissions %}",
        "{% if has_menu_permission('accounts.main_account_ledger') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('accounts.supplier_ledger_page') or has_menu_permission('accounts.account_ledger_page') or has_menu_permission('accounts.chart_of_accounts_list') or allow_all_permissions %}",
        "{% if has_menu_permission('accounts.supplier_ledger_page') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('accounts.customer_ledger_page') or has_menu_permission('accounts.account_ledger_page') or has_menu_permission('accounts.chart_of_accounts_list') or allow_all_permissions %}",
        "{% if has_menu_permission('accounts.customer_ledger_page') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('accounts.cash_payment_voucher') or has_menu_permission('accounts.journal_entry') or allow_all_permissions %}",
        "{% if has_menu_permission('accounts.cash_payment_voucher') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('accounts.transaction_audit') or has_menu_permission('accounts.journal_entry') or allow_all_permissions %}",
        "{% if has_menu_permission('accounts.transaction_audit') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('accounts.opening_balance_import') or has_menu_permission('accounts.journal_entry') or allow_all_permissions %}",
        "{% if has_menu_permission('accounts.opening_balance_import') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('accounts.customer_opening_outstanding') or has_menu_permission('accounts.journal_entry') or allow_all_permissions %}",
        "{% if has_menu_permission('accounts.customer_opening_outstanding') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('accounts.supplier_opening_outstanding') or has_menu_permission('accounts.journal_entry') or allow_all_permissions %}",
        "{% if has_menu_permission('accounts.supplier_opening_outstanding') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('purchase.purchase_return_posting') or has_menu_permission('purchase.purchase_return_list') or allow_all_permissions %}",
        "{% if has_menu_permission('purchase.purchase_return_posting') or allow_all_permissions %}",
    ),
    (
        "{% if has_menu_permission('reports.customer_outstanding_cr') or has_menu_permission('reports.customer_outstanding_cr_month') %}\n                  <a href=\"{{ url_for('reports.customer_outstanding_cr_month') }}\"",
        "{% if has_menu_permission('reports.customer_outstanding_cr_month') or allow_all_permissions %}\n                  <a href=\"{{ url_for('reports.customer_outstanding_cr_month') }}\"",
    ),
]

for old, new in replacements:
    if old not in text:
        print("MISSING:", old[:80].replace("\n", " "))
    else:
        text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Done.")
