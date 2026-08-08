from typing import Dict, List, Set, Tuple, Optional

_POS_SETTLEMENT_POSTING_ENDPOINTS: List[str] = [
    'pos_billing.pos_settlement_posting_page',
    'pos_billing.pos_settlement_posting_workflow_page',
    'pos_billing.pos_settlement_posting_pdf',
    'pos_billing.pos_settlement_posting_api_bills',
    'pos_billing.pos_settlement_posting_api_counters',
    'pos_billing.pos_settlement_posting_api_coa',
    'pos_billing.pos_settlement_posting_api_tender_defaults',
    'pos_billing.pos_settlement_posting_api_payment_mode_summary',
    'pos_billing.pos_settlement_posting_api_drafts',
    'pos_billing.pos_settlement_posting_api_draft_generate',
    'pos_billing.pos_settlement_posting_api_draft_mutation',
    'pos_billing.pos_settlement_posting_api_settlement_reverse_gl',
    'pos_billing.pos_settlement_posting_api_update_status',
    'pos_billing.pos_validate_pos_date_closed_api',
]

MENU_GROUPS: List[Dict[str, object]] = [{'title': 'Dashboard',
  'items': [{'label': 'Dashboard',
             'menu_path': 'dashboard.dashboard',
             'endpoints': ['dashboard.index', 'dashboard.dashboard', 'dashboard.switch_dbkey']}]},
 {'title': 'Setup',
  'items': [{'label': 'User Management',
             'menu_path': 'users.user_create',
             'endpoints': ['users.user_list', 'users.user_create', 'users.user_edit_role', 'users.check_username']},
            {'label': 'Transfer Approval Setup',
             'menu_path': 'purchase.stock_transfer_approval_setup',
             'endpoints': ['purchase.stock_transfer_approval_setup',
                           'purchase.stock_transfer_approval_setup_init',
                           'purchase.stock_transfer_approval_setup_load',
                           'purchase.stock_transfer_approval_setup_save'],
             'blueprints': ['purchase']},
            {'label': 'Tenants',
             'menu_path': 'tenants.tenant_list',
             'endpoints': ['tenants.tenant_list', 'tenants.tenant_create', 'tenants.tenant_edit'],
             'blueprints': ['tenants']},
            {'label': 'Roles & Permissions',
             'menu_path': 'roles.roles_list',
             'endpoints': ['roles.roles_list', 'roles.roles_create', 'roles.roles_edit', 'roles.roles_delete']},
            {'label': 'System Configuration',
             'menu_path': 'system_config.system_config_list',
             'endpoints': ['system_config.system_config_list',
                           'system_config.system_config',
                           'system_config.delete_system_config',
                           'company_profile.company_profile_page',
                           'company_profile.company_list',
                           'company_profile.company_profile_new',
                           'company_profile.company_profile_edit',
                           'menu_price_setup.menu_price_points_page']},
            {'label': 'Company profile',
             'menu_path': 'setup.company_profile',
             'endpoints': ['company_profile.company_profile_page',
                           'company_profile.company_list',
                           'company_profile.company_profile_new',
                           'company_profile.company_profile_edit'],
             'blueprints': ['company_profile']},
            {'label': 'Menu price & points',
             'menu_path': 'setup.menu_price_points',
             'endpoints': ['menu_price_setup.menu_price_points_page'],
             'blueprints': ['menu_price_setup']},
            {'label': 'Branch / Location Master',
             'menu_path': 'setup.branch_location_master',
             'endpoints': ['branch_location.branch_location_master',
                           'branch_location.branch_location_new',
                           'branch_location.branch_location_edit'],
             'blueprints': ['branch_location']},
            {'label': 'GL dimension master',
             'menu_path': 'setup.gl_dimension_master',
             'endpoints': ['gl_dimension.gl_dimension_list',
                           'gl_dimension.gl_dimension_new',
                           'gl_dimension.gl_dimension_edit',
                           'gl_dimension.gl_dimension_delete'],
             'blueprints': ['gl_dimension']},
            {'label': 'Fiscal Year Setup',
             'menu_path': 'setup.fiscal_year',
             'endpoints': ['fiscal_year.fiscal_year_list',
                           'fiscal_year.fiscal_year_new',
                           'fiscal_year.fiscal_year_edit',
                           'fiscal_year.fiscal_year_set_current',
                           'fiscal_year.fiscal_year_delete'],
             'blueprints': ['fiscal_year']},
            {'label': 'Document Numbering',
             'menu_path': 'setup.document_numbering',
             'endpoints': ['document_numbering.document_numbering_page'],
             'blueprints': ['document_numbering']},
            {'label': 'Transaction Date Setup',
             'menu_path': 'setup.transaction_date_setup',
             'endpoints': ['transaction_date_setup.transaction_date_setup_page',
                           'transaction_date_setup.transaction_date_api_bootstrap',
                           'transaction_date_setup.transaction_date_api_save',
                           'transaction_date_setup.transaction_date_api_close'],
             'blueprints': ['transaction_date_setup']},
            # Capability flag only — checked by transaction_date_setup._is_txn_date_admin().
            # Does not grant page access; pair with setup.transaction_date_setup.
            {'label': 'Transaction Date — change any date (like admin)',
             'menu_path': 'setup.transaction_date_change_any',
             'endpoints': [],
             'blueprints': []},
            {'label': 'Promotions',
             'menu_path': 'promotions.promotions_page',
             'endpoints': ['promotions.promotions_page'],
             'blueprints': ['promotions']},
            {'label': 'New Company setup',
             'menu_path': 'setup.new_company_setup',
             'endpoints': ['db_sync.new_company_setup_page'],
             'blueprints': ['db_sync']},
            {'label': 'Approval Workflow',
             'menu_path': 'setup.approval_workflow_page',
             'endpoints': [
                 'approval_workflow.approval_workflow_page',
                 'approval_workflow.approval_workflow_api_dashboard',
                 'approval_workflow.approval_workflow_api_save',
                 'approval_workflow.approval_workflow_api_delete',
                 'approval_workflow.approval_workflow_api_queue_action',
             ],
             'blueprints': ['approval_workflow']},
            {'label': 'General Setup',
             'menu_path': 'setup.general_setup_page',
             'endpoints': ['general_setup.general_setup_page'],
             'blueprints': ['general_setup']},
            {'label': 'DB Structure Sync',
             'menu_path': 'utilities.db_structure_sync',
             'endpoints': ['db_sync.new_company_setup_page'],
             'blueprints': ['db_sync']},
            {'label': 'DBA — Table Locks',
             'menu_path': 'setup.dba_tools',
             'endpoints': ['dba_tools.dba_page',
                           'dba_tools.dba_api_tables',
                           'dba_tools.dba_api_unlock'],
             'blueprints': ['dba_tools']}]},
 {'title': 'PDT',
  'items': [{'label': 'PDT Roles Setup',
             'menu_path': 'pdt.pdt_roles_list',
             'endpoints': ['pdt.pdt_roles_list',
                           'pdt.pdt_roles_create',
                           'pdt.pdt_roles_edit',
                           'pdt.pdt_roles_delete'],
             'blueprints': ['pdt']},
            {'label': 'PDT User Creation',
             'menu_path': 'pdt.pdt_user_create',
             'endpoints': ['pdt.pdt_user_create', 'pdt.check_username', 'pdt.pdt_users_list'],
             'blueprints': ['pdt']},
            {'label': 'PDT Users',
             'menu_path': 'pdt.pdt_users_list',
             'endpoints': ['pdt.pdt_users_list'],
             'blueprints': ['pdt']}]},
 {'title': 'Online',
  'items': [{'label': 'Tasveek',
             'menu_path': 'tasveek.tasveek_list',
             'endpoints': ['tasveek.tasveek_list',
                           'tasveek.tasveek_import',
                           'tasveek.tasveek_export_xlsx',
                           'tasveek.tasveek_template',
                           'tasveek.tasveek_rfsr_toggle',
                           'tasveek.tasveek_delete_row',
                           'tasveek.tasveek_api_rawabi_data',
                           'tasveek.tasveek_api_rawabi_export_xlsx'],
             'blueprints': ['tasveek']},
            {'label': 'Tasveek API data',
             'menu_path': 'tasveek.tasveek_api_rawabi_data',
             'endpoints': ['tasveek.tasveek_api_rawabi_data', 'tasveek.tasveek_api_rawabi_export_xlsx']}]},
 {'title': 'Collaboration',
  'items': [{'label': 'Chat',
             'menu_path': 'chat.chat_page',
             'endpoints': ['chat.chat_page',
                           'chat.chat_api_users',
                           'chat.chat_api_conversations',
                           'chat.chat_api_conversation_direct',
                           'chat.chat_api_conversation_group',
                           'chat.chat_api_messages_list',
                           'chat.chat_api_message_send',
                           'chat.chat_api_message_edit',
                           'chat.chat_api_message_delete',
                           'chat.chat_api_message_react',
                           'chat.chat_api_message_share',
                           'chat.chat_api_typing_set',
                           'chat.chat_api_typing_get',
                           'chat.chat_api_stream'],
             'blueprints': ['chat']}]},
 {'title': 'Master',
  'items': [            {'label': 'Customer',
             'menu_path': 'customer.customer_list',
             'endpoints': ['customer.customer_list',
                           'customer.customer_list_api_items',
                           'customer.customer_list_api_filter_options',
                           'customer.customer_create',
                           'customer.customer_edit',
                           'customer.customer_view',
                           'customer.customer_delete',
                           'customer.customer_export',
                           'customer.api_salesman_list',
                           'customer.api_category_list',
                           'customer.api_route_list',
                           'customer.api_employee_list',
                           'activity_log.activity_log_page']},
            {'label': 'Salesman',
             'menu_path': 'salesman.salesman_list',
             'endpoints': ['salesman.salesman_list',
                           'salesman.salesman_create',
                           'salesman.salesman_edit',
                           'salesman.salesman_delete',
                           'activity_log.activity_log_page']},
            {'label': 'Route',
             'menu_path': 'route_master.route_list',
             'endpoints': ['route_master.route_list',
                           'route_master.route_create',
                           'route_master.route_edit',
                           'route_master.route_delete',
                           'activity_log.activity_log_page']},
            {'label': 'Customer category',
             'menu_path': 'customer_category.category_list',
             'endpoints': ['customer_category.category_list',
                           'customer_category.category_create',
                           'customer_category.category_edit',
                           'customer_category.category_delete',
                           'activity_log.activity_log_page']},
            {'label': 'Session',
             'menu_path': 'session_master.session_list',
             'endpoints': ['session_master.session_list',
                           'session_master.session_create',
                           'session_master.session_edit',
                           'session_master.session_delete',
                           'activity_log.activity_log_page']},
            {'label': 'Employee',
             'menu_path': 'employee.employee_list',
             'endpoints': ['employee.employee_list',
                           'employee.employee_create',
                           'employee.employee_view',
                           'employee.employee_edit',
                           'employee.employee_export',
                           'activity_log.activity_log_page']},
            {'label': 'Supplier',
             'menu_path': 'supplier.supplier_list',
             'endpoints': ['supplier.supplier_list',
                           'supplier.supplier_create',
                           'supplier.supplier_edit',
                           'activity_log.activity_log_page']}]},
 {'title': 'Plan',
  'items': [{'label': 'Missing customer recovery',
             'menu_path': 'customer.missing_customer_recovery',
             'endpoints': ['customer.missing_customer_recovery',
                           'customer.missing_customer_recovery_assign',
                           'customer.missing_customer_recovery_tasks',
                           'customer.missing_customer_recovery_case_update']},
            {'label': 'My visit tasks',
             'menu_path': 'customer.missing_customer_visit_tasks',
             'endpoints': ['customer.missing_customer_recovery_tasks',
                           'customer.missing_customer_recovery_case_update']}]},
 {'title': 'Sales',
  'items': [{'label': 'Sales Invoice',
             'menu_path': 'sales.sales_invoice',
             'endpoints': ['sales.sales_invoice',
                           'sales.sales_invoice_list',
                           'sales.sales_invoice_export',
                           'sales.sales_invoice_summary_pdf',
                           'sales.sales_customers_picker',
                           'sales.sales_next_billno',
                           'sales.sales_item_info',
                           'sales.sales_uom_info',
                           'sales.sales_item_uoms',
                           'sales.sales_item_inventory',
                           'sales.sales_invoice_type',
                           'sales.sales_item_popup_items',
                           'sales.sales_item_history',
                           'sales.sales_api_batch_lots_for_line',
                           'sales.sales_save',
                           'sales.sales_load_from_order',
                           'reports.crystal_reports_open_report'],
             'blueprints': ['sales']},
            {'label': 'Sales Order',
             'menu_path': 'sales.sales_order_list',
             'endpoints': ['sales.sales_order',
                           'sales.sales_order_list',
                           'sales.sales_order_export',
                           'sales.sales_order_next_billno',
                           'sales.sales_order_api_batch_lots_for_line',
                           'sales.sales_order_save',
                           'sales.sales_order_load',
                           'sales.sales_order_pdf',
                           'sales.sales_order_cancel',
                           'sales.sales_order_batch_invoice',
                           'sales.sales_order_batch_invoice_step',
                           'sales.sales_order_batch_invoice_cancel',
                           'sales.sales_load_from_order',
                           'sales.sales_customers_picker',
                           'sales.sales_item_info',
                           'sales.sales_uom_info',
                           'sales.sales_item_uoms',
                           'sales.sales_item_inventory',
                           'sales.sales_invoice_type',
                           'sales.sales_item_popup_items',
                           'sales.sales_item_history'],
             'blueprints': ['sales']},
            {'label': 'Sales Return',
             'menu_path': 'sales.sales_return',
             'endpoints': ['sales.sales_return',
                           'sales.sales_return_list',
                           'sales.sales_invoice_list',
                           'sales.sales_invoice_export',
                           'sales.sales_invoice_summary_pdf',
                           'sales.sales_return_next_billno',
                           'sales.sales_return_item_info',
                           'sales.sales_return_uom_info',
                           'sales.sales_return_item_uoms',
                           'sales.sales_return_item_inventory',
                           'sales.sales_return_item_bin_inventory',
                           'sales.sales_return_api_warehouse_bins',
                           'sales.sales_return_invoice_type',
                           'sales.sales_return_item_popup_items',
                           'sales.sales_return_item_history',
                           'sales.sales_return_api_batch_lots_for_line',
                           'sales.sales_return_load_from_invoice',
                           'sales.sales_return_ai_screenshot_lines',
                           'sales.sales_return_save',
                           'sales.sales_customers_picker',
                           'reports.crystal_reports_open_report'],
             'blueprints': ['sales']},
            {'label': 'Sales Accounts Configuration',
             'menu_path': 'sales.sales_accounts_configuration',
             'endpoints': ['sales.sales_accounts_configuration'],
             'blueprints': ['sales']},
            {'label': 'Credit Note',
             'menu_path': 'sales.sales_credit_note_list',
             'endpoints': ['sales.sales_credit_note_list',
                           'sales.sales_credit_note_new',
                           'sales.sales_credit_note_query',
                           'sales.sales_credit_note_edit',
                           'sales.sales_credit_note_next_no_api',
                           'sales.sales_credit_note_refresh_save_nonce',
                           'sales.sales_credit_note_save',
                           'sales.sales_credit_note_items',
                           'sales.sales_credit_note_item_uoms',
                           'sales.sales_customers_picker',
                           'sales.sales_item_popup_items',
                           'sales.sales_item_info',
                           'sales.sales_item_uoms'],
             'blueprints': ['sales']},
            {'label': 'POS Billing',
             'menu_path': 'pos_billing.pos_billing_page',
             'endpoints': ['pos_billing.pos_resolve_counter_by_hostname',
                           'pos_billing.pos_bind_session_counter',
                           'pos_billing.pos_sample_test_barcode',
                           'pos_billing.pos_checkout_tenders_api',
                           'pos_billing.pos_bills_page',
                           'pos_billing.pos_bills_detail',
                           'pos_billing.pos_sales_list_page',
                           'pos_billing.pos_sales_list_summary_api',
                           'pos_billing.pos_counter_operations_page',
                           'pos_billing.pos_counter_operations_open',
                           'pos_billing.pos_counter_operations_close',
                           'pos_billing.pos_tender_types_page',
                           'pos_billing.pos_tender_types_api_bootstrap',
                           'pos_billing.pos_tender_types_api_save',
                           'pos_billing.pos_tender_types_api_delete'],
             'blueprints': ['pos_billing']},
            {'label': 'POS Shop',
             'menu_path': 'pos_billing.pos_shop_page',
             'endpoints': ['pos_billing.pos_shop_page',
                           'pos_billing.pos_products',
                           'pos_billing.pos_shop_categories',
                           'pos_billing.pos_barcode_items',
                           'pos_billing.pos_customers_picker',
                           'pos_billing.pos_checkout_tenders_api',
                           'pos_billing.pos_resolve_counter_by_hostname',
                           'pos_billing.pos_bind_session_counter'],
             'blueprints': ['pos_billing']},
            {'label': 'POS Verify',
             'menu_path': 'pos_billing.pos_verify_page',
             'endpoints': ['pos_billing.pos_verify_page',
                           'pos_billing.pos_verify_simulate_api',
                           'pos_billing.pos_verify_ai_api',
                           'pos_billing.pos_verify_temp_bills_api',
                           'pos_billing.pos_verify_temp_bill_detail_api',
                           'pos_billing.pos_verify_live_stock_api'],
             'blueprints': ['pos_billing']},
            {'label': 'POS Transactions',
             'menu_path': 'pos_billing.pos_bills_page',
             'endpoints': ['pos_billing.pos_bills_page',
                           'pos_billing.pos_bills_detail',
                           'pos_billing.pos_receipt_print',
                           'pos_billing.pos_sales_list_page',
                           'pos_billing.pos_sales_list_summary_api'],
             'blueprints': ['pos_billing']},
            {'label': 'POS Counter Setup',
             'menu_path': 'pos_billing.pos_counter_setup_list',
             'endpoints': ['pos_billing.pos_counter_setup_list',
                           'pos_billing.pos_counter_setup_new',
                           'pos_billing.pos_counter_setup_create',
                           'pos_billing.pos_counter_setup_next_code',
                           'pos_billing.pos_counter_setup_edit',
                           'pos_billing.pos_counter_setup_update',
                           'pos_billing.pos_counter_setup_delete'],
             'blueprints': ['pos_billing']},
            {'label': 'POS Tender Types',
             'menu_path': 'pos_billing.pos_tender_types_page',
             'endpoints': ['pos_billing.pos_tender_types_page',
                           'pos_billing.pos_tender_types_api_bootstrap',
                           'pos_billing.pos_tender_types_api_save',
                           'pos_billing.pos_tender_types_api_delete'],
             'blueprints': ['pos_billing']},
            {'label': 'POS Counter Operations',
             'menu_path': 'pos_billing.pos_counter_operations_page',
             'endpoints': ['pos_billing.pos_counter_operations_page',
                           'pos_billing.pos_counter_operations_open',
                           'pos_billing.pos_counter_operations_close',
                           'pos_billing.pos_counter_operations_shift_bills',
                           'pos_billing.pos_counter_operations_preclose_report',
                           'pos_billing.pos_counter_operations_held_bill_open',
                           'pos_billing.pos_counter_operations_held_bill_cancel'],
             'blueprints': ['pos_billing']},
            {'label': 'POS Receipt Design',
             'menu_path': 'pos_billing.pos_receipt_design_page',
             'endpoints': ['pos_billing.pos_receipt_design_page',
                           'pos_billing.pos_receipt_design_printers',
                           'pos_billing.pos_receipt_design_printer_paper_size',
                           'pos_billing.pos_receipt_design_test_print',
                           'pos_billing.pos_receipt_design_config'],
             'blueprints': ['pos_billing']},
            {'label': 'Printer Setup',
             'menu_path': 'reports.crystal_reports',
             'endpoints': ['reports.crystal_reports',
                           'reports.crystal_reports_cashbilldup',
                           'reports.crystal_reports_cashbilldup_print_payload',
                           'reports.crystal_reports_cashbilldup_qz_pdf',
                           'reports.crystal_reports_open_report',
                           'reports.qz_certificate',
                           'reports.qz_certificate_download',
                           'reports.qz_certificate_regenerate',
                           'reports.qz_cert_info',
                           'reports.qz_sign'],
             'blueprints': ['reports']}]},
 {'title': 'Inventory Management',
  'items': [{'label': 'Item Master',
             'menu_path': 'itemmaster.productlist',
             'endpoints': ['itemmaster.productlist',
                           'itemmaster.productlist_export',
                           'itemmaster.itemmaster',
                           'itemmaster.itemmaster_save',
                           'itemmaster.itemmaster_activity_log',
                           'itemmaster.itemmaster_import_excel',
                           'itemmaster.itemmaster_import_template',
                           'itemmaster.itemmaster_data_config',
                           'itemmaster.itemmaster_data_config_missing_accounts_count',
                           'itemmaster.itemmaster_data_config_backfill_missing_accounts',
                           'itemmaster.itemmaster_data_config_base_alternate_missing_count',
                           'itemmaster.itemmaster_data_config_base_alternate_bulk',
                           'itemmaster.itemmaster_data_config_price_import_template',
                           'itemmaster.itemmaster_data_config_price_import',
                           'itemmaster.itemmaster_data_config_cost_import_template',
                           'itemmaster.itemmaster_data_config_cost_import',
                           'itemmaster.itemmaster_data_config_ai_arabic_missing_count',
                           'itemmaster.itemmaster_data_config_ai_arabic_bulk',
                           'itemmaster.itemmaster_ai_arabic_name',
                           'itemmaster.api_productlist_items',
                           'itemmaster.api_productlist_item_quick_update',
                           'itemmaster.api_itemmaster_bootstrap',
                           'itemmaster.api_itemmaster_default_bins',
                           'itemmaster.api_item_accounts',
                           'itemmaster.api_category_price_percentage',
                           'itemmaster.api_item_ledger'],
             'blueprints': ['itemmaster']},
            {'label': 'Category Master',
             'menu_path': 'itemmaster.category_master_list',
             'endpoints': ['itemmaster.category_master_list',
                           'itemmaster.category_master_save',
                           'itemmaster.category_master_issue_once',
                           'itemmaster.category_master_import_excel',
                           'itemmaster.category_master_import_template'],
             'blueprints': ['itemmaster']},
            {'label': 'Brand Master',
             'menu_path': 'itemmaster.brand_master_list',
             'endpoints': ['itemmaster.brand_master_list', 'itemmaster.brand_master_save'],
             'blueprints': ['itemmaster']},
            {'label': 'Unit of measurement',
             'menu_path': 'itemmaster.unit_of_measurement_list',
             'endpoints': ['itemmaster.unit_of_measurement_list',
                           'itemmaster.unit_of_measurement_save',
                           'itemmaster.unit_of_measurement_issue_once'],
             'blueprints': ['itemmaster']},
            {'label': 'Property & Origin',
             'menu_path': 'itemmaster.item_property_origin_list',
             'endpoints': ['itemmaster.item_property_origin_list', 'itemmaster.item_property_origin_save'],
             'blueprints': ['itemmaster']},
            {'label': 'Repacking',
             'menu_path': 'purchase.repacking_list',
             'endpoints': ['purchase.repacking',
                           'purchase.repacking_list',
                           'purchase.repacking_form',
                           'purchase.repacking_view',
                           'purchase.repacking_pdf',
                           'purchase.repacking_save',
                           'purchase.stock_adjustment_api_items',
                           'purchase.stock_adjustment_item_stock',
                           'purchase.stock_transfer_stores',
                           'purchase.stock_transfer_item_batch_tracked',
                           'purchase.stock_transfer_lots',
                           'purchase.stock_transfer_warehouse_bins',
                           'purchase.stock_transfer_items'],
             'blueprints': ['purchase']},
            {'label': 'Store Transfer',
             'menu_path': 'purchase.stock_transfer',
             'endpoints': ['purchase.stock_transfer',
                           'purchase.stock_transfer_configuration',
                           'purchase.stock_transfer_api_all_rows',
                           'purchase.stock_transfer_new',
                           'purchase.stock_transfer_query',
                           'purchase.stock_transfer_stores',
                           'purchase.stock_transfer_items',
                           'purchase.stock_transfer_item_uoms',
                           'purchase.stock_transfer_item_stock',
                           'purchase.stock_transfer_save',
                           'purchase.stock_transfer_transfer',
                           'purchase.stock_transfer_approve',
                           'purchase.stock_transfer_pdf',
                           'purchase.stock_transfer_approval_setup',
                           'purchase.stock_transfer_approval_setup_init',
                           'purchase.stock_transfer_approval_setup_load',
                           'purchase.stock_transfer_approval_setup_save'],
             'blueprints': ['purchase']},
            {'label': 'Barcode Management',
             'menu_path': 'barcode_management.barcode_management_page',
             'endpoints': ['barcode_management.barcode_management_page',
                           'barcode_management.barcode_products_api',
                           'barcode_management.barcode_items_api',
                           'barcode_management.barcode_grn_lines_api',
                           'barcode_management.barcode_item_uoms_api',
                           'barcode_management.barcode_storage_save_api'],
             'blueprints': ['barcode_management']}]},
 {'title': 'Warehouse Management',
  'items': [{'label': 'Warehouse locations',
             'menu_path': 'warehouse.warehouse_locations',
             'endpoints': ['warehouse.warehouse_locations_list',
                           'warehouse.warehouse_locations_new',
                           'warehouse.warehouse_locations_edit'],
             'blueprints': ['warehouse']},
            {'label': 'Shelf / Bin / Rack',
             'menu_path': 'warehouse.warehouse_storage_list',
             'endpoints': ['warehouse.warehouse_storage_list', 'warehouse.warehouse_storage_save'],
             'blueprints': ['warehouse']},
            {'label': 'Bin stock & moves',
             'menu_path': 'warehouse.warehouse_bin_stock',
             'endpoints': ['warehouse.warehouse_bin_stock',
                           'warehouse.warehouse_bin_stock_save',
                           'warehouse.warehouse_bin_transfer_lines_json'],
             'blueprints': ['warehouse']},
            {'label': 'Visual Stock Report',
             'menu_path': 'warehouse.warehouse_visual_stock',
             'endpoints': ['warehouse.warehouse_visual_stock',
                           'warehouse.warehouse_visual_stock_api',
                           'warehouse.warehouse_visual_stock_export_csv'],
             'blueprints': ['warehouse']},
            {'label': 'Stock verification',
             'menu_path': 'warehouse.warehouse_stock_verification',
             'endpoints': ['warehouse.warehouse_stock_verification',
                           'warehouse.warehouse_stock_verification_api',
                           'warehouse.warehouse_stock_verification_export_csv'],
             'blueprints': ['warehouse']},
            {'label': 'Stock Counting',
             'menu_path': 'warehouse.warehouse_stock_counting',
             'endpoints': ['warehouse.warehouse_stock_counting_list',
                           'warehouse.warehouse_stock_counting_new',
                           'warehouse.warehouse_stock_counting_detail',
                           'warehouse.warehouse_stock_counting_mobile_redirect',
                           'warehouse.warehouse_stock_counting_mobile_scan_redirect',
                           'warehouse.api_stock_count_list',
                           'warehouse.api_stock_count_get',
                           'warehouse.api_stock_count_pdt_upload',
                           'warehouse.api_stock_count_add_line',
                           'warehouse.api_stock_count_edit_line',
                           'warehouse.api_stock_count_delete_line',
                           'warehouse.api_stock_count_post',
                           'warehouse.api_stock_count_cancel',
                           'warehouse.api_stock_count_delete'],
             'blueprints': ['warehouse']},
            {'label': 'Stock Counting (Mobile)',
             'menu_path': 'warehouse.warehouse_stock_counting_mobile',
             'endpoints': ['warehouse.warehouse_stock_counting_mobile_home',
                           'warehouse.warehouse_stock_counting_mobile_new',
                           'warehouse.warehouse_stock_counting_mobile_scan',
                           'warehouse.api_stock_count_list',
                           'warehouse.api_stock_count_get',
                           'warehouse.api_stock_count_pdt_upload',
                           'warehouse.api_stock_count_add_line',
                           'warehouse.api_stock_count_post',
                           'warehouse.api_stock_count_cancel',
                           'warehouse.api_stock_count_delete'],
             'blueprints': ['warehouse']},
            {'label': 'Price Update',
             'menu_path': 'warehouse.warehouse_stock_count_price',
             'endpoints': ['warehouse.warehouse_stock_count_price_list',
                           'warehouse.warehouse_stock_count_price_new',
                           'warehouse.warehouse_stock_count_price_detail',
                           'warehouse.api_stock_count_price_batches',
                           'warehouse.api_stock_count_price_get',
                           'warehouse.api_stock_count_price_lines',
                           'warehouse.api_stock_count_price_apply',
                           'warehouse.api_stock_count_price_delete'],
             'blueprints': ['warehouse']}]},
 {'title': 'Accounts',
  'items': [{'label': 'Chart of Accounts',
             'menu_path': 'accounts.chart_of_accounts_list',
             'endpoints': ['accounts.chart_of_accounts_list',
                           'accounts.chart_of_accounts_create',
                           'accounts.chart_of_accounts_edit',
                           'accounts.chart_of_accounts_delete',
                           'accounts.chart_of_accounts_excel',
                           'accounts.api_chart_list',
                           'accounts.api_chart_get',
                           'accounts.api_chart_create',
                           'accounts.api_chart_update',
                           'accounts.api_chart_delete',
                           'accounts.account_ledger',
                           'accounts.account_ledger_page',
                           'accounts.main_account_ledger',
                           'accounts.main_account_ledger_pdf',
                           'accounts.main_account_ledger_excel',
                           'accounts.account_ledger_pdf',
                           'accounts.account_ledger_excel',
                           'accounts.supplier_ledger_page',
                           'accounts.supplier_ledger_pdf',
                           'accounts.customer_ledger_page',
                           'accounts.customer_ledger_pdf',
                           'accounts.profit_loss',
                           'accounts.profit_loss_pdf',
                           'accounts.profit_loss_excel',
                           'accounts.opening_balance_import',
                           'accounts.opening_balance_sample_csv',
                           'accounts.opening_balance_sample_excel',
                           'accounts.customer_opening_outstanding',
                           'accounts.customer_opening_outstanding_sample_csv',
                           'accounts.supplier_opening_outstanding',
                           'accounts.supplier_opening_outstanding_sample_csv'],
             'blueprints': ['accounts']},
            {'label': 'Accounts Payable (AP)',
             'menu_path': 'accounts.accounts_payable',
             'endpoints': ['accounts.accounts_payable',
                           'accounts.accounts_payable_receipt_new',
                           'accounts.accounts_payable_payment_summary_voucher_pdf',
                           'accounts.accounts_payable_payment_summary_excel',
                           'accounts.accounts_payable_supplier_payment_voucher_pdf'],
             'blueprints': ['accounts']},
            {'label': 'Accounts Receivable (AR)',
             'menu_path': 'accounts.accounts_receivable',
             'endpoints': ['accounts.accounts_receivable',
                           'accounts.accounts_receivable_receipt_new',
                           'accounts.accounts_receivable_receipt_summary_voucher_pdf',
                           'accounts.accounts_receivable_receipt_summary_excel',
                           'accounts.accounts_receivable_customer_receipt_voucher_pdf'],
             'blueprints': ['accounts']},
            {'label': 'Cash Payment Voucher',
             'menu_path': 'accounts.cash_payment_voucher',
             'endpoints': ['accounts.cash_payment_voucher',
                           'accounts.cash_payment_voucher_list',
                           'accounts.cash_payment_voucher_pdf'],
             'blueprints': ['accounts']},
            {'label': 'Receipt Voucher',
             'menu_path': 'accounts.receipt_voucher',
             'endpoints': ['accounts.receipt_voucher', 'accounts.receipt_voucher_list', 'accounts.receipt_voucher_pdf'],
             'blueprints': ['accounts']},
            {'label': 'Payment Voucher',
             'menu_path': 'accounts.payment_voucher',
             'endpoints': ['accounts.payment_voucher', 'accounts.payment_voucher_list', 'accounts.payment_voucher_pdf'],
             'blueprints': ['accounts']},
            {'label': 'Contra Voucher',
             'menu_path': 'accounts.contra_voucher',
             'endpoints': ['accounts.contra_voucher', 'accounts.contra_voucher_list', 'accounts.contra_voucher_pdf'],
             'blueprints': ['accounts']},
            {'label': 'Cash Flow',
             'menu_path': 'accounts.cash_flow',
             'endpoints': ['accounts.cash_flow', 'accounts.cash_flow_pdf', 'accounts.cash_flow_excel'],
             'blueprints': ['accounts']},
            {'label': 'Bank Reconciliation',
             'menu_path': 'accounts.bank_reconciliation',
             'endpoints': ['accounts.bank_reconciliation',
                           'accounts.api_bank_recon_list',
                           'accounts.api_bank_recon_load',
                           'accounts.api_bank_recon_save',
                           'accounts.api_bank_recon_import',
                           'accounts.api_bank_recon_auto_match',
                           'accounts.api_bank_recon_match',
                           'accounts.api_bank_recon_unmatch',
                           'accounts.api_bank_recon_delete'],
             'blueprints': ['accounts']},
            {'label': 'Journal Entry',
             'menu_path': 'accounts.journal_entry',
             'endpoints': ['accounts.journal_entry',
                           'accounts.journal_voucher_view',
                           'accounts.journal_voucher_pdf',
                           'accounts.journal_entry_reverse',
                           'accounts.journal_entry_summary_pdf',
                           'accounts.journal_entry_dimension_values',
                           'accounts.journal_entry_history_suggest',
                           'accounts.opening_balance_import',
                           'accounts.opening_balance_sample_csv',
                           'accounts.opening_balance_sample_excel',
                           'accounts.customer_opening_outstanding',
                           'accounts.customer_opening_outstanding_sample_csv',
                           'accounts.supplier_opening_outstanding',
                           'accounts.supplier_opening_outstanding_sample_csv'],
             'blueprints': ['accounts']},
            {'label': 'Transaction accounts audit',
             'menu_path': 'accounts.transaction_audit',
             'endpoints': ['accounts.transaction_audit',
                           'accounts.api_transaction_audit_vouchers',
                           'accounts.api_transaction_audit_detail',
                           'accounts.transaction_audit_export_csv'],
             'blueprints': ['accounts']},
            {'label': 'Tax (VAT / GST)',
             'menu_path': 'accounts.tax_accounts',
             'endpoints': ['accounts.tax_accounts'],
             'blueprints': ['accounts']},
            {'label': 'Period Closing',
             'menu_path': 'accounts.period_closing_page',
             'endpoints': [
                 'accounts.period_closing_page',
                 'accounts.period_closing_history_page',
                 'accounts.api_period_closing_preview',
                 'accounts.api_period_closing_validate',
                 'accounts.api_period_closing_close',
                 'accounts.api_period_closing_reopen',
                 'accounts.api_period_closing_history',
                 'accounts.api_period_closing_history_detail',
                 'accounts.api_period_closing_draft_sales',
                 'accounts.api_period_closing_draft_sales_delete',
             ],
             'blueprints': ['accounts']},
            {'label': 'Trial Balance',
             'menu_path': 'accounts.trial_balance',
             'endpoints': ['accounts.trial_balance', 'accounts.trial_balance_pdf', 'accounts.trial_balance_excel', 'accounts.trial_balance_ledger_api'],
             'blueprints': ['accounts']},
            {'label': 'Profit & Loss',
             'menu_path': 'accounts.profit_loss',
             'endpoints': ['accounts.profit_loss', 'accounts.profit_loss_pdf', 'accounts.profit_loss_excel'],
             'blueprints': ['accounts']},
            {'label': 'Balance Sheet',
             'menu_path': 'accounts.balance_sheet',
             'endpoints': ['accounts.balance_sheet', 'accounts.balance_sheet_pdf', 'accounts.balance_sheet_excel', 'accounts.balance_sheet_ledger_api'],
             'blueprints': ['accounts']},
            {'label': 'PDC Check Tracking',
             'menu_path': 'accounts.pdc_tracker',
             'endpoints': ['accounts.pdc_tracker',
                           'accounts.pdc_add',
                           'accounts.pdc_edit',
                           'accounts.pdc_update_status',
                           'accounts.pdc_delete',
                           'accounts.api_pdc_list',
                           'accounts.api_pdc_audit_log'],
             'blueprints': ['accounts']}]},
 {'title': 'Fixed Assets',
  'items': [{'label': 'Categories',
             'menu_path': 'fixed_assets.fa_category_list',
             'endpoints': [
                 'fixed_assets.fa_category_list',
                 'fixed_assets.fa_category_form',
                 'fixed_assets.fa_category_delete',
             ],
             'blueprints': ['fixed_assets']},
            {'label': 'Asset Register',
             'menu_path': 'fixed_assets.fa_asset_list',
             'endpoints': [
                 'fixed_assets.fa_asset_list',
                 'fixed_assets.fa_asset_form',
                 'fixed_assets.fa_asset_post_acquisition',
             ],
             'blueprints': ['fixed_assets']},
            {'label': 'Depreciation',
             'menu_path': 'fixed_assets.fa_depreciation',
             'endpoints': [
                 'fixed_assets.fa_depreciation_page',
                 'fixed_assets.fa_depreciation_preview',
                 'fixed_assets.fa_depreciation_create_run',
                 'fixed_assets.fa_depreciation_post',
                 'fixed_assets.fa_api_preview',
             ],
             'blueprints': ['fixed_assets']},
            {'label': 'Fixed Asset Sale',
             'menu_path': 'fixed_assets.fa_sale_list',
             'endpoints': [
                 'fixed_assets.fa_sale_list',
                 'fixed_assets.fa_sale_form',
                 'fixed_assets.fa_sale_post',
                 'fixed_assets.fa_sale_pdf',
             ],
             'blueprints': ['fixed_assets']},
            {'label': 'Disposal',
             'menu_path': 'fixed_assets.fa_disposal_list',
             'endpoints': [
                 'fixed_assets.fa_disposal_list',
                 'fixed_assets.fa_disposal_form',
                 'fixed_assets.fa_disposal_post',
             ],
             'blueprints': ['fixed_assets']},
            {'label': 'Transfer',
             'menu_path': 'fixed_assets.fa_transfer_list',
             'endpoints': [
                 'fixed_assets.fa_transfer_list',
                 'fixed_assets.fa_transfer_form',
             ],
             'blueprints': ['fixed_assets']}]},
 {'title': 'Accounts Posting',
  'items': [{'label': 'Purchase Invoice', 'menu_path': 'purchase.purchase_invoice_list', 'blueprints': ['purchase']},
            {'label': 'Purchase Return Posting',
             'menu_path': 'purchase.purchase_return_posting',
             'endpoints': ['purchase.purchase_return_posting', 'purchase.api_purchase_return_post']},
            {'label': 'POS Settlement Posting',
             'menu_path': 'pos_billing.pos_settlement_posting_page',
             'endpoints': list(_POS_SETTLEMENT_POSTING_ENDPOINTS),
             'blueprints': ['pos_billing']},
            {'label': 'Online Settlement',
             'menu_path': 'accounts.online_settlement_page',
             'endpoints': [
                 'accounts.online_settlement_page',
                 'accounts.online_settlement_history',
                 'accounts.online_settlement_reports',
                 'accounts.api_online_settlement_upload',
                 'accounts.api_online_settlement_validate',
                 'accounts.api_online_settlement_auto_match',
                 'accounts.api_online_settlement_post',
                 'accounts.api_online_settlement_batch',
                 'accounts.api_online_settlement_config',
                 'accounts.api_online_settlement_line',
                 'accounts.api_online_settlement_open_invoices',
                 'accounts.api_online_settlement_export_exceptions',
                 'accounts.api_online_settlement_export_report',
                 'accounts.online_settlement_sample_csv',
                 'accounts.online_settlement_sample_xlsx',
             ],
             'blueprints': ['accounts']}]},
 {'title': 'Purchase',
  'items': [{'label': 'Purchase Order',
             'menu_path': 'purchase.purchase_order_list',
             'endpoints': ['purchase.api_lpo_approval_status',
                           'purchase.api_lpo_approve',
                           'purchase.api_lpo_cancel',
                           'purchase.api_lpo_cart_load',
                           'purchase.api_lpo_cart_new',
                           'purchase.api_lpo_cart_save',
                           'purchase.api_lpo_cart_supplier',
                           'purchase.api_lpo_item_uoms',
                           'purchase.api_lpo_items',
                           'purchase.api_lpo_list',
                           'purchase.api_lpo_load',
                           'purchase.api_lpo_next_no',
                           'purchase.api_lpo_pdf',
                           'purchase.api_lpo_reject',
                           'purchase.api_lpo_save',
                           'purchase.api_lpo_submit',
                           'purchase.api_lpo_suppliers',
                           'purchase.api_lpo_warehouses',
                           'purchase.api_po_sales_invoice_import_fetch',
                           'purchase.api_po_sales_invoice_import_tenants',
                           'purchase.purchase_order_edit',
                           'purchase.purchase_order_list',
                           'purchase.purchase_order_new',
                           'purchase.purchase_order_query'],
             'blueprints': ['purchase']},
            {'label': 'Goods Receipt Note (GRN)',
             'menu_path': 'purchase.goods_receipt_list',
             'endpoints': ['purchase.goods_receipt_list',
                           'purchase.goods_receipt_new',
                           'purchase.goods_receipt_query',
                           'purchase.api_receipt_next_no',
                           'purchase.api_receipt_transaction_date',
                           'purchase.api_receipt_suppliers',
                           'purchase.api_receipt_items',
                           'purchase.api_receipt_save',
                           'purchase.api_receipt_approval_status',
                           'purchase.api_receipt_submit',
                           'purchase.api_receipt_approve',
                           'purchase.api_receipt_reject',
                           'purchase.api_receipt_load_from_lpo',
                           'purchase.api_receipt_receive_locations',
                           'purchase.api_test_itemstore'],
             'blueprints': ['purchase']},
            {'label': 'Purchase Return',
             'menu_path': 'purchase.purchase_return_list',
             'endpoints': ['purchase.api_purchase_return_load_from_order',
                           'purchase.api_purchase_return_load_from_grn',
                           'purchase.api_purchase_return_grn_picker',
                           'purchase.api_purchase_return_next_no',
                           'purchase.api_purchase_return_save',
                           'purchase.api_return_order_approve',
                           'purchase.api_return_order_cancel',
                           'purchase.api_return_order_next_no',
                           'purchase.api_return_order_pdf',
                           'purchase.api_return_order_save',
                           'purchase.purchase_return_list',
                           'purchase.purchase_return_new',
                           'purchase.purchase_return_order',
                           'purchase.purchase_return_order_edit',
                           'purchase.purchase_return_order_new',
                           'purchase.purchase_return_order_query',
                           'purchase.purchase_return_query',
                           'purchase.purchase_return_request_list'],
             'blueprints': ['purchase']},
            {'label': 'Purchase change log',
             'menu_path': 'purchase.purchase_change_log',
             'endpoints': ['purchase.purchase_change_log',
                           'purchase.api_purchase_change_log_list'],
             'blueprints': ['purchase']},
            {'label': 'Debit Note',
             'menu_path': 'purchase.purchase_debit_note_list',
             'endpoints': ['purchase.purchase_debit_note_list',
                           'purchase.purchase_debit_note_new',
                           'purchase.purchase_debit_note_post_new',
                           'purchase.purchase_debit_note_request_query',
                           'purchase.purchase_debit_note_request_edit',
                           'purchase.purchase_debit_note_query',
                           'purchase.api_return_order_next_no',
                           'purchase.api_return_order_save',
                           'purchase.api_purchase_return_load_from_order',
                           'purchase.api_debit_note_request_pdf',
                           'purchase.api_debit_note_request_next_no',
                           'purchase.api_purchase_debit_note_refresh_save_nonce',
                           'purchase.api_purchase_debit_note_next_no',
                           'purchase.api_purchase_debit_note_save',
                           'purchase.api_debit_note_pdf'],
             'blueprints': ['purchase']},
            {'label': 'Stock Adjustment',
             'menu_path': 'purchase.stock_adjustment_list',
             'endpoints': ['purchase.stock_adjustment',
                           'purchase.stock_adjustment_list',
                           'purchase.stock_adjustment_form',
                           'purchase.stock_adjustment_view',
                           'purchase.stock_adjustment_next_no',
                           'purchase.stock_adjustment_api_items',
                           'purchase.stock_adjustment_item_stock',
                           'purchase.stock_adjustment_save',
                           'purchase.stock_adjustment_pdf',
                           'purchase.stock_adjustment_reverse',
                           'purchase.api_stock_adjustment_change_date'],
             'blueprints': ['purchase']},
            {'label': 'Inventory Valuation',
             'menu_path': 'purchase.inventory_valuation',
             'endpoints': ['purchase.inventory_valuation',
                           'purchase.inventory_valuation_api',
                           'purchase.inventory_valuation_export_csv',
                           'purchase.inventory_valuation_export_pdf'],
             'blueprints': ['purchase']},
            {'label': 'Inventory Value Adjustment',
             'menu_path': 'purchase.inventory_value_adjustment_list',
             'endpoints': ['purchase.inventory_value_adjustment',
                           'purchase.inventory_value_adjustment_list',
                           'purchase.inventory_value_adjustment_form',
                           'purchase.inventory_value_adjustment_view',
                           'purchase.inventory_value_adjustment_api_items',
                           'purchase.inventory_value_adjustment_api_item_context',
                           'purchase.inventory_value_adjustment_api_save'],
             'blueprints': ['purchase']},
            {'label': 'Item Journal',
             'menu_path': 'purchase.item_journal_list',
             'endpoints': ['purchase.item_journal_list',
                           'purchase.item_journal_export'],
             'blueprints': ['purchase']},
            {'label': 'Item Journal Summary',
             'menu_path': 'purchase.item_journal_summary_list',
             'endpoints': ['purchase.item_journal_summary_list'],
             'blueprints': ['purchase']},
            {'label': 'Purchase verification',
             'menu_path': 'purchase.purchase_verification',
             'endpoints': ['purchase.purchase_verification',
                           'purchase.api_purchase_verification_documents',
                           'purchase.api_purchase_verification_detail',
                           'purchase.purchase_verification_export_csv'],
             'blueprints': ['purchase']},
            {'label': 'Batch / Expiry (lots)',
             'menu_path': 'purchase.batch_lot_inquiry',
             'endpoints': ['purchase.batch_lot_inquiry',
                           'purchase.batch_lot_operator_checklist',
                           'purchase.batch_lot_movements_json',
                           'purchase.batch_lot_set_tracked',
                           'purchase.batch_lot_putaway_api',
                           'purchase.batch_lot_bins_api',
                           'purchase.batch_lot_bin_breakdown_api'],
             'blueprints': ['purchase']}]},
 {'title': 'Reports & Analytics',
  'items': [            {'label': 'Business Summary Dashboard',
             'menu_path': 'business_summary.dashboard',
             'endpoints': ['business_summary.dashboard', 'business_summary.api_dashboard'],
             'blueprints': ['business_summary']},
            {'label': 'Sales Summary', 'menu_path': 'sales_summary.sales_summary', 'blueprints': ['sales_summary']},
            {'label': 'Sales Invoices',
             'menu_path': 'temporary_invoices.temporary_invoices',
             'endpoints': ['temporary_invoices.temporary_invoices',
                           'temporary_invoices.invoice_analysis',
                           'temporary_invoices.salesanalysis_data_config',
                           'temporary_invoices.api_salesanalysis_config',
                           'temporary_invoices.api_salesanalysis_db_objects',
                           'temporary_invoices.api_salesanalysis_table_columns',
                           'temporary_invoices.api_invoice_analysis_columns',
                           'temporary_invoices.api_invoice_analysis_run',
                           'temporary_invoices.api_invoice_analysis_ai_suggest',
                           'temporary_invoices.api_invoice_analysis_sql_preview'],
             'blueprints': ['temporary_invoices']},
            {'label': 'Customer Outstanding CR',
             'menu_path': 'reports.customer_outstanding_cr',
             'endpoints': ['reports.customer_outstanding_cr',
                           'reports.customer_outstanding_cr_month',
                           'reports.customer_outstanding_cr_month_export',
                           'reports.customer_outstanding_cr_details_cash',
                           'reports.customer_outstanding_cr_details_credit',
                           'reports.customer_outstanding_cr_export_summary',
                           'reports.customer_outstanding_cr_export_cash',
                           'reports.customer_outstanding_cr_export_credit']},
            {'label': 'Customer Outstanding CR (month)',
             'menu_path': 'reports.customer_outstanding_cr_month',
             'endpoints': ['reports.customer_outstanding_cr_month',
                           'reports.customer_outstanding_cr_month_export',
                           'reports.customer_outstanding_cr_details_cash',
                           'reports.customer_outstanding_cr_details_credit',
                           'reports.customer_outstanding_cr_export_cash',
                           'reports.customer_outstanding_cr_export_credit'],
             'blueprints': ['reports']},
            {'label': 'Route Outstanding',
             'menu_path': 'reports.route_outstanding',
             'endpoints': ['reports.route_outstanding',
                           'reports.route_outstanding_details',
                           'reports.route_outstanding_export',
                           'reports.route_outstanding_details_export']},
            {'label': 'Collection Report',
             'menu_path': 'reports.collection_report',
             'endpoints': ['reports.collection_report'],
             'blueprints': ['reports']},
            {'label': 'Store Transfer Details',
             'menu_path': 'reports.store_transfer_details',
             'endpoints': ['reports.store_transfer_details'],
             'blueprints': ['reports']},
            {'label': 'Purchase Details',
             'menu_path': 'reports.purchase_details',
             'endpoints': ['reports.purchase_details',
                           'reports.purchase_details_suppliers_api',
                           'reports.purchase_details_items_api',
                           'reports.purchase_details_export_excel'],
             'blueprints': ['reports']},
            {'label': 'GRN Details',
             'menu_path': 'reports.grn_details',
             'endpoints': ['reports.grn_details',
                           'reports.grn_details_suppliers_api',
                           'reports.grn_details_items_api',
                           'reports.grn_details_export_excel'],
             'blueprints': ['reports']},
            {'label': 'Purchase Return Details',
             'menu_path': 'reports.purchase_return_details',
             'endpoints': ['reports.purchase_return_details',
                           'reports.purchase_return_details_suppliers_api',
                           'reports.purchase_return_details_items_api',
                           'reports.purchase_return_details_export_excel'],
             'blueprints': ['reports']},
            {'label': 'Sales Details',
             'menu_path': 'reports.sales_details',
             'endpoints': ['reports.sales_details',
                           'reports.sales_details_customers_api',
                           'reports.sales_details_items_api',
                           'reports.sales_details_export_excel'],
             'blueprints': ['reports']},
            {'label': 'Last Transactions',
             'menu_path': 'reports.last_transactions_report',
             'endpoints': ['reports.last_transactions_report', 'reports.last_transactions_report_export_excel'],
             'blueprints': ['reports']},
            {'label': 'Stock Report',
             'menu_path': 'reports.stock_report',
             'endpoints': ['reports.stock_report',
                           'reports.stock_report_export',
                           'reports.stock_report_pdf',
                           'reports.stock_report_micro_export'],
             'blueprints': ['reports']},
            {'label': 'Stock Report Datewise',
             'menu_path': 'reports.stock_report_datewise',
             'endpoints': ['reports.stock_report_datewise', 'reports.stock_report_datewise_export_excel'],
             'blueprints': ['reports']},
            {'label': 'Margin Report',
             'menu_path': 'reports.margin_report',
             'endpoints': ['reports.margin_report',
                           'reports.margin_report_export_excel',
                           'reports.report_customer_search',
                           'reports.report_category_search'],
             'blueprints': ['reports']},
            {'label': 'System Logs',
             'menu_path': 'reports.system_logs',
             'endpoints': ['reports.system_logs'],
             'blueprints': ['reports']}]},
 {'title': 'Utilities',
  'items': [{'label': 'Send SMS', 'menu_path': 'sms.sms_page', 'blueprints': ['sms']},
            {'label': 'Send SMS Credit', 'menu_path': 'sms.sms_credit_page', 'blueprints': ['sms']},
            {'label': 'WhatsApp', 'menu_path': 'sms.whatsapp_page', 'blueprints': ['sms']},
            {'label': 'DB modes guide',
             'menu_path': 'utilities.database_modes_guide',
             'endpoints': ['utilities_db_modes.database_modes_guide_page'],
             'blueprints': ['utilities_db_modes']},
            {'label': 'Backup',
             'menu_path': 'utilities.backup',
             'endpoints': ['utilities_backup.backup_page', 'utilities_backup.backup_download'],
             'blueprints': ['utilities_backup']},
            {'label': 'Password Change',
             'menu_path': 'auth.change_password',
             'endpoints': ['auth.change_password', 'auth.update_password']}]},
 {'title': 'HO',
  'items': [{'label': 'Itemmaster Central',
             'menu_path': 'ho.itemmaster_central',
             'endpoints': ['ho.itemmaster_central',
                           'ho.itemmaster_central_activity_log',
                           'ho.itemmaster_central_remap',
                           'ho.itemmaster_central_delete_item',
                           'ho.itemmaster_central_save_item',
                           'ho.itemmaster_central_form',
                           'ho.itemmaster_central_next_code',
                           'ho.item_request_reject']},
            {'label': 'Supplier Central',
             'menu_path': 'ho.supplier_central',
             'endpoints': ['ho.supplier_central', 'ho.supplier_central_form', 'ho.supplier_central_save']},
            {'label': 'Customer Creation',
             'menu_path': 'ho.customer_central',
             'endpoints': ['ho.customer_central',
                           'ho.customer_central_form',
                           'ho.customer_central_save',
                           'ho.customer_central_next_code',
                           'ho.customer_central_check_name',
                           'ho.customer_request_ai_process',
                           'ho.customer_request_ai_auto_convert_set',
                           'ho.customer_request_pending_count',
                           'ho.customer_request_alert_dismiss',
                           'ho.customer_request_accounts_api',
                           'ho.cc_api_salesman_list',
                           'ho.cc_api_category_list',
                           'ho.cc_api_route_list',
                           'ho.cc_api_employee_list']}]},
 {'title': 'Master Request',
  'items': [{'label': 'Item Request',
             'menu_path': 'ho.item_request',
             'endpoints': ['ho.item_request',
                           'ho.item_request_convert',
                           'ho.item_request_form',
                           'ho.item_request_next_code',
                           'ho.item_request_save_item']},
            {'label': 'Customer Request',
             'menu_path': 'ho.customer_request',
             'endpoints': ['ho.customer_request',
                           'ho.customer_request_form',
                           'ho.customer_request_save',
                           'ho.customer_request_pending_count',
                           'ho.customer_request_alert_dismiss',
                           'ho.customer_request_approve',
                           'ho.customer_request_reject',
                           'ho.customer_request_reopen',
                           'ho.customer_request_ack_alert',
                           'ho.customer_request_convert',
                           'ho.customer_request_ai_process',
                           'ho.customer_request_ai_auto_convert_set',
                           'ho.customer_request_accounts_api',
                           'ho.cc_api_salesman_list',
                           'ho.cc_api_category_list',
                           'ho.cc_api_route_list',
                           'ho.cc_api_employee_list']}]},
 {'title': 'Notifications',
  'items': [{'label': 'Outstanding due',
             'menu_path': 'notifications.outstanding_due',
             'endpoints': ['notifications.outstanding_due'],
             'blueprints': ['notifications']}]},
 {'title': 'Demo addon (Odoo-style layout)',
  'items': [{'label': 'Demo Sales (sample module)',
             'menu_path': 'demo_sales.dashboard',
             'endpoints': ['demo_sales.dashboard', 'demo_sales.orders', 'demo_sales.pipeline'],
             'blueprints': ['demo_sales']}]},
 {'title': 'AI',
  'items': [{'label': 'Sales AI Dashboard',
             'menu_path': 'sales_ai.dashboard',
             'endpoints': [
                 'sales_ai.dashboard',
                 'sales_ai.api_dashboard',
                 'sales_ai.api_narrative',
             ],
             'blueprints': ['sales_ai']},
            {'label': 'AI Forecasting',
             'menu_path': 'ai_forecast.dashboard',
             'endpoints': [
                 'ai_forecast.dashboard',
                 'ai_forecast.sales_forecast_page',
                 'ai_forecast.purchase_forecast_page',
                 'ai_forecast.reorder_page',
                 'ai_forecast.products_page',
                 'ai_forecast.suppliers_page',
                 'ai_forecast.customers_page',
                 'ai_forecast.reports_page',
                 'ai_forecast.api_dashboard',
                 'ai_forecast.api_sales_forecast',
                 'ai_forecast.api_purchase_forecast',
                 'ai_forecast.api_reorder',
                 'ai_forecast.api_products',
                 'ai_forecast.api_suppliers',
                 'ai_forecast.api_customers',
                 'ai_forecast.api_report',
                 'ai_forecast.reports_export',
                 'ai_forecast.api_insights_narrative',
             ],
             'blueprints': ['ai_forecast']},
            {'label': 'Smart List',
             'menu_path': 'reports.smart_list',
             'endpoints': ['reports.smart_list',
                           'reports.smart_list_tables',
                           'reports.smart_list_columns',
                           'reports.smart_list_run',
                           'reports.smart_list_sql',
                           'reports.smart_list_ai',
                           'reports.smart_list_export',
                           'reports.smart_list_ai_history_list',
                           'reports.smart_list_ai_history_get',
                           'reports.smart_list_ai_history_delete',
                           'reports.smart_list_ai_history_rename'],
             'blueprints': ['reports']},
            {'label': 'Stock Aging',
             'menu_path': 'reports.stock_aging_report',
             'endpoints': [
                 'reports.stock_aging_report',
                 'reports.stock_aging_api_data',
                 'reports.stock_aging_api_drilldown',
                 'reports.stock_aging_export_excel',
                 'reports.stock_aging_export_pdf',
             ],
             'blueprints': ['reports']},
            {'label': 'Integrity Dashboard',
             'menu_path': 'reports.integrity_dashboard_page',
             'endpoints': [
                 'reports.integrity_dashboard_page',
                 'reports.integrity_dashboard_api_data',
                 'reports.integrity_dashboard_api_journal',
                 'reports.integrity_dashboard_api_item_movement',
                 'reports.integrity_dashboard_api_stock_item',
                 'reports.integrity_dashboard_api_stock_gl_drill',
                 'reports.integrity_dashboard_export_excel',
                 'reports.integrity_dashboard_export_pdf',
             ],
             'blueprints': ['reports']},
            {'label': 'Gross Margin Analysis',
             'menu_path': 'reports.gross_margin_dashboard_page',
             'endpoints': [
                 'reports.gross_margin_dashboard_page',
                 'reports.gross_margin_api_data',
                 'reports.gross_margin_api_drilldown',
                 'reports.gross_margin_export_excel',
                 'reports.gross_margin_export_pdf',
             ],
             'blueprints': ['reports']},
            {'label': 'Transaction Recording Audit',
             'menu_path': 'transaction_recording_audit.viewer',
             'endpoints': [
                 'transaction_recording_audit.viewer_page',
                 'transaction_recording_audit.replay_page',
                 'transaction_recording_audit.dashboard_page',
                 'transaction_recording_audit.api_list',
                 'transaction_recording_audit.api_detail',
                 'transaction_recording_audit.api_dashboard',
                 'transaction_recording_audit.api_usernames',
                 'transaction_recording_audit.serve_file',
             ],
             'blueprints': ['transaction_recording_audit']}]}]
_REPACKING_MENU_ITEM: Dict[str, object] = {
    'label': 'Repacking',
    'menu_path': 'purchase.repacking_list',
    'endpoints': [
        'purchase.repacking',
        'purchase.repacking_list',
        'purchase.repacking_form',
        'purchase.repacking_view',
        'purchase.repacking_pdf',
        'purchase.repacking_save',
        'purchase.stock_adjustment_api_items',
        'purchase.stock_adjustment_item_stock',
        'purchase.stock_transfer_stores',
        'purchase.stock_transfer_item_batch_tracked',
        'purchase.stock_transfer_lots',
        'purchase.stock_transfer_warehouse_bins',
        'purchase.stock_transfer_items',
    ],
    'blueprints': ['purchase'],
}

for _group in MENU_GROUPS:
    if _group.get('title') == 'Inventory Management':
        _items = _group.setdefault('items', [])
        if isinstance(_items, list) and not any((it or {}).get('menu_path') in ('purchase.repacking', 'purchase.repacking_list') for it in _items if isinstance(it, dict)):
            _insert_at = 0
            for _idx, _it in enumerate(_items):
                if isinstance(_it, dict) and _it.get('menu_path') == 'purchase.stock_transfer':
                    _insert_at = _idx
                    break
            _items.insert(_insert_at, _REPACKING_MENU_ITEM)
        if isinstance(_items, list):
            _merged: List[Dict[str, object]] = []
            _legacy_transit_eps: List[str] = []
            for _it in _items:
                if not isinstance(_it, dict):
                    _merged.append(_it)
                    continue
                if _it.get('menu_path') == 'purchase.store_transit_approval':
                    for _ep in _it.get('endpoints') or []:
                        if _ep not in _legacy_transit_eps:
                            _legacy_transit_eps.append(_ep)
                    continue
                if _it.get('menu_path') == 'purchase.stock_transfer':
                    _it = dict(_it)
                    _eps = list(_it.get('endpoints') or [])
                    for _ep in _legacy_transit_eps:
                        if _ep not in _eps:
                            _eps.append(_ep)
                    _it['endpoints'] = _eps
                _merged.append(_it)
            _group['items'] = _merged
        break

_PURCHASE_ORDER_NEW_MENU_ITEM: Dict[str, object] = {
    'label': 'New LPO',
    'menu_path': 'purchase.purchase_order_new',
    'endpoints': [
        'purchase.purchase_order_new',
        'purchase.api_lpo_next_no',
        'purchase.api_lpo_suppliers',
        'purchase.api_lpo_items',
        'purchase.api_lpo_item_uoms',
        'purchase.api_lpo_warehouses',
        'purchase.api_lpo_cart_new',
        'purchase.api_lpo_cart_supplier',
        'purchase.api_lpo_cart_load',
        'purchase.api_lpo_cart_save',
        'purchase.api_lpo_save',
        'purchase.api_lpo_load',
        'purchase.api_lpo_pdf',
        'purchase.api_po_sales_invoice_import_tenants',
        'purchase.api_po_sales_invoice_import_fetch',
    ],
    'blueprints': ['purchase'],
}

_PURCHASE_ORDER_LIST_MENU_ITEM: Dict[str, object] = {
    'label': 'LPO List',
    'menu_path': 'purchase.purchase_order_list',
    'endpoints': [
        'purchase.purchase_order_list',
        'purchase.purchase_order_query',
        'purchase.purchase_order_edit',
        'purchase.api_lpo_list',
        'purchase.api_lpo_cancel',
        'purchase.api_lpo_approval_status',
        'purchase.api_lpo_submit',
        'purchase.api_lpo_approve',
        'purchase.api_lpo_reject',
        'purchase.api_lpo_load',
        'purchase.api_lpo_pdf',
    ],
    'blueprints': ['purchase'],
}

_PURCHASE_ORDER_MENU_ITEM: Dict[str, object] = {
    'label': 'Purchase Order',
    'menu_path': 'purchase.purchase_order_list',
    'endpoints': sorted(
        set(_PURCHASE_ORDER_NEW_MENU_ITEM.get('endpoints', []))
        | set(_PURCHASE_ORDER_LIST_MENU_ITEM.get('endpoints', []))
    ),
    'blueprints': ['purchase'],
}

_PURCHASE_RETURN_REQUEST_MENU_ITEM: Dict[str, object] = {
    'label': 'Purchase Return Request',
    'menu_path': 'purchase.purchase_return_order',
    'endpoints': [
        'purchase.purchase_return_order',
        'purchase.purchase_return_request_list',
        'purchase.purchase_return_order_new',
        'purchase.purchase_return_order_query',
        'purchase.purchase_return_order_edit',
        'purchase.api_return_order_next_no',
        'purchase.api_return_order_save',
        'purchase.api_return_order_approve',
        'purchase.api_return_order_cancel',
        'purchase.api_return_order_pdf',
        'purchase.api_purchase_return_load_from_grn',
        'purchase.api_purchase_return_grn_picker',
    ],
    'blueprints': ['purchase'],
}

for _group in MENU_GROUPS:
    if _group.get('title') == 'Purchase':
        _items = _group.get('items', [])
        if isinstance(_items, list):
            _po_menu = _PURCHASE_ORDER_MENU_ITEM
            _rebuilt: List[Dict[str, object]] = []
            _po_done = False
            for _it in _items:
                if not isinstance(_it, dict):
                    _rebuilt.append(_it)
                    continue
                if _it.get('menu_path') in (
                    'purchase.purchase_order_list',
                    'purchase.purchase_order_new',
                ):
                    if not _po_done:
                        _rebuilt.append(dict(_po_menu))
                        _po_done = True
                    continue
                _rebuilt.append(_it)
            if not _po_done:
                _rebuilt.insert(0, dict(_po_menu))
            _group['items'] = _rebuilt
        break

for _group in MENU_GROUPS:
    if _group.get('title') == 'Purchase':
        _items = _group.get('items', [])
        if isinstance(_items, list):
            _merged_eps = set(_PURCHASE_RETURN_REQUEST_MENU_ITEM.get('endpoints', []))
            for _it in _items:
                if isinstance(_it, dict) and _it.get('menu_path') == 'purchase.purchase_return_list':
                    _it['label'] = 'Purchase Return'
                    _eps = set(_it.get('endpoints', []))
                    _eps.update(_merged_eps)
                    _it['endpoints'] = sorted(_eps)
                    break
            _group['items'] = [
                _it for _it in _items
                if not (isinstance(_it, dict) and _it.get('menu_path') == 'purchase.purchase_return_order')
            ]
        break

for _group in MENU_GROUPS:
    if _group.get('title') == 'Accounts':
        for _item in _group.get('items', []):
            if isinstance(_item, dict) and _item.get('menu_path') == 'accounts.cash_payment_voucher':
                _eps = _item.setdefault('endpoints', [])
                for _ep in ('accounts.cash_payment_voucher_list', 'accounts.cash_payment_voucher', 'accounts.cash_payment_voucher_pdf'):
                    if _ep not in _eps:
                        _eps.append(_ep)
                break
        break

for _group in MENU_GROUPS:
    for _item in _group.get('items', []):
        if isinstance(_item, dict) and _item.get('menu_path') == 'pos_billing.pos_settlement_posting_page':
            _eps = _item.setdefault('endpoints', [])
            if 'pos_billing.pos_settlement_posting_pdf' not in _eps:
                _eps.append('pos_billing.pos_settlement_posting_pdf')
            break


def _mi(
    label: str,
    menu_path: str,
    *,
    endpoints: Optional[List[str]] = None,
    blueprints: Optional[List[str]] = None,
    roles_subsection: Optional[str] = None,
    roles_visible: bool = True,
) -> Dict[str, object]:
    item: Dict[str, object] = {'label': label, 'menu_path': menu_path, 'roles_visible': roles_visible}
    if endpoints is not None:
        item['endpoints'] = endpoints
    if blueprints is not None:
        item['blueprints'] = blueprints
    if roles_subsection:
        item['roles_subsection'] = roles_subsection
    return item


# Sidebar / base.html menu_path values that were missing from Roles & Permissions checkboxes.
_MENU_REGISTRY_SUPPLEMENTS: List[Tuple[str, List[Dict[str, object]]]] = [
    ('Master', [
        _mi('Activity log', 'activity_log.activity_log_page', endpoints=['activity_log.activity_log_page'], blueprints=['activity_log']),
    ]),
    ('Reports & Analytics', [
        _mi('Transaction Recording Audit', 'transaction_recording_audit.viewer',
            endpoints=[
                'transaction_recording_audit.viewer_page',
                'transaction_recording_audit.replay_page',
                'transaction_recording_audit.dashboard_page',
                'transaction_recording_audit.api_list',
                'transaction_recording_audit.api_detail',
                'transaction_recording_audit.api_dashboard',
                'transaction_recording_audit.api_usernames',
                'transaction_recording_audit.serve_file',
            ],
            blueprints=['transaction_recording_audit']),
    ]),
    ('AI', [
        _mi('Sales AI Dashboard', 'sales_ai.dashboard',
            endpoints=['sales_ai.dashboard', 'sales_ai.api_dashboard', 'sales_ai.api_narrative'],
            blueprints=['sales_ai'], roles_subsection='AI — pages'),
        _mi('Sales forecast', 'ai_forecast.sales_forecast_page',
            endpoints=['ai_forecast.sales_forecast_page', 'ai_forecast.api_sales_forecast'],
            blueprints=['ai_forecast'], roles_subsection='AI — pages'),
        _mi('Purchase forecast', 'ai_forecast.purchase_forecast_page',
            endpoints=['ai_forecast.purchase_forecast_page', 'ai_forecast.api_purchase_forecast'],
            blueprints=['ai_forecast'], roles_subsection='AI — pages'),
        _mi('Smart reorder', 'ai_forecast.reorder_page',
            endpoints=['ai_forecast.reorder_page', 'ai_forecast.api_reorder'],
            blueprints=['ai_forecast'], roles_subsection='AI — pages'),
        _mi('Product performance', 'ai_forecast.products_page',
            endpoints=['ai_forecast.products_page', 'ai_forecast.api_products'],
            blueprints=['ai_forecast'], roles_subsection='AI — pages'),
        _mi('Supplier analysis', 'ai_forecast.suppliers_page',
            endpoints=['ai_forecast.suppliers_page', 'ai_forecast.api_suppliers'],
            blueprints=['ai_forecast'], roles_subsection='AI — pages'),
        _mi('Customer analysis', 'ai_forecast.customers_page',
            endpoints=['ai_forecast.customers_page', 'ai_forecast.api_customers'],
            blueprints=['ai_forecast'], roles_subsection='AI — pages'),
        _mi('AI reports', 'ai_forecast.reports_page',
            endpoints=['ai_forecast.reports_page', 'ai_forecast.api_report', 'ai_forecast.reports_export', 'ai_forecast.api_insights_narrative'],
            blueprints=['ai_forecast'], roles_subsection='AI — pages'),
        _mi('Stock Aging', 'reports.stock_aging_report',
            endpoints=['reports.stock_aging_report', 'reports.stock_aging_api_data', 'reports.stock_aging_api_drilldown',
                       'reports.stock_aging_export_excel', 'reports.stock_aging_export_pdf'],
            blueprints=['reports'], roles_subsection='AI — pages'),
        _mi('Integrity Dashboard', 'reports.integrity_dashboard_page',
            endpoints=['reports.integrity_dashboard_page', 'reports.integrity_dashboard_api_data',
                       'reports.integrity_dashboard_api_journal', 'reports.integrity_dashboard_api_item_movement',
                       'reports.integrity_dashboard_api_stock_item', 'reports.integrity_dashboard_api_stock_gl_drill',
                       'reports.integrity_dashboard_export_excel',
                       'reports.integrity_dashboard_export_pdf'],
            blueprints=['reports'], roles_subsection='AI — pages'),
        _mi('Gross Margin Analysis', 'reports.gross_margin_dashboard_page',
            endpoints=['reports.gross_margin_dashboard_page', 'reports.gross_margin_api_data',
                       'reports.gross_margin_api_drilldown', 'reports.gross_margin_export_excel',
                       'reports.gross_margin_export_pdf'],
            blueprints=['reports'], roles_subsection='AI — pages'),
    ]),
    ('Sales', [
        _mi('Sales Order (menu)', 'sales.sales_order',
            endpoints=['sales.sales_order', 'sales.sales_order_list'],
            blueprints=['sales']),
    ]),
    ('Purchase', [
        _mi('New LPO', 'purchase.purchase_order_new',
            endpoints=list(_PURCHASE_ORDER_NEW_MENU_ITEM.get('endpoints', [])),
            blueprints=['purchase']),
        _mi('Purchase Return Request', 'purchase.purchase_return_order',
            endpoints=list(_PURCHASE_RETURN_REQUEST_MENU_ITEM.get('endpoints', [])),
            blueprints=['purchase']),
        _mi('Purchase Return Request (menu)', 'purchase.purchase_return_request_list',
            endpoints=['purchase.purchase_return_request_list', 'purchase.purchase_return_order'],
            blueprints=['purchase']),
        _mi('Stock Adjustment (menu)', 'purchase.stock_adjustment',
            endpoints=['purchase.stock_adjustment', 'purchase.stock_adjustment_list'],
            blueprints=['purchase']),
        _mi('Repacking (menu)', 'purchase.repacking',
            endpoints=['purchase.repacking', 'purchase.repacking_list'],
            blueprints=['purchase']),
        _mi('Batch / lot — operator checklist', 'purchase.batch_lot_operator_checklist',
            endpoints=['purchase.batch_lot_operator_checklist', 'purchase.batch_lot_inquiry'],
            blueprints=['purchase']),
    ]),
    ('Accounts', [
        _mi('Account Ledger', 'accounts.account_ledger_page',
            endpoints=['accounts.account_ledger_page', 'accounts.account_ledger', 'accounts.account_ledger_pdf', 'accounts.account_ledger_excel'],
            blueprints=['accounts']),
        _mi('Main account ledger', 'accounts.main_account_ledger',
            endpoints=['accounts.main_account_ledger'],
            blueprints=['accounts']),
        _mi('Supplier Ledger', 'accounts.supplier_ledger_page',
            endpoints=['accounts.supplier_ledger_page', 'accounts.supplier_ledger'],
            blueprints=['accounts']),
        _mi('Customer Ledger', 'accounts.customer_ledger_page',
            endpoints=['accounts.customer_ledger_page', 'accounts.customer_ledger'],
            blueprints=['accounts']),
        _mi('Import opening (CSV)', 'accounts.opening_balance_import',
            endpoints=['accounts.opening_balance_import', 'accounts.opening_balance_sample_csv', 'accounts.opening_balance_sample_excel'],
            blueprints=['accounts']),
        _mi('Customer opening outstanding', 'accounts.customer_opening_outstanding',
            endpoints=['accounts.customer_opening_outstanding', 'accounts.customer_opening_outstanding_sample_csv'],
            blueprints=['accounts']),
        _mi('Supplier opening outstanding', 'accounts.supplier_opening_outstanding',
            endpoints=['accounts.supplier_opening_outstanding', 'accounts.supplier_opening_outstanding_sample_csv'],
            blueprints=['accounts']),
        _mi('Account Ledger — PDF export', 'accounts.account_ledger_pdf',
            endpoints=['accounts.account_ledger_pdf'], blueprints=['accounts'], roles_visible=False),
        _mi('Account Ledger — Excel export', 'accounts.account_ledger_excel',
            endpoints=['accounts.account_ledger_excel'], blueprints=['accounts'], roles_visible=False),
        _mi('Main account ledger — PDF', 'accounts.main_account_ledger_pdf',
            endpoints=['accounts.main_account_ledger_pdf'], blueprints=['accounts'], roles_visible=False),
        _mi('Main account ledger — Excel', 'accounts.main_account_ledger_excel',
            endpoints=['accounts.main_account_ledger_excel'], blueprints=['accounts'], roles_visible=False),
        _mi('Supplier Ledger — PDF', 'accounts.supplier_ledger_pdf',
            endpoints=['accounts.supplier_ledger_pdf'], blueprints=['accounts'], roles_visible=False),
        _mi('Customer Ledger — PDF', 'accounts.customer_ledger_pdf',
            endpoints=['accounts.customer_ledger_pdf'], blueprints=['accounts'], roles_visible=False),
        _mi('Cash Flow — PDF', 'accounts.cash_flow_pdf',
            endpoints=['accounts.cash_flow_pdf'], blueprints=['accounts'], roles_visible=False),
        _mi('Cash Flow — Excel', 'accounts.cash_flow_excel',
            endpoints=['accounts.cash_flow_excel'], blueprints=['accounts'], roles_visible=False),
        _mi('Trial Balance — PDF', 'accounts.trial_balance_pdf',
            endpoints=['accounts.trial_balance_pdf'], blueprints=['accounts'], roles_visible=False),
        _mi('Trial Balance — Excel', 'accounts.trial_balance_excel',
            endpoints=['accounts.trial_balance_excel'], blueprints=['accounts'], roles_visible=False),
        _mi('Trial Balance — ledger drill-down API', 'accounts.trial_balance_ledger_api',
            endpoints=['accounts.trial_balance_ledger_api'], blueprints=['accounts'], roles_visible=False),
        _mi('Profit & Loss — PDF', 'accounts.profit_loss_pdf',
            endpoints=['accounts.profit_loss_pdf'], blueprints=['accounts'], roles_visible=False),
        _mi('Profit & Loss — Excel', 'accounts.profit_loss_excel',
            endpoints=['accounts.profit_loss_excel'], blueprints=['accounts'], roles_visible=False),
        _mi('Balance Sheet — PDF', 'accounts.balance_sheet_pdf',
            endpoints=['accounts.balance_sheet_pdf'], blueprints=['accounts'], roles_visible=False),
        _mi('Balance Sheet — Excel', 'accounts.balance_sheet_excel',
            endpoints=['accounts.balance_sheet_excel'], blueprints=['accounts'], roles_visible=False),
        _mi('Balance Sheet — ledger drill-down API', 'accounts.balance_sheet_ledger_api',
            endpoints=['accounts.balance_sheet_ledger_api'], blueprints=['accounts'], roles_visible=False),
    ]),
    ('POS', [
        _mi('POS Save Queue', 'pos_billing.pos_save_queue_page',
            endpoints=['pos_billing.pos_save_queue_page', 'pos_billing.pos_save_queue_api',
                       'pos_billing.pos_save_queue_job_detail_api'],
            blueprints=['pos_billing']),
        _mi('POS Accounts Configuration', 'pos_billing.pos_accounts_configuration_page',
            endpoints=['pos_billing.pos_accounts_configuration_page',
                       'pos_billing.pos_accounts_configuration_api_bootstrap',
                       'pos_billing.pos_accounts_configuration_api_save'],
            blueprints=['pos_billing']),
        _mi('POS Sales List', 'pos_billing.pos_sales_list_page',
            endpoints=['pos_billing.pos_sales_list_page', 'pos_billing.pos_sales_list_summary_api'],
            blueprints=['pos_billing']),
        _mi('POS Price Edited Report', 'pos_billing.pos_price_edited_report_page',
            endpoints=['pos_billing.pos_price_edited_report_page',
                       'pos_billing.pos_price_edited_report_api',
                       'pos_billing.pos_price_edited_report_export'],
            blueprints=['pos_billing']),
    ]),
]

# (subsection, sidebar label, menu_path) — order matches templates/base.html sidebar.
_SIDEBAR_ROLES_LAYOUT: List[Tuple[str, List[Tuple[Optional[str], str, str]]]] = [
    ('Home', [
        (None, 'Dashboard', 'dashboard.dashboard'),
        (None, 'Chat', 'chat.chat_page'),
    ]),
    ('Demo Sales (sample)', [
        (None, 'Sales cockpit', 'demo_sales.dashboard'),
    ]),
    ('AI', [
        (None, 'Sales AI', 'sales_ai.dashboard'),
        (None, 'Forecast cockpit', 'ai_forecast.dashboard'),
        (None, 'Sales forecast', 'ai_forecast.sales_forecast_page'),
        (None, 'Purchase forecast', 'ai_forecast.purchase_forecast_page'),
        (None, 'Smart reorder', 'ai_forecast.reorder_page'),
        (None, 'Product performance', 'ai_forecast.products_page'),
        (None, 'Supplier analysis', 'ai_forecast.suppliers_page'),
        (None, 'Customer analysis', 'ai_forecast.customers_page'),
        (None, 'AI reports', 'ai_forecast.reports_page'),
        (None, 'Smart List', 'reports.smart_list'),
        (None, 'Stock Aging', 'reports.stock_aging_report'),
        (None, 'Integrity Dashboard', 'reports.integrity_dashboard_page'),
        (None, 'Gross Margin Analysis', 'reports.gross_margin_dashboard_page'),
        (None, 'Transaction Recording Audit', 'transaction_recording_audit.viewer'),
    ]),
    ('Online', [
        (None, 'Tasveek', 'tasveek.tasveek_list'),
        (None, 'Tasveek API data', 'tasveek.tasveek_api_rawabi_data'),
    ]),
    ('Setup', [
        (None, 'Companies', 'setup.company_profile'),
        (None, 'Menu price & points', 'setup.menu_price_points'),
        (None, 'Branch / Location Master', 'setup.branch_location_master'),
        (None, 'GL dimension master', 'setup.gl_dimension_master'),
        (None, 'User Management', 'users.user_create'),
        (None, 'Transfer Approval Setup', 'purchase.stock_transfer_approval_setup'),
        (None, 'Tenants', 'tenants.tenant_list'),
        (None, 'Roles & Permissions', 'roles.roles_list'),
        (None, 'Fiscal Year Setup', 'setup.fiscal_year'),
        (None, 'Document Numbering', 'setup.document_numbering'),
        (None, 'Transaction Date Setup', 'setup.transaction_date_setup'),
        (None, 'Transaction Date — change any date (like admin)', 'setup.transaction_date_change_any'),
        (None, 'System Configuration', 'system_config.system_config_list'),
        (None, 'Promotions', 'promotions.promotions_page'),
        (None, 'New Company setup', 'setup.new_company_setup'),
        (None, 'Approval Workflow', 'setup.approval_workflow_page'),
        (None, 'General Setup', 'setup.general_setup_page'),
        (None, 'DBA — Table Locks', 'setup.dba_tools'),
    ]),
    ('PDT', [
        (None, 'PDT Roles Setup', 'pdt.pdt_roles_list'),
        (None, 'PDT User Creation', 'pdt.pdt_user_create'),
        (None, 'PDT Users', 'pdt.pdt_users_list'),
    ]),
    ('HO', [
        (None, 'Customer Creation', 'ho.customer_central'),
    ]),
    ('Master Request', [
        (None, 'Customer Request', 'ho.customer_request'),
    ]),
    ('Item Request', [
        (None, 'Item Request', 'ho.item_request'),
    ]),
    ('Itemmaster Central', [
        (None, 'Itemmaster Central', 'ho.itemmaster_central'),
        (None, 'Supplier Central', 'ho.supplier_central'),
    ]),
    ('Itemmaster Branch', [
        (None, 'Item Master', 'itemmaster.productlist'),
        (None, 'Category Master', 'itemmaster.category_master_list'),
        (None, 'Brand Master', 'itemmaster.brand_master_list'),
        (None, 'Unit of measurement', 'itemmaster.unit_of_measurement_list'),
        (None, 'Property & Origin', 'itemmaster.item_property_origin_list'),
    ]),
    ('Master', [
        (None, 'Customer', 'customer.customer_list'),
        (None, 'Employee', 'employee.employee_list'),
        (None, 'Vendor', 'supplier.supplier_list'),
        (None, 'Salesman', 'salesman.salesman_list'),
        (None, 'Route', 'route_master.route_list'),
        (None, 'Cust. category', 'customer_category.category_list'),
        (None, 'Session', 'session_master.session_list'),
        (None, 'Activity log', 'activity_log.activity_log_page'),
    ]),
    ('Plan', [
        (None, 'Missing customers', 'customer.missing_customer_recovery'),
        (None, 'My visit tasks', 'customer.missing_customer_visit_tasks'),
    ]),
    ('POS', [
        ('POS Setup', 'POS Billing', 'pos_billing.pos_billing_page'),
        ('POS Setup', 'POS Shop', 'pos_billing.pos_shop_page'),
        ('POS Setup', 'POS Verify', 'pos_billing.pos_verify_page'),
        ('POS Setup', 'POS Transactions', 'pos_billing.pos_bills_page'),
        ('POS Setup', 'POS Sales List', 'pos_billing.pos_sales_list_page'),
        ('POS Setup', 'POS Price Edited Report', 'pos_billing.pos_price_edited_report_page'),
        ('POS Setup', 'POS Save Queue', 'pos_billing.pos_save_queue_page'),
        ('POS Setup', 'POS Counter Setup', 'pos_billing.pos_counter_setup_list'),
        ('POS Setup', 'POS Tender Types', 'pos_billing.pos_tender_types_page'),
        ('POS Setup', 'POS Accounts Configuration', 'pos_billing.pos_accounts_configuration_page'),
        ('POS Setup', 'POS Counter Operations', 'pos_billing.pos_counter_operations_page'),
        ('POS Setup', 'POS Receipt Design', 'pos_billing.pos_receipt_design_page'),
    ]),
    ('Sales', [
        (None, 'Sales Order', 'sales.sales_order_list'),
        (None, 'Sales Invoice', 'sales.sales_invoice'),
        (None, 'Sales Return', 'sales.sales_return'),
        (None, 'Printer configuration', 'reports.crystal_reports'),
        (None, 'Discount & Promotions', 'promotions.promotions_page'),
        (None, 'AI Reports', 'temporary_invoices.temporary_invoices'),
    ]),
    ('Purchase', [
        (None, 'Purchase Order', 'purchase.purchase_order_list'),
        (None, 'Goods Receipt Note (GRN)', 'purchase.goods_receipt_list'),
        (None, 'Purchase Return', 'purchase.purchase_return_list'),
        (None, 'Debit Note', 'purchase.purchase_debit_note_list'),
    ]),
    ('Inventory Management', [
        (None, 'Stock Adjustment', 'purchase.stock_adjustment_list'),
        (None, 'Repacking', 'purchase.repacking_list'),
        (None, 'Store Transfer', 'purchase.stock_transfer'),
        (None, 'Inventory Valuation', 'purchase.inventory_valuation'),
        (None, 'Inventory Value Adjustment', 'purchase.inventory_value_adjustment_list'),
        (None, 'Item Journal', 'purchase.item_journal_list'),
        (None, 'Item Journal Summary', 'purchase.item_journal_summary_list'),
        (None, 'Barcode Management', 'barcode_management.barcode_management_page'),
    ]),
    ('Warehouse Management', [
        (None, 'Warehouse locations', 'warehouse.warehouse_locations'),
        (None, 'Shelf / Bin / Rack', 'warehouse.warehouse_storage_list'),
        (None, 'Bin stock & moves', 'warehouse.warehouse_bin_stock'),
        (None, 'Visual Stock Report', 'warehouse.warehouse_visual_stock'),
        (None, 'Stock verification', 'warehouse.warehouse_stock_verification'),
        (None, 'Stock Counting', 'warehouse.warehouse_stock_counting'),
        (None, 'Price Update', 'warehouse.warehouse_stock_count_price'),
        (None, 'Stock Counting (Mobile)', 'warehouse.warehouse_stock_counting_mobile'),
        (None, 'Batch / Expiry (lots)', 'purchase.batch_lot_inquiry'),
        (None, 'Batch / lot — operator checklist', 'purchase.batch_lot_operator_checklist'),
    ]),
    ('Accounts', [
        ('Accounts Masters', 'Chart of Accounts', 'accounts.chart_of_accounts_list'),
        ('Transactions', 'Journal Entry', 'accounts.journal_entry'),
        ('Transactions', 'Receipt Voucher', 'accounts.receipt_voucher'),
        ('Transactions', 'Payment Voucher', 'accounts.payment_voucher'),
        ('Transactions', 'Cash Payment Voucher', 'accounts.cash_payment_voucher'),
        ('Transactions', 'Contra Voucher', 'accounts.contra_voucher'),
        ('Receivables & Payables', 'Accounts Receivable (AR)', 'accounts.accounts_receivable'),
        ('Receivables & Payables', 'Accounts Payable (AP)', 'accounts.accounts_payable'),
        ('Receivables & Payables', 'Customer Opening Outstanding', 'accounts.customer_opening_outstanding'),
        ('Receivables & Payables', 'Supplier Opening Outstanding', 'accounts.supplier_opening_outstanding'),
        ('Banking', 'Bank Reconciliation', 'accounts.bank_reconciliation'),
        ('Banking', 'PDC Check Tracking', 'accounts.pdc_tracker'),
        ('Accounts Reports', 'Customer Ledger', 'accounts.customer_ledger_page'),
        ('Accounts Reports', 'Supplier Ledger', 'accounts.supplier_ledger_page'),
        ('Accounts Reports', 'Account Ledger', 'accounts.account_ledger_page'),
        ('Accounts Reports', 'Main account ledger', 'accounts.main_account_ledger'),
        ('Accounts Reports', 'Cash Flow', 'accounts.cash_flow'),
        ('Accounts Reports', 'Transaction accounts audit', 'accounts.transaction_audit'),
        ('Accounts Reports', 'Trial Balance', 'accounts.trial_balance'),
        ('Accounts Reports', 'Profit & Loss', 'accounts.profit_loss'),
        ('Accounts Reports', 'Balance Sheet', 'accounts.balance_sheet'),
        ('Accounts Utilities', 'Import opening (CSV)', 'accounts.opening_balance_import'),
        ('Accounts Utilities', 'Period Closing', 'accounts.period_closing_page'),
        ('Accounts Utilities', 'Tax (VAT / GST)', 'accounts.tax_accounts'),
    ]),
    ('Fixed Assets', [
        (None, 'Categories', 'fixed_assets.fa_category_list'),
        (None, 'Asset Register', 'fixed_assets.fa_asset_list'),
        (None, 'Depreciation', 'fixed_assets.fa_depreciation'),
        (None, 'Fixed Asset Sale', 'fixed_assets.fa_sale_list'),
        (None, 'Disposal', 'fixed_assets.fa_disposal_list'),
        (None, 'Transfer', 'fixed_assets.fa_transfer_list'),
    ]),
    ('Accounts Posting', [
        (None, 'Purchase Invoice', 'purchase.purchase_invoice_list'),
        (None, 'Purchase Return Posting', 'purchase.purchase_return_posting'),
        (None, 'POS Settlement Posting', 'pos_billing.pos_settlement_posting_page'),
        (None, 'Online Settlement', 'accounts.online_settlement_page'),
    ]),
]

_POS_MENU_PATHS: frozenset = frozenset(
    path for _t, entries in _SIDEBAR_ROLES_LAYOUT if _t == 'POS' for _s, _l, path in entries
)

_SIDEBAR_LAYOUT_PATHS: frozenset = frozenset(
    path for _t, entries in _SIDEBAR_ROLES_LAYOUT for _s, _l, path in entries
)

# Non-sidebar export/API paths only — not used for Roles checkboxes or sidebar visibility.
_MENU_PATH_GRANTS_IF_HAS: Dict[str, Tuple[str, ...]] = {
    'accounts.chart_of_accounts_excel': ('accounts.chart_of_accounts_list',),
    'accounts.opening_balance_sample_csv': ('accounts.opening_balance_import',),
    'accounts.opening_balance_sample_excel': ('accounts.opening_balance_import',),
    'accounts.account_ledger_pdf': ('accounts.chart_of_accounts_list', 'accounts.account_ledger_page'),
    'accounts.account_ledger_excel': ('accounts.chart_of_accounts_list', 'accounts.account_ledger_page'),
    'accounts.main_account_ledger_pdf': ('accounts.chart_of_accounts_list', 'accounts.main_account_ledger'),
    'accounts.main_account_ledger_excel': ('accounts.chart_of_accounts_list', 'accounts.main_account_ledger'),
    'accounts.supplier_ledger_pdf': ('accounts.chart_of_accounts_list', 'accounts.supplier_ledger_page'),
    'accounts.customer_ledger_pdf': ('accounts.chart_of_accounts_list', 'accounts.customer_ledger_page'),
    'accounts.cash_flow_pdf': ('accounts.cash_flow',),
    'accounts.cash_flow_excel': ('accounts.cash_flow',),
    'accounts.trial_balance_pdf': ('accounts.trial_balance',),
    'accounts.trial_balance_excel': ('accounts.trial_balance',),
    'accounts.trial_balance_ledger_api': ('accounts.trial_balance',),
    'accounts.profit_loss_pdf': ('accounts.profit_loss',),
    'accounts.profit_loss_excel': ('accounts.profit_loss',),
    'accounts.balance_sheet_pdf': ('accounts.balance_sheet',),
    'accounts.balance_sheet_excel': ('accounts.balance_sheet',),
    'accounts.balance_sheet_ledger_api': ('accounts.balance_sheet',),
}

# Fixed Assets screens inherit Chart of Accounts access until explicitly assigned in Roles.
FIXED_ASSETS_MENU_PATHS: Tuple[str, ...] = (
    'fixed_assets.fa_category_list',
    'fixed_assets.fa_asset_list',
    'fixed_assets.fa_depreciation',
    'fixed_assets.fa_sale_list',
    'fixed_assets.fa_disposal_list',
    'fixed_assets.fa_transfer_list',
)
_MENU_PATH_INHERITS_FROM: Dict[str, Tuple[str, ...]] = {
    path: ('accounts.chart_of_accounts_list',) for path in FIXED_ASSETS_MENU_PATHS
}


def _apply_menu_registry_supplements() -> None:
    for group_title, extra_items in _MENU_REGISTRY_SUPPLEMENTS:
        for group in MENU_GROUPS:
            if group.get('title') != group_title:
                continue
            items = group.setdefault('items', [])
            if not isinstance(items, list):
                break
            existing = {
                str(it.get('menu_path')).strip()
                for it in items
                if isinstance(it, dict) and it.get('menu_path')
            }
            for it in extra_items:
                mp = str(it.get('menu_path') or '').strip()
                if mp and mp not in existing:
                    items.append(dict(it))
                    existing.add(mp)
            break


_apply_menu_registry_supplements()


def _collect_strict_role_menu_paths() -> frozenset:
    """Menu paths controlled by Roles & Permissions — no cross-menu umbrella grants."""
    paths: Set[str] = set(_SIDEBAR_LAYOUT_PATHS)
    for group in MENU_GROUPS:
        for item in group.get('items') or []:
            if not isinstance(item, dict):
                continue
            mp = str(item.get('menu_path') or '').strip()
            if mp:
                paths.add(mp)
    for _title, extra_items in _MENU_REGISTRY_SUPPLEMENTS:
        for item in extra_items:
            if isinstance(item, dict):
                mp = str(item.get('menu_path') or '').strip()
                if mp:
                    paths.add(mp)
    return frozenset(paths)


_STRICT_ROLE_MENU_PATHS: frozenset = _collect_strict_role_menu_paths()


def _flatten_menu_registry() -> Dict[str, Dict[str, object]]:
    """All menu_path -> item definitions (for endpoint resolution and roles UI)."""
    out: Dict[str, Dict[str, object]] = {}
    for group in MENU_GROUPS:
        for raw in group.get('items', []) or []:
            if not isinstance(raw, dict):
                continue
            mp = str(raw.get('menu_path') or '').strip()
            if mp:
                out[mp] = dict(raw)
    return out


def _item_roles_visible(item: Dict[str, object]) -> bool:
    if item.get('roles_visible') is False:
        return False
    sub = str(item.get('roles_subsection') or '')
    if 'exports' in sub.lower():
        return False
    return True


def _roles_menu_item(
    registry: Dict[str, Dict[str, object]],
    *,
    subsection: Optional[str],
    label: str,
    menu_path: str,
) -> Optional[Dict[str, object]]:
    path = (menu_path or '').strip()
    if not path:
        return None
    base = dict(registry.get(path) or {})
    if base and not _item_roles_visible(base):
        return None
    item: Dict[str, object] = {
        'label': label,
        'menu_path': path,
    }
    if base.get('endpoints'):
        item['endpoints'] = list(base.get('endpoints') or [])
    else:
        item['endpoints'] = [path]
    if base.get('blueprints'):
        item['blueprints'] = list(base.get('blueprints') or [])
    if subsection:
        item['roles_subsection'] = subsection
    return item


def _append_registry_group_items(
    groups: List[Dict[str, object]],
    used_paths: Set[str],
    registry: Dict[str, Dict[str, object]],
    group_title: str,
) -> None:
    for group in MENU_GROUPS:
        if group.get('title') != group_title:
            continue
        items: List[Dict[str, object]] = []
        for raw in group.get('items', []) or []:
            if not isinstance(raw, dict):
                continue
            mp = str(raw.get('menu_path') or '').strip()
            if not mp or mp in used_paths or mp in _SIDEBAR_LAYOUT_PATHS:
                continue
            if mp in _POS_MENU_PATHS:
                continue
            if not _item_roles_visible(raw):
                continue
            items.append(dict(raw))
            used_paths.add(mp)
        if items:
            groups.append({'title': group_title, 'items': items})
        break


def _build_sidebar_menu_groups_for_roles() -> List[Dict[str, object]]:
    """Menu groups for Roles & Permissions — mirrors sidebar order and labels."""
    registry = _flatten_menu_registry()
    used_paths: Set[str] = set()
    groups: List[Dict[str, object]] = []
    for section_title, entries in _SIDEBAR_ROLES_LAYOUT:
        items: List[Dict[str, object]] = []
        for subsection, label, menu_path in entries:
            if menu_path in used_paths:
                continue
            built = _roles_menu_item(
                registry,
                subsection=subsection,
                label=label,
                menu_path=menu_path,
            )
            if not built:
                continue
            items.append(built)
            used_paths.add(menu_path)
        if items:
            groups.append({'title': section_title, 'items': items})
    for extra_title in ('Reports & Analytics', 'Utilities', 'Notifications'):
        _append_registry_group_items(groups, used_paths, registry, extra_title)
    return groups


# Legacy rows may use old menu_path values; map to current registry paths for grants.
_LEGACY_MENU_PATH_ALIASES: Dict[str, str] = {
    'transaction_recording_audit.dashboard': 'transaction_recording_audit.viewer',
    'transaction_recording_audit.replay': 'transaction_recording_audit.viewer',
    'transaction_recording_audit.serve_files': 'transaction_recording_audit.viewer',
}


def expand_role_permission_paths(paths: List[str]) -> List[str]:
    """Normalize stored role_permissions paths (legacy aliases + canonical)."""
    out: List[str] = []
    seen: Set[str] = set()
    for raw in paths or []:
        p = str(raw or '').strip()
        if not p:
            continue
        canon = _LEGACY_MENU_PATH_ALIASES.get(p, p)
        for candidate in (p, canon):
            if candidate and candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
    return out


# Extra API permission keys granted when an ERP role menu is checked (mobile JWT gates).
_MOBILE_API_PERMISSION_ALIASES: Dict[str, Tuple[str, ...]] = {
    'warehouse.warehouse_stock_counting': (
        'warehouse.warehouse_stock_counting_mobile',
        'itemmaster.productlist',
    ),
    'warehouse.warehouse_stock_counting_mobile': (
        'warehouse.warehouse_stock_counting',
        'itemmaster.productlist',
    ),
    'warehouse.warehouse_stock_verification': ('itemmaster.productlist',),
    'purchase.stock_adjustment_list': ('itemmaster.productlist',),
    'purchase.inventory_value_adjustment_list': ('itemmaster.productlist',),
    'purchase.purchase_order_new': ('purchase.purchase_order_add',),
    'purchase.purchase_order_edit': ('purchase.purchase_order_add',),
    'purchase.purchase_order_list': ('purchase.purchase_order_edit',),
    'purchase.purchase_order_add': (
        'purchase.purchase_order_new',
        'purchase.purchase_order_edit',
    ),
}


def expand_mobile_api_permission_aliases(paths: List[str]) -> List[str]:
    """Expand role menu paths for Nexa mobile API ``require_permission`` checks."""
    base = expand_role_permission_paths(paths)
    out: List[str] = []
    seen: Set[str] = set()
    for raw in base:
        p = str(raw or '').strip()
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
        for alias in MOBILE_PERMISSION_API_ALIASES.get(p, ()):
            if alias and alias not in seen:
                seen.add(alias)
                out.append(alias)
        for alias in _MOBILE_API_PERMISSION_ALIASES.get(p, ()):
            if alias not in seen:
                seen.add(alias)
                out.append(alias)
    return out


# Mobile app drawer — must stay aligned with ``flutter_app`` inventory shell labels.
# Each item is visible when ``is_menu_path_allowed`` passes for any listed ``menu_paths``.
MOBILE_APP_MENU_SECTIONS: List[Dict[str, object]] = [
    {
        'section': None,
        'items': [
            {'id': 'dashboard', 'label': 'Dashboard', 'nav': 'Dashboard',
             'menu_paths': ['dashboard.dashboard']},
        ],
    },
    {
        'section': 'INVENTORY',
        'items': [
            {'id': 'goods_receiving', 'label': 'Goods Receiving', 'nav': 'Goods Receiving',
             'menu_paths': ['purchase.purchase_order_list', 'purchase.purchase_order_new', 'purchase.purchase_order_edit']},
            {'id': 'grn', 'label': 'GRN', 'nav': 'GRN',
             'menu_paths': ['purchase.goods_receipt_list', 'purchase.purchase_order_list']},
            {'id': 'stock_transfer', 'label': 'Stock Transfer', 'nav': 'Stock Transfer',
             'menu_paths': ['purchase.stock_transfer']},
            {'id': 'stock_return', 'label': 'Stock Return', 'nav': 'Stock Return',
             'menu_paths': ['purchase.purchase_return_list']},
            {'id': 'stock_adjustment', 'label': 'Stock Adjustment', 'nav': 'Stock Adjustment',
             'menu_paths': ['purchase.stock_adjustment_list']},
            {'id': 'stock_counting', 'label': 'Stock Counting', 'nav': 'Stock Counting',
             'menu_paths': [
                 'warehouse.warehouse_stock_counting',
                 'warehouse.warehouse_stock_counting_mobile',
                 'warehouse.warehouse_stock_verification',
             ]},
            {'id': 'barcode_scanning', 'label': 'Barcode Scanning', 'nav': 'Barcode Scanning',
             'menu_paths': ['barcode_management.barcode_management_page']},
            {'id': 'stock_lookup', 'label': 'Stock Lookup', 'nav': 'Stock Lookup',
             'menu_paths': ['itemmaster.productlist']},
        ],
    },
    {
        'section': 'SALES',
        'items': [
            {'id': 'sales_order', 'label': 'Sales Order', 'nav': 'Sales Order',
             'menu_paths': ['sales.sales_order_list', 'sales.sales_order']},
            {'id': 'sales', 'label': 'Sales', 'nav': 'Sales',
             'menu_paths': ['sales.sales_invoice']},
            {'id': 'sales_return', 'label': 'Sales Return', 'nav': 'Sales Return',
             'menu_paths': ['sales.sales_return']},
        ],
    },
    {
        'section': 'ACCOUNTS',
        'items': [
            {'id': 'customer_ledger', 'label': 'Customer Ledger', 'nav': 'Customer Ledger',
             'menu_paths': ['accounts.customer_ledger_page', 'mobile.customer_ledger']},
            {'id': 'supplier_ledger', 'label': 'Supplier Ledger', 'nav': 'Supplier Ledger',
             'menu_paths': ['accounts.supplier_ledger_page', 'mobile.supplier_ledger']},
            {'id': 'journal_entry', 'label': 'Journal Entry', 'nav': 'Journal Entry',
             'menu_paths': ['accounts.journal_entry', 'mobile.journal_entry']},
            {'id': 'accounts_receivable', 'label': 'Accounts Receivable', 'nav': 'Accounts Receivable',
             'menu_paths': ['accounts.accounts_receivable', 'mobile.accounts_receivable']},
            {'id': 'accounts_payable', 'label': 'Accounts Payable', 'nav': 'Accounts Payable',
             'menu_paths': ['accounts.accounts_payable', 'mobile.accounts_payable']},
            {'id': 'cash_payment_voucher', 'label': 'Cash Payment Voucher', 'nav': 'Cash Payment Voucher',
             'menu_paths': [
                 'accounts.cash_payment_voucher',
                 'accounts.cash_payment_voucher_list',
                 'mobile.cash_payment_voucher',
             ]},
            {'id': 'trial_balance', 'label': 'Trial Balance', 'nav': 'Trial Balance',
             'menu_paths': ['accounts.trial_balance', 'mobile.trial_balance']},
            {'id': 'profit_loss', 'label': 'Profit & Loss', 'nav': 'Profit & Loss',
             'menu_paths': ['accounts.profit_loss', 'mobile.profit_loss']},
            {'id': 'balance_sheet', 'label': 'Balance Sheet', 'nav': 'Balance Sheet',
             'menu_paths': ['accounts.balance_sheet', 'mobile.balance_sheet']},
        ],
    },
    {
        'section': 'MASTERS',
        'items': [
            {'id': 'customers', 'label': 'Customers', 'nav': 'Customers',
             'menu_paths': [
                 'customer.customer_list',
                 'customer.customer_create',
                 'mobile.customers',
             ]},
            {'id': 'items', 'label': 'Items', 'nav': 'Items',
             'menu_paths': [
                 'itemmaster.productlist',
                 'itemmaster.itemmaster',
                 'itemmaster.itemmaster_save',
                 'mobile.items',
             ]},
            {'id': 'warehouses', 'label': 'Warehouses', 'nav': 'Warehouses',
             'menu_paths': ['warehouse.warehouse_locations', 'warehouse.warehouse_storage_list']},
            {'id': 'suppliers', 'label': 'Suppliers', 'nav': 'Suppliers',
             'menu_paths': [
                 'supplier.supplier_list',
                 'supplier.supplier_create',
                 'mobile.suppliers',
             ]},
        ],
    },
    {
        'section': 'REPORTS',
        'items': [
            {'id': 'stock_ledger', 'label': 'Stock Ledger', 'nav': 'Stock Ledger',
             'menu_paths': ['reports.stock_report', 'warehouse.warehouse_visual_stock']},
            {'id': 'stock_summary', 'label': 'Stock Summary', 'nav': 'Stock Summary',
             'menu_paths': ['reports.stock_report', 'purchase.inventory_valuation']},
            {'id': 'inventory_history', 'label': 'Inventory History', 'nav': 'Inventory History',
             'menu_paths': ['purchase.item_journal_list', 'reports.stock_report']},
            {'id': 'business_summary', 'label': 'Business Summary', 'nav': 'Business Summary',
             'menu_paths': ['business_summary.dashboard']},
            {'id': 'sales_reports', 'label': 'Sales Reports', 'nav': 'Sales Reports',
             'menu_paths': ['sales_summary.sales_summary', 'reports.sales_details', 'reports.margin_report']},
        ],
    },
    {
        'section': None,
        'items': [
            {'id': 'settings', 'label': 'Settings', 'nav': 'Settings',
             'menu_paths': ['mobile.settings']},
        ],
    },
]


def resolve_mobile_app_menus(
    menu_permissions: Optional[List[str]],
    *,
    allow_all: bool = False,
) -> List[Dict[str, object]]:
    """Build mobile drawer menu for JWT login (same rules as ERP ``has_menu_permission``)."""
    sections_out: List[Dict[str, object]] = []
    for block in MOBILE_APP_MENU_SECTIONS:
        section_title = block.get('section')
        visible_items: List[Dict[str, object]] = []
        for raw in block.get('items') or []:
            if not isinstance(raw, dict):
                continue
            paths = [str(p).strip() for p in (raw.get('menu_paths') or []) if str(p).strip()]
            if allow_all or not paths:
                visible_items.append({
                    'id': raw.get('id'),
                    'label': raw.get('label'),
                    'nav': raw.get('nav'),
                })
                continue
            if any(is_menu_path_allowed(p, menu_permissions) for p in paths):
                visible_items.append({
                    'id': raw.get('id'),
                    'label': raw.get('label'),
                    'nav': raw.get('nav'),
                })
        if visible_items:
            sections_out.append({
                'section': section_title,
                'items': visible_items,
            })
    return sections_out


# Nexa Mobile app (Flutter) — checkboxes on Roles & Permissions → Mobile tab.
_MOBILE_MENU_LAYOUT: List[Tuple[str, List[Tuple[Optional[str], str, str]]]] = [
    ('Home', [
        (None, 'Dashboard', 'mobile.dashboard'),
    ]),
    ('Inventory', [
        (None, 'Goods Receiving', 'mobile.goods_receiving'),
        (None, 'GRN', 'mobile.grn'),
        (None, 'Stock Transfer', 'mobile.stock_transfer'),
        (None, 'Stock Return', 'mobile.stock_return'),
        (None, 'Stock Adjustment', 'mobile.stock_adjustment'),
        (None, 'Stock Counting', 'mobile.stock_counting'),
        (None, 'Barcode Scanning', 'mobile.barcode_scanning'),
        (None, 'Stock Lookup', 'mobile.stock_lookup'),
    ]),
    ('Sales', [
        (None, 'Sales Order', 'mobile.sales_order'),
        (None, 'Sales', 'mobile.sales'),
        (None, 'Sales Return', 'mobile.sales_return'),
    ]),
    ('Accounts', [
        (None, 'Customer Ledger', 'mobile.customer_ledger'),
        (None, 'Supplier Ledger', 'mobile.supplier_ledger'),
        (None, 'Journal Entry', 'mobile.journal_entry'),
        (None, 'Accounts Receivable', 'mobile.accounts_receivable'),
        (None, 'Accounts Payable', 'mobile.accounts_payable'),
        (None, 'Cash Payment Voucher', 'mobile.cash_payment_voucher'),
        (None, 'Trial Balance', 'mobile.trial_balance'),
        (None, 'Profit & Loss', 'mobile.profit_loss'),
        (None, 'Balance Sheet', 'mobile.balance_sheet'),
    ]),
    ('Masters', [
        (None, 'Customers', 'mobile.customers'),
        (None, 'Items', 'mobile.items'),
        (None, 'Warehouses', 'mobile.warehouses'),
        (None, 'Suppliers', 'mobile.suppliers'),
    ]),
    ('Reports', [
        (None, 'Stock Ledger', 'mobile.stock_ledger'),
        (None, 'Stock Summary', 'mobile.stock_summary'),
        (None, 'Inventory History', 'mobile.inventory_history'),
        (None, 'Business Summary', 'mobile.business_summary'),
        (None, 'Sales Reports', 'mobile.sales_reports'),
    ]),
    ('App', [
        (None, 'Settings', 'mobile.settings'),
    ]),
]

MOBILE_MENU_PATHS: frozenset = frozenset(
    path for _title, entries in _MOBILE_MENU_LAYOUT for _sub, _label, path in entries
)

# When a mobile menu is granted, these ERP/API keys are also included in the JWT.
MOBILE_PERMISSION_API_ALIASES: Dict[str, Tuple[str, ...]] = {
    'mobile.dashboard': ('dashboard.dashboard',),
    'mobile.goods_receiving': (
        'purchase.purchase_order_list',
        'purchase.purchase_order_add',
        'purchase.purchase_order_new',
        'purchase.purchase_order_edit',
    ),
    'mobile.grn': ('purchase.goods_receipt_list', 'purchase.purchase_order_list'),
    'mobile.stock_transfer': ('purchase.stock_transfer',),
    'mobile.stock_return': ('purchase.purchase_return_list',),
    'mobile.stock_adjustment': ('purchase.stock_adjustment_list',),
    'mobile.stock_counting': (
        'warehouse.warehouse_stock_counting',
        'warehouse.warehouse_stock_counting_mobile',
        'warehouse.warehouse_stock_verification',
        'itemmaster.productlist',
    ),
    'mobile.barcode_scanning': ('barcode_management.barcode_management_page',),
    'mobile.stock_lookup': ('itemmaster.productlist',),
    'mobile.sales_order': ('sales.sales_order_list', 'sales.sales_order'),
    'mobile.sales': ('sales.sales_invoice',),
    'mobile.sales_return': ('sales.sales_return',),
    'mobile.sales_reports': (
        'sales_summary.sales_summary',
        'reports.sales_details',
        'reports.margin_report',
    ),
    'mobile.customer_ledger': ('accounts.customer_ledger_page',),
    'mobile.supplier_ledger': ('accounts.supplier_ledger_page',),
    'mobile.journal_entry': ('accounts.journal_entry',),
    'mobile.accounts_receivable': ('accounts.accounts_receivable',),
    'mobile.accounts_payable': ('accounts.accounts_payable',),
    'mobile.cash_payment_voucher': (
        'accounts.cash_payment_voucher',
        'accounts.cash_payment_voucher_list',
        'accounts.cash_payment_voucher_pdf',
    ),
    'mobile.trial_balance': (
        'accounts.trial_balance',
        'accounts.trial_balance_pdf',
    ),
    'mobile.profit_loss': (
        'accounts.profit_loss',
        'accounts.profit_loss_pdf',
    ),
    'mobile.balance_sheet': (
        'accounts.balance_sheet',
        'accounts.balance_sheet_pdf',
    ),
    'mobile.customers': (
        'customer.customer_list',
        'customer.customer_create',
        'customer.customer_edit',
    ),
    'mobile.items': (
        'itemmaster.productlist',
        'itemmaster.itemmaster',
        'itemmaster.itemmaster_save',
    ),
    'mobile.warehouses': ('warehouse.warehouse_locations', 'warehouse.warehouse_storage_list'),
    'mobile.suppliers': (
        'supplier.supplier_list',
        'supplier.supplier_create',
        'supplier.supplier_edit',
    ),
    'mobile.stock_ledger': ('reports.stock_report', 'warehouse.warehouse_visual_stock'),
    'mobile.stock_summary': ('reports.stock_report', 'purchase.inventory_valuation'),
    'mobile.inventory_history': ('purchase.item_journal_list', 'reports.stock_report'),
    'mobile.business_summary': (
        'business_summary.dashboard',
        'business_summary.api_dashboard',
    ),
    'mobile.settings': (),
}


def get_mobile_menu_groups() -> List[Dict[str, object]]:
    """Menu tree for Roles & Permissions → Mobile tab (Flutter app menus)."""
    groups: List[Dict[str, object]] = []
    for section_title, entries in _MOBILE_MENU_LAYOUT:
        items: List[Dict[str, object]] = []
        for subsection, label, menu_path in entries:
            built: Dict[str, object] = {'label': label, 'menu_path': menu_path}
            if subsection:
                built['roles_subsection'] = subsection
            items.append(built)
        if items:
            groups.append({'title': section_title, 'items': items})
    return groups


def get_role_editor_menu_paths() -> Set[str]:
    """Menu paths shown as checkboxes in Roles & Permissions (ERP + Mobile tabs)."""
    return set(_STRICT_ROLE_MENU_PATHS) | set(MOBILE_MENU_PATHS)


def effective_role_menu_paths(menu_permissions: Optional[List[str]]) -> Set[str]:
    """
    Role menu paths plus ERP paths implied by granted mobile.* checkboxes
    (e.g. mobile.sales_return also grants sales.sales_return for web ERP).
    """
    perms: Set[str] = set()
    for raw in menu_permissions or []:
        p = str(raw or '').strip()
        if not p:
            continue
        perms.add(p)
        if p.startswith('mobile.'):
            for erp_path in MOBILE_PERMISSION_API_ALIASES.get(p, ()):
                if erp_path:
                    perms.add(erp_path)
    return perms


def is_menu_path_allowed(menu_path: str, menu_permissions: Optional[List[str]]) -> bool:
    """
    True if menu_path is granted for this role.
    ERP sidebar paths: exact checkbox, or linked mobile.* checkbox.
    Export/API helper paths may inherit from their parent screen permission.
    """
    path = (menu_path or '').strip()
    if not path:
        return False
    perms = effective_role_menu_paths(menu_permissions)
    if path in perms:
        return True
    for parent in _MENU_PATH_INHERITS_FROM.get(path, ()):
        if parent in perms:
            return True
    if path in _STRICT_ROLE_MENU_PATHS:
        return False
    for parent in _MENU_PATH_GRANTS_IF_HAS.get(path, ()):
        if parent in perms:
            return True
    return False


def get_menu_groups() -> List[Dict[str, object]]:
    """Role editor menu tree (sidebar-aligned). Full registry remains in MENU_GROUPS."""
    return _build_sidebar_menu_groups_for_roles()


# Handheld (PDT) roles: only stock-count mobile + password change (no ERP menus).
PDT_ROLE_ID_PREFIX = 'PDT_'
PDT_MENU_PATHS: frozenset = frozenset({
    'warehouse.warehouse_stock_counting',
    'warehouse.warehouse_stock_counting_mobile',
    'auth.change_password',
})
PDT_MENU_ITEMS: List[Dict[str, object]] = [
    {
        'label': 'Stock Counting (Mobile)',
        'menu_path': 'warehouse.warehouse_stock_counting_mobile',
        'endpoints': [
            'warehouse.warehouse_stock_counting_mobile_home',
            'warehouse.warehouse_stock_counting_mobile_new',
            'warehouse.warehouse_stock_counting_mobile_scan',
            'warehouse.api_stock_count_list',
            'warehouse.api_stock_count_get',
            'warehouse.api_stock_count_pdt_upload',
            'warehouse.api_stock_count_add_line',
            'warehouse.api_stock_count_post',
            'warehouse.api_stock_count_cancel',
            'warehouse.api_stock_count_delete',
        ],
    },
    {
        'label': 'Stock Counting',
        'menu_path': 'warehouse.warehouse_stock_counting',
        'endpoints': [
            'warehouse.warehouse_stock_counting_list',
            'warehouse.warehouse_stock_counting_new',
            'warehouse.warehouse_stock_counting_detail',
            'warehouse.warehouse_stock_counting_mobile_redirect',
            'warehouse.warehouse_stock_counting_mobile_scan_redirect',
            'warehouse.api_stock_count_list',
            'warehouse.api_stock_count_get',
            'warehouse.api_stock_count_pdt_upload',
            'warehouse.api_stock_count_add_line',
            'warehouse.api_stock_count_edit_line',
            'warehouse.api_stock_count_delete_line',
            'warehouse.api_stock_count_post',
            'warehouse.api_stock_count_cancel',
            'warehouse.api_stock_count_delete',
        ],
    },
    {
        'label': 'Change password',
        'menu_path': 'auth.change_password',
        'endpoints': ['auth.change_password', 'auth.logout', 'auth.login'],
    },
]


def get_pdt_menu_groups() -> List[Dict[str, object]]:
    """Menu groups shown on PDT Roles Setup (subset of ERP permissions)."""
    return [{'title': 'PDT device access', 'items': list(PDT_MENU_ITEMS)}]


def is_pdt_menu_path(menu_path: str) -> bool:
    return (menu_path or '').strip() in PDT_MENU_PATHS


def validate_pdt_menu_permissions(menu_permissions: Optional[List[str]]) -> List[str]:
    """Keep only allowed paths; raise if any invalid path was submitted."""
    allowed = set(PDT_MENU_PATHS)
    out: List[str] = []
    invalid: List[str] = []
    for raw in menu_permissions or []:
        p = (raw or '').strip()
        if not p:
            continue
        if p in allowed:
            if p not in out:
                out.append(p)
        else:
            invalid.append(p)
    if invalid:
        raise ValueError(f'PDT roles may only include: {", ".join(sorted(allowed))}.')
    return out


def is_pdt_role_id(role_id: str) -> bool:
    from db.pdt_auth import PDT_ROLE_ID_PREFIX as _pfx
    return str(role_id or '').strip().upper().startswith(_pfx)


def role_is_pdt_role(role_id: str) -> bool:
    """True if role exists in pdt_roles table."""
    from db.pdt_auth import pdt_role_exists
    return pdt_role_exists((role_id or '').strip())


def get_pdt_roles() -> List[Dict[str, object]]:
    from db.pdt_auth import get_all_pdt_roles
    return get_all_pdt_roles() or []


def get_next_pdt_role_id() -> str:
    from db.pdt_auth import get_next_pdt_role_id as _next
    return _next()


def ensure_default_pdt_operator_role() -> None:
    from db.pdt_auth import ensure_default_pdt_operator_role as _seed
    _seed()

_MENU_PATH_INDEX: Dict[str, Dict[str, object]] = {}
for _group in MENU_GROUPS:
    for _item in _group.get('items', []):
        if isinstance(_item, dict) and _item.get('menu_path'):
            _MENU_PATH_INDEX[str(_item['menu_path'])] = _item

_MENU_ICON_BY_PATH: Dict[str, str] = {
    'dashboard.dashboard': 'bi-speedometer2',
    'chat.chat_page': 'bi-chat-dots',
    'pos_billing.pos_billing_page': 'bi-cart-check',
    'pos_billing.pos_shop_page': 'bi-shop',
    'pos_billing.pos_verify_page': 'bi-patch-check',
    'pos_billing.pos_bills_page': 'bi-receipt',
    'pos_billing.pos_sales_list_page': 'bi-list-ul',
    'pos_billing.pos_price_edited_report_page': 'bi-pencil-square',
    'pos_billing.pos_settlement_posting_page': 'bi-calculator',
    'pos_billing.pos_counter_setup_list': 'bi-pc-display',
    'pos_billing.pos_tender_types_page': 'bi-credit-card',
    'pos_billing.pos_counter_operations_page': 'bi-gear',
    'sales.sales_invoice': 'bi-file-earmark-text',
    'sales.sales_order_list': 'bi-bag-check',
    'sales.sales_return': 'bi-arrow-return-left',
    'purchase.purchase_order_list': 'bi-bag-plus',
    'purchase.goods_receipt_list': 'bi-box-seam',
    'purchase.purchase_return_list': 'bi-arrow-counterclockwise',
    'purchase.stock_adjustment_list': 'bi-sliders',
    'purchase.inventory_value_adjustment_list': 'bi-currency-exchange',
    'purchase.item_journal_list': 'bi-journal-text',
    'purchase.item_journal_summary_list': 'bi-journals',
    'purchase.purchase_verification': 'bi-shield-check',
    'purchase.purchase_change_log': 'bi-clock-history',
    'purchase.stock_transfer': 'bi-truck',
    'customer.customer_list': 'bi-people',
    'supplier.supplier_list': 'bi-building',
    'salesman.salesman_list': 'bi-person-badge',
    'itemmaster.productlist': 'bi-box',
    'accounts.chart_of_accounts_list': 'bi-diagram-3',
    'fixed_assets.fa_category_list': 'bi-tags',
    'fixed_assets.fa_asset_list': 'bi-building-gear',
    'fixed_assets.fa_depreciation': 'bi-graph-down-arrow',
    'fixed_assets.fa_sale_list': 'bi-cash-coin',
    'fixed_assets.fa_disposal_list': 'bi-trash3',
    'fixed_assets.fa_transfer_list': 'bi-arrow-left-right',
    'accounts.journal_entry': 'bi-journal-plus',
    'accounts.receipt_voucher': 'bi-box-arrow-in-down',
    'accounts.payment_voucher': 'bi-box-arrow-up-right',
    'accounts.contra_voucher': 'bi-arrow-left-right',
    'accounts.period_closing_page': 'bi-calendar2-check',
    'accounts.trial_balance': 'bi-bar-chart-line',
    'accounts.profit_loss': 'bi-graph-up-arrow',
    'accounts.balance_sheet': 'bi-layout-three-columns',
    'accounts.accounts_payable': 'bi-wallet2',
    'accounts.accounts_receivable': 'bi-cash-coin',
    'warehouse.warehouse_bin_stock': 'bi-grid-3x3-gap',
    'warehouse.warehouse_stock_counting': 'bi-clipboard-data',
    'reports.crystal_reports': 'bi-bar-chart',
    'business_summary.dashboard': 'bi-graph-up',
    'users.user_create': 'bi-person-gear',
    'roles.roles_list': 'bi-shield-lock',
    'pdt.pdt_roles_list': 'bi-phone-flip',
    'pdt.pdt_user_create': 'bi-person-plus',
}

def get_menu_item_by_path(menu_path: str) -> Optional[Dict[str, object]]:
    return _MENU_PATH_INDEX.get((menu_path or '').strip())

def icon_for_menu_path(menu_path: str) -> str:
    path = (menu_path or '').strip()
    if path in _MENU_ICON_BY_PATH:
        return _MENU_ICON_BY_PATH[path]
    if path.startswith('pos_billing.'):
        return 'bi-cash-register'
    if path.startswith('sales.'):
        return 'bi-receipt'
    if path.startswith('purchase.'):
        return 'bi-bag'
    if path.startswith('accounts.'):
        return 'bi-journal-text'
    if path.startswith('warehouse.'):
        return 'bi-boxes'
    if path.startswith('reports.'):
        return 'bi-graph-up'
    if path.startswith('ho.'):
        return 'bi-building-gear'
    if path.startswith('itemmaster.'):
        return 'bi-box-seam'
    return 'bi-grid'

def resolve_quick_access_items(
    quick_access_paths: List[str],
    menu_permissions: List[str],
    *,
    allow_all: bool = False,
) -> List[Dict[str, object]]:
    """Build top-bar quick access entries from role config and allowed menus."""
    allowed = set(menu_permissions or [])
    items: List[Dict[str, object]] = []
    seen: set = set()
    for path in quick_access_paths or []:
        p = (path or '').strip()
        if not p or p in seen:
            continue
        if not allow_all and p not in allowed:
            continue
        menu_item = get_menu_item_by_path(p)
        if not menu_item:
            continue
        endpoints = menu_item.get('endpoints') or []
        endpoint = p
        if p in endpoints:
            endpoint = p
        elif endpoints:
            suffix = p.rsplit('.', 1)[-1]
            for ep in endpoints:
                ep_str = str(ep)
                if ep_str == p or ep_str.endswith('.' + suffix):
                    endpoint = ep_str
                    break
            else:
                # menu_path often differs from the page route (e.g. setup.transaction_date_setup).
                endpoint = str(endpoints[0])
        items.append({
            'menu_path': p,
            'label': str(menu_item.get('label') or p),
            'endpoint': endpoint,
            'icon': str(menu_item.get('icon') or icon_for_menu_path(p)),
        })
        seen.add(p)
    return items

def resolve_permission_targets(menu_paths: List[str]) -> Tuple[Set[str], Set[str]]:
    allowed_endpoints: Set[str] = set()
    allowed_blueprints: Set[str] = set()
    menu_set = effective_role_menu_paths(menu_paths)
    for group in MENU_GROUPS:
        for item in group.get('items', []):
            menu_path = item.get('menu_path')
            if menu_path in menu_set:
                allowed_endpoints.update(item.get('endpoints', []))
                allowed_blueprints.update(item.get('blueprints', []))
    if menu_set.intersection({'sales.sales_invoice', 'sales.sales_return', 'sales.sales_order', 'sales.sales_order_list'}):
        allowed_blueprints.add('sales')
    if 'utilities.db_structure_sync' in menu_set:
        allowed_endpoints.add('db_sync.new_company_setup_page')
        allowed_blueprints.add('db_sync')
    if menu_set.intersection({'purchase.purchase_order_list', 'purchase.purchase_order_new'}):
        allowed_endpoints.update(_PURCHASE_ORDER_LIST_MENU_ITEM.get('endpoints', []))
        allowed_endpoints.update(_PURCHASE_ORDER_NEW_MENU_ITEM.get('endpoints', []))
        allowed_blueprints.add('purchase')
    if 'purchase.inventory_valuation' in menu_set:
        allowed_endpoints.update({
            'purchase.inventory_valuation',
            'purchase.inventory_valuation_api',
            'purchase.inventory_valuation_export_csv',
            'purchase.inventory_valuation_export_pdf',
        })
        allowed_blueprints.add('purchase')
    if menu_set.intersection({'purchase.purchase_return_list', 'purchase.purchase_return_order', 'purchase.purchase_return_request_list'}):
        allowed_endpoints.update(_PURCHASE_RETURN_REQUEST_MENU_ITEM.get('endpoints', []))
        allowed_endpoints.add('purchase.purchase_return_posting')
        allowed_endpoints.add('purchase.api_purchase_return_post')
        allowed_endpoints.add('purchase.api_pr_post_selected')
        allowed_endpoints.add('purchase.purchase_return_new')
        allowed_endpoints.add('purchase.purchase_return_query')
        allowed_endpoints.add('purchase.api_purchase_return_save')
        allowed_endpoints.add('purchase.api_purchase_return_next_no')
        allowed_endpoints.add('purchase.api_purchase_return_load_from_order')
        allowed_endpoints.add('purchase.api_purchase_return_load_from_grn')
        allowed_endpoints.add('purchase.api_purchase_return_grn_picker')
        allowed_blueprints.add('purchase')
    if menu_set.intersection({
        'customer.customer_list',
        'customer.customer_create',
        'customer.customer_edit',
        'customer.customer_view',
    }):
        allowed_endpoints.update({
            'customer.customer_list_api_items',
            'customer.customer_list_api_filter_options',
            'customer.api_salesman_list',
            'customer.api_category_list',
            'customer.api_route_list',
            'customer.api_employee_list',
        })
    return (allowed_endpoints, allowed_blueprints)

def get_ho_seed_roles() -> List[Dict[str, object]]:
    """
    Default auth-DB roles for HO screens and Master Request (idempotent installs).
    Assign via User Management (role_id on login_users).
    """
    _all_ho_menus = ['ho.itemmaster_central', 'ho.supplier_central', 'ho.item_request', 'ho.customer_request', 'ho.customer_central']
    return [{'role_id': 'HO_ITEMMASTER', 'role_name': 'HO — Itemmaster Central', 'description': 'Manage items at HQ (HO itemmaster-central).', 'menu_permissions': ['ho.itemmaster_central']}, {'role_id': 'HO_SUPPLIER_CENTRAL', 'role_name': 'HO — Supplier Central', 'description': 'Create and sync suppliers centrally at HQ.', 'menu_permissions': ['ho.supplier_central']}, {'role_id': 'HO_ITEM_REQUEST', 'role_name': 'HO — Item Request', 'description': 'Submit and convert branch item requests.', 'menu_permissions': ['ho.item_request']}, {'role_id': 'HO_CUSTOMER_REQUEST', 'role_name': 'HO — Customer Request', 'description': 'Review, approve/reject branch customer onboarding requests.', 'menu_permissions': ['ho.customer_request']}, {'role_id': 'HO_CUSTOMER_CENTRAL', 'role_name': 'HO — Customer Creation', 'description': 'Create/maintain customers centrally at HQ (customer-central).', 'menu_permissions': ['ho.customer_central']}, {'role_id': 'HO_FULL', 'role_name': 'HO — Full access', 'description': 'HO (Itemmaster + Customer Creation) and Master Request (Item + Customer Request).', 'menu_permissions': list(_all_ho_menus)}]
