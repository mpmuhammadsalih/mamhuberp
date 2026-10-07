# MamaHub WhatsApp CRM

WhatsApp Admin / Sales CRM for MamaHub Trading. Staff can manage official Meta WhatsApp Cloud API chats, search Oracle `ITEMMASTER` stock and prices, create orders from conversations, and use AI **suggested** replies (never auto-sent).

This is a **new standalone project** at `/var/www/mamahub-whatsapp`. It uses the existing MamaHub **Oracle Autonomous Database**. CRM tables are prefixed `WA_*` so they do not collide with ERP tables (`ITEMMASTER`, `CUSTOMER`, `BILLHDR`, `BILLDTL`).

## Stack

- Frontend: React + Next.js (port `3090`)
- Backend: FastAPI (port `8090`)
- Database: Oracle (`oracledb` thin TLS + SQLAlchemy)
- Auth: JWT + bcrypt + role-based permissions
- Realtime: WebSocket (`/ws`)
- WhatsApp: Official Meta Cloud API only
- AI: OpenAI (suggest only)

## Project layout

```
mamahub-whatsapp/
  backend/app/{api,core,database,models,schemas,services,repositories/oracle,integrations}
  frontend/src/{app,components,lib}
  nginx/mamahub-whatsapp.conf
  .env.example
```

## Phase status

1. Backend, Oracle models, JWT auth, webhook, send-message service
2. WhatsApp Inbox UI + WebSocket
3. Product search (ITEMMASTER) + customer panel
4. Orders / cart from chat
5. Quick replies + templates
6. AI suggested replies
7. Dashboard + reports
8. Oracle repository interfaces (`ProductRepository`, `CustomerRepository`, `OrderRepository`)

## Setup

```bash
cd /var/www/mamahub-whatsapp
cp .env.example .env
# fill Oracle + WhatsApp + JWT + OpenAI values
```

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd /var/www/mamahub-whatsapp/backend
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8090
```

On first start the app creates `WA_*` tables and seeds:

- Super admin from `BOOTSTRAP_ADMIN_*`
- Default quick replies (`/delivery`, `/payment`, `/price`, `/thanks`, `/location`)
- `order_confirmed` template row

Login default (change immediately): `admin` / `admin123`

### Frontend

```bash
cd /var/www/mamahub-whatsapp
./scripts/start-backend.sh
./scripts/start-frontend.sh
```

Production URL: `https://whatsapp.mamahub.store`

Local: `http://127.0.0.1:3090` — sign in with `admin` / `admin123`.

Add a DNS **A** record for `whatsapp.mamahub.store` pointing to this server, then:

```bash
certbot --nginx -d whatsapp.mamahub.store --redirect
```

Meta webhook URL: `https://whatsapp.mamahub.store/api/whatsapp/webhook`

The UI first compile can take a minute. If `/login` hangs, restart the frontend process and try again.

### Meta webhook

Point WhatsApp webhook to:

- `GET/POST https://your-host/api/whatsapp/webhook`
- Verify token = `WHATSAPP_VERIFY_TOKEN`
- Subscribe to `messages`

The webhook returns `200` immediately and processes events in a background task.

## Roles

| Role | Access |
| --- | --- |
| SUPER_ADMIN | Everything |
| ADMIN | Users, settings, templates, reports, chats, orders |
| SALES | Chats, product search, orders, customers |
| CUSTOMER_SERVICE | Chats, customers, product search |

## Oracle integration

Product search reads live `ITEMMASTER` via `OracleItemMasterProductRepository`.  
New WhatsApp numbers create `WA_CUSTOMERS` and optionally match `CUSTOMER` by mobile/WhatsApp.  
Orders are stored in `WA_ORDERS` / `WA_ORDER_ITEMS` so they can later post to `BILLHDR` / `BILLDTL` without changing API services.

## Security

Never put `WHATSAPP_ACCESS_TOKEN`, `OPENAI_API_KEY`, or `DB_PASSWORD` in frontend code. The Next.js app only talks to `/api` on the FastAPI backend.
