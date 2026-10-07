# Views (templates) — `demo_sales`

Odoo analogy: XML views define UI; here **Jinja** replaces XML.

## Rules

| Rule | Reason |
|------|--------|
| One logical screen → one `.html` under `views/templates/demo_sales/` | Matches Odoo “one view per xml id”, easier git history |
| Extend shared chrome via `{% extends "base.html" %}` | One navbar/sidebar for the whole ERP |
| No business logic in templates | Move calculations to `services/` |

## Files

| Template | Route |
|----------|-------|
| `dashboard.html` | `/demo-sales/` |
| `orders.html` | `/demo-sales/orders` |
| `pipeline.html` | `/demo-sales/pipeline` |

Blueprint `template_folder` resolves to `addons/demo_sales/views/templates`.

## CSS bundled with the addon

Put stylesheet files under **`../static/`** (sibling of `views/`). The Blueprint sets **`static_folder`** to that directory. In templates:

```jinja2
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('demo_sales.static', filename='css/demo_sales.css') }}" />
{% endblock %}
```

That serves `addons/demo_sales/static/css/demo_sales.css` at `/demo-sales/static/css/demo_sales.css`.
