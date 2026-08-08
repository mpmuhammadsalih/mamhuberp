# Static assets (`addon_name/static/`)

Same idea as **Odoo addon `static/`**: CSS/JS/images shipped with the module.

**Served by Flask** through the addon Blueprint’s `static_folder`:

- URL prefix: `/demo-sales/static/...` (blueprint `url_prefix` + `static_url_path`)
- In Jinja: `{{ url_for('demo_sales.static', filename='css/demo_sales.css') }}`

Keep names scoped (e.g. `demo_sales.css`, `demo_sales.js`) so they never clash with global `static/css/style.css`.
