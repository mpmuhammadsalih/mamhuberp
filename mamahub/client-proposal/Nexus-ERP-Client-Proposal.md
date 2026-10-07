# Nexus ERP — Client Proposal

**Prepared for:** [Client Name]  
**Prepared by:** [Your Company]  
**Date:** May 2026  
**Version:** 1.0  
**Classification:** Confidential

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [Business context](#2-business-context)
3. [Solution overview](#3-solution-overview)
4. [Core platform modules](#4-core-platform-modules)
5. [AI intelligence suite](#5-ai-intelligence-suite-optional)
6. [Technical architecture](#6-technical-architecture)
7. [Integrations](#7-integrations)
8. [Implementation roadmap](#8-implementation-roadmap)
9. [Support, training & SLA](#9-support-training--sla)
10. [Investment summary](#10-investment-summary)
11. [Why Nexus ERP](#11-why-nexus-erp)
12. [Next steps](#12-next-steps)

---

## 1. Executive summary

**Nexus ERP** is a modern, web-based enterprise resource planning platform designed for **distribution, wholesale, and multi-branch retail** operations. Built on a proven Oracle data model aligned with industry-standard RFIM/RGC workflows, Nexus ERP unifies sales, point-of-sale, purchasing, warehouse, finance, and head-office control in a single browser-accessible system.

This proposal outlines a phased deployment that delivers operational excellence through a **modular, 47-addon architecture**, optional **multi-tenant head-office control**, and an **AI Intelligence Suite** that can be adopted independently of the core platform.

**Recommended starting point:** Growth-tier core ERP with phased AI adoption (Forecast + Smart List in Phase 2).

| | |
|---|---|
| **Target go-live** | 16–20 weeks from contract |
| **Year 1 investment (Core)** | $101,000 *(see [PRICING.md](./PRICING.md))* |
| **Year 1 investment (Core + AI)** | $128,800 |
| **Platform** | FastAPI + Oracle + browser UI |

---

## 2. Business context

### 2.1 Typical challenges

Organizations in FMCG distribution and retail commonly face:

- **Fragmented systems** — POS, finance, and warehouse on separate tools with manual reconciliation
- **Slow visibility** — Outstanding balances, stock levels, and margins reported days late
- **Multi-branch complexity** — Each location operating independently without HO oversight
- **Manual purchase workflows** — Paper GRNs, handwritten LPOs, delayed AP posting
- **Limited analytics** — Reports require IT or SQL knowledge; no self-service insights
- **Customer engagement gaps** — Outstanding reminders sent manually or not at all

### 2.2 How Nexus ERP addresses these

| Challenge | Nexus ERP response |
|-----------|-------------------|
| Fragmented operations | Single platform: sales, POS, purchase, warehouse, GL |
| Branch silos | Multi-DB tenant model with HO central masters & requests |
| Slow reporting | Real-time dashboards, 20+ standard reports, central stock views |
| Manual AP/GRN | Digital LPO → GRN → posting with optional AI document extract |
| Analytics bottleneck | Dashboard KPIs + optional Smart List natural-language assistant |
| Collections | Automated SMS/WhatsApp outstanding alerts with PDF attachments |

---

## 3. Solution overview

Nexus ERP is organized as **installable business modules** (addons), each covering a distinct operational area. Modules share a common security model (role-based menu permissions), session context (branch/tenant/location), and Oracle backend.

```
┌─────────────────────────────────────────────────────────────────┐
│                     Nexus ERP — Web Application                  │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│   Dashboard  │    Setup     │    Master    │   Sales & POS      │
│   & KPIs     │  Users/Roles │  Data Mgmt   │   Invoicing        │
├──────────────┼──────────────┼──────────────┼────────────────────┤
│  Inventory   │  Warehouse   │   Purchase   │   Accounts/GL      │
│  & Items     │  & Stock     │  LPO/GRN/AP  │   Finance          │
├──────────────┴──────────────┴──────────────┴────────────────────┤
│  Reports & Analytics  │  HO Control  │  Collaboration (Chat)    │
├───────────────────────┴──────────────┴─────────────────────────┤
│              AI Intelligence Suite (Optional Add-on)             │
│   Forecast │ Smart List │ Document AI │ Operational AI          │
├─────────────────────────────────────────────────────────────────┤
│              Oracle Database (Single-DB or Multi-DB)             │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 Delivery model

- **Deployment:** On-premise or client-managed VM (Windows/Linux)
- **Access:** Any modern browser; no desktop client required
- **Users:** Unlimited within licensed branch count
- **Languages:** English UI with Arabic item/description support

---

## 4. Core platform modules

The following modules are included in the **Core ERP Platform** license. Scope can be trimmed for Phase 1 if certain areas are not yet required.

### 4.1 Setup & administration

| Module | Capability |
|--------|------------|
| **Users & roles** | User provisioning, password policies, menu-level RBAC |
| **Tenants & multi-DB** | Auth DB + per-tenant Oracle connections; tenant switcher |
| **Branch / location** | Location master, fiscal context, company profile |
| **System config** | GL dimensions, fiscal year, promotions, menu pricing |
| **Database wizard** | Guided first-time Oracle setup and schema bootstrap |
| **Activity log** | Audit trail of key user actions |

### 4.2 Master data

| Module | Capability |
|--------|------------|
| **Customer master** | Cash/credit customers, routes, categories, credit limits |
| **Supplier master** | Vendor records, payment terms |
| **Item master** | Products, brands, UOM, barcodes, repacking, categories |
| **Salesman & route** | Territory assignment, visit planning |
| **Employee & session** | Staff records, POS session management |

### 4.3 Sales & point of sale

| Module | Capability |
|--------|------------|
| **Sales invoicing** | Cash/credit invoices, returns, sales orders |
| **POS billing** | Counter sales, multi-tender settlement (cash, card, wallet) |
| **Settlement** | End-of-day counter reconciliation |
| **Printing** | QZ Tray signed receipts; Crystal Reports compatibility |

### 4.4 Inventory & warehouse

| Module | Capability |
|--------|------------|
| **Stock management** | On-hand by location, store transfers |
| **Warehouse ops** | Bins, stock moves, visual stock, verification |
| **Stock counting** | Cycle counts with mobile-friendly workflows |
| **Barcode management** | Label generation and scanning support |

### 4.5 Purchasing

| Module | Capability |
|--------|------------|
| **LPO** | Local purchase orders with approval workflow |
| **GRN** | Goods receipt, batch/lot tracking, verification |
| **Returns & adjustments** | Purchase returns, debit notes, valuation |
| **AP posting** | Purchase invoice posting to GL |

### 4.6 Finance & accounts

| Module | Capability |
|--------|------------|
| **Chart of accounts** | Full COA with dimensions |
| **Journals & posting** | Manual and system-generated entries |
| **AR/AP** | Receivables, payables, PDC (post-dated cheques) |
| **Bank reconciliation** | Statement matching |
| **VAT & compliance** | Tax reporting aligned to regional requirements |
| **Financial statements** | Trial balance, P&L, balance sheet |

### 4.7 Collections & temporary workflows

| Module | Capability |
|--------|------------|
| **Temporary invoices** | Ad-hoc invoice analysis and staging |
| **Temporary collection** | Field collection recording |
| **Temporary pending** | Pending receipt tracking |
| **Outstanding reports** | Aging, salesman-wise, location-wise |

### 4.8 Head office (HO)

| Module | Capability |
|--------|------------|
| **Central masters** | Item, supplier, customer maintained at HO |
| **Master requests** | Branch-initiated requests for new items/customers |
| **Cross-tenant reporting** | Central stock views across linked Oracle schemas |
| **DB sync** | Schema synchronization for new company onboarding |

### 4.9 Reports & analytics

| Module | Capability |
|--------|------------|
| **Sales reports** | Detail, summary, margin analysis |
| **Purchase reports** | PO/GRN detail, supplier performance |
| **Stock reports** | Location stock, central/linked stock, movement |
| **Collection reports** | Outstanding, receipts, salesman performance |
| **Dashboard** | KPI tiles, tenant/dbkey switching for admins |

### 4.10 Collaboration & utilities

| Module | Capability |
|--------|------------|
| **Internal chat** | Team messaging with groups and reactions |
| **Notifications** | Outstanding due alerts |
| **PDT setup** | Handheld scanner roles for warehouse |
| **Plan / recovery** | Missing-customer visit tasks |
| **Tasveek online** | External wholesale API sync (optional integration) |

---

## 5. AI Intelligence Suite (optional)

AI capabilities are delivered as **optional add-on modules**, priced and implemented separately from the core ERP. This allows your organization to stabilize operations first, then layer intelligence where it delivers the highest ROI.

> **Detailed AI pricing:** See [PRICING.md — Section 2](./PRICING.md#2-ai-intelligence-suite-optional)

### 5.1 AI Forecast Cockpit

- Sales and purchase demand forecasting with reorder suggestions
- Product, supplier, and customer analytics with interactive charts
- Rule-based engine with optional OpenAI narrative insights
- Configurable forecast horizons and safety stock parameters

### 5.2 Smart List Assistant

- Natural-language questions answered against **live Oracle data** (read-only)
- Role-aware query guardrails — users only see data their permissions allow
- Conversation history for follow-up questions
- Eliminates ad-hoc SQL requests to IT for routine business questions

### 5.3 Document Intelligence Pack

| Feature | Benefit |
|---------|---------|
| **GRN invoice extract** | Upload supplier invoice (PDF/image) → structured GRN lines |
| **Natural-language PO** | Describe purchase needs in plain text → draft PO with item matching |
| **Temporary invoice analysis** | AI-assisted column/SQL suggestions for ad-hoc analysis |

### 5.4 Operational AI Pack

| Feature | Benefit |
|---------|---------|
| **POS verify insights** | AI analysis of settlement simulation and live counter data |
| **Arabic item names** | Bulk suggest/fill Arabic product descriptions |
| **HO customer onboarding** | AI-assisted processing of branch customer requests |

### 5.5 AI adoption recommendation

| Phase | Modules | Rationale |
|-------|---------|-----------|
| **Phase 2a** | Forecast + Smart List | Immediate visibility ROI; low change management |
| **Phase 2b** | Document Intelligence | Reduces AP/GRN data entry after core purchase is stable |
| **Phase 3** | Operational AI Pack | POS and HO workflows optimized once baseline metrics exist |

---

## 6. Technical architecture

### 6.1 Technology stack

| Layer | Technology |
|-------|------------|
| Application server | **FastAPI** + Uvicorn (Python 3.10+) |
| Database | **Oracle Database** (cx_Oracle 8.3) |
| Web UI | Server-rendered templates + Bootstrap; responsive layout |
| Authentication | Session-based login with role/menu permissions |
| Reporting export | PDF (ReportLab), Excel (openpyxl) |
| Arabic support | UTF-8 (`NLS_LANG`), arabic-reshaper, python-bidi |
| AI (optional) | OpenAI API (gpt-4o-mini default) |

### 6.2 Multi-tenant architecture

Nexus ERP supports two deployment modes:

**Single-DB mode** — All users and business data in one Oracle schema. Suitable for single-entity deployments.

**Multi-DB mode** — Separates authentication from business data:

```
┌─────────────────┐     ┌──────────────────────────────────────┐
│    Auth DB      │     │           Tenant DBs                  │
│  login_users    │     │  Tenant A │ Tenant B │ HO │ ...       │
│  roles          │────▶│  (Oracle) │ (Oracle) │    │           │
│  tenant_databases│     └──────────────────────────────────────┘
└─────────────────┘
```

- Users authenticate against the **Auth DB**
- Business transactions route to the correct **Tenant DB** based on session context
- HO tenant (`HO`) enables central master management and cross-branch requests
- Admin users can switch tenants via the dashboard switcher

### 6.3 Security

- Role-based access control at menu and action level
- Session timeout (configurable, default 8 hours)
- Password hashing (industry-standard algorithms)
- AI Smart List enforces read-only SELECT with schema guardrails
- Optional HTTPS termination at reverse proxy

### 6.4 Infrastructure requirements (client-provided)

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| App server | 4 vCPU, 8 GB RAM | 8 vCPU, 16 GB RAM |
| Oracle | Client-managed instance | RAC or managed Oracle Cloud |
| OS | Windows Server or Linux | Linux (Ubuntu/RHEL) |
| Network | LAN + optional VPN | SSL reverse proxy (nginx/IIS) |
| Oracle client | Instant Client 19c+ | Matching DB version |

---

## 7. Integrations

| Integration | Type | Use case |
|-------------|------|----------|
| **Oracle Database** | Core | System of record |
| **Vodafone Connect SMS** | Messaging | Outstanding balance alerts (Qatar) |
| **Twilio WhatsApp** | Messaging | PDF outstanding delivery |
| **Tasveek / Rawabi API** | Data sync | Online wholesale stock & pricing |
| **QZ Tray** | Printing | Signed PDF receipts at POS |
| **Crystal Reports** | Reporting | Legacy report compatibility |
| **OpenAI** | AI (optional) | Forecast, Smart List, document extract |

*Payment gateways (Stripe, etc.) are not included — POS supports internal tender types mapped to GL.*

---

## 8. Implementation roadmap

### Phase 1 — Foundation (Weeks 1–4)

- Kickoff, discovery workshops, process blueprint
- Server provisioning, Oracle connectivity, database wizard
- Auth DB / tenant DB configuration (if multi-DB)
- Core master data: company, branches, roles, users, GL dimensions, fiscal year

### Phase 2 — Operations (Weeks 5–10)

- Item, customer, supplier, salesman master migration
- Sales invoicing and POS counter setup
- Purchase LPO/GRN workflows
- Warehouse locations, stock moves, opening balances
- Standard reports validation

### Phase 3 — Finance & HO (Weeks 11–14)

- Accounts posting, VAT, bank recon
- HO central masters and request workflows (if applicable)
- SMS/WhatsApp integration (if purchased)
- End-user training (remote)

### Phase 4 — Go-live (Weeks 15–18)

- User acceptance testing (UAT)
- Parallel run with legacy system
- Cutover and hypercare (2 weeks post go-live)
- Handover documentation

### Phase 5 — AI (Optional, Weeks 19–22)

- OpenAI integration and security review
- Forecast calibration against historical data
- Smart List guardrail configuration
- Document AI prompt tuning
- AI user training (half day)

```
Week:  1    4    8    12   16   20   22
       │────│────│────│────│────│────│
Phase1 ████
Phase2      ████████████
Phase3                  ████████
Phase4                          ████
Phase5 (opt)                        ████
```

---

## 9. Support, training & SLA

### 9.1 Support tiers

| Plan | Hours | Response (Critical) | Response (Normal) |
|------|-------|---------------------|-------------------|
| Standard | Business hours | 4 business hours | 1 business day |
| Premium | Extended | 2 business hours | 4 business hours |
| Enterprise | 24×7 critical | 1 hour | Same day |

### 9.2 Training included in typical package

- 2 days — Finance & accounts team
- 3 days — Operations (sales, POS, warehouse, purchase)
- 1 day — Admin & IT (roles, tenants, database modes)
- User quick-reference guides (PDF)

### 9.3 Deliverables at go-live

- Configured production environment
- Migrated master data and opening balances
- Role/permission matrix document
- Admin runbook (backup, restart, log locations)
- UAT sign-off record

---

## 10. Investment summary

> Full pricing tables: **[PRICING.md](./PRICING.md)**

### 10.1 Core ERP (recommended — Growth tier)

| Component | Year 1 |
|-----------|--------|
| Platform license | $32,000 |
| Implementation | $52,000 |
| Standard support | $12,000 |
| Training | $5,000 |
| **Total Year 1** | **$101,000** |
| **Year 2+ recurring** | **$12,000 / year** |

### 10.2 AI Intelligence Suite (optional add-on)

| Component | Year 1 add-on |
|-----------|---------------|
| Full AI Suite license | $14,000 |
| AI implementation | $10,000 |
| AI support | $3,600 |
| OpenAI usage (capped tier) | $4,200 |
| **AI Year 1 add-on** | **$31,800** |
| **AI Year 2+ recurring** | **$7,800 / year** |

### 10.3 Combined (Core + AI)

| | Year 1 | Year 2+ |
|---|--------|---------|
| **Total** | **$128,800** | **$19,800 / year** |

### 10.4 Payment schedule

30% signing → 20% blueprint → 30% UAT → 20% go-live + hypercare

---

## 11. Why Nexus ERP

| Differentiator | Detail |
|----------------|--------|
| **Oracle-native** | Built on proven RFIM/RGC schema — not a generic SaaS retrofit |
| **Multi-branch ready** | HO control, tenant isolation, central reporting out of the box |
| **Modular growth** | Start with core modules; add AI, Tasveek, messaging when ready |
| **Regional fit** | Arabic support, Qatar SMS, Gulf distribution workflows |
| **Practical AI** | Intelligence tied to real business data — not generic chatbots |
| **No per-user SaaS tax** | Perpetual license with predictable annual support |
| **Full ownership** | Deployed on your infrastructure; your data stays yours |

---

## 12. Next steps

1. **Discovery call** — Confirm branch count, tenant structure, and legacy system
2. **Module scoping** — Finalize Phase 1 module list and migration scope
3. **Proposal refinement** — Adjust tier and pricing based on scope
4. **Contract & kickoff** — Target start within 2 weeks of signing

---

**Contact**

[Your Name]  
[Title]  
[Email] | [Phone]  
[Company Website]

---

*This document is confidential and intended solely for [Client Name]. Pricing valid for 90 days from date of issue.*
