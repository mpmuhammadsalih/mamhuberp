# AI Sales & Purchase Forecasting Engine

FastAPI addon: `addons/ai_forecast` — menu **AI** → Forecast cockpit and analytics pages.

## Architecture (ML-ready)

```
addons/ai_forecast/
  services/schema.py          # Table/column resolution
  services/forecast_engine.py # Rule-based models → JSON (swap for ML later)
  controllers/routes.py       # Pages + REST APIs
  views/templates/            # Dashboard UI (Chart.js)
  sql/forecast_views.sql      # Optional Oracle views
```

## Forecast formulas

| Model | Formula |
|-------|---------|
| Moving average (7/30/90d) | `avg(daily_qty[-window:])` |
| Weighted trend forecast | `Σ(qty × weight) / Σ(weight) × horizon_days` |
| Reorder point | `(avg_daily_sales × lead_days) + safety_stock` |
| Safety stock | `avg_daily_sales × AI_FORECAST_SAFETY_DAYS` (default 7) |
| Reorder trigger | `(current_stock + pending_lpo) < reorder_point` |
| Product score (0–100) | Base 50 + monthly qty + log revenue + turnover − return penalty |
| Supplier rating | 35% frequency + 35% price stability + 30% delivery speed |

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/ai/` | Forecast cockpit dashboard |
| GET | `/ai/api/dashboard` | Full insights JSON |
| GET | `/ai/api/sales-forecast?horizon=30` | Sales forecast |
| GET | `/ai/api/purchase-forecast` | Purchase / reorder forecast |
| GET | `/ai/api/reorder` | Smart reorder list |
| GET | `/ai/api/products` | Product performance |
| GET | `/ai/api/suppliers` | Supplier performance |
| GET | `/ai/api/customers` | Customer analysis |
| GET | `/ai/api/reports/<type>` | Report JSON |
| POST | `/ai/api/insights/narrative` | OpenAI summary (optional) |

## Business rules

- Cancelled/deleted bills excluded when `CANCELFLAG` / `DELFLAG` exist
- Inactive items filtered when `ITEMFLAG` exists
- Pending LPO qty subtracted from reorder need (included in available stock)
- Branch filter via `session.location_code` → `LOCATIONCODE`
- Uses `BILLHDRHISTORY` / `BILLHDR` with automatic fallback

## Environment

- `AI_FORECAST_LEAD_DAYS` — default supplier lead (14)
- `AI_FORECAST_SAFETY_DAYS` — safety stock days (7)
- `AI_FORECAST_DEAD_DAYS` — dead stock threshold (90)
- `OPENAI_API_KEY` — optional narrative insights

## Permissions

Menu path: `ai_forecast.dashboard` — grant via **Roles & Permissions** for non-admin users.

## Future ML integration

Replace functions in `forecast_engine.py` with model inference; keep JSON response shapes stable for the UI.
