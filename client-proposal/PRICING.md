# Nexus ERP — Pricing Schedule

**Prepared for:** [Client Name]  
**Prepared by:** [Your Company]  
**Valid until:** [Date + 90 days]  
**Currency:** USD (or specify QAR/AED as needed)

---

## Pricing overview

| Category | One-time | Recurring (annual) |
|----------|----------|---------------------|
| **Core ERP Platform** | $45,000 – $85,000 | $12,000 – $24,000 / year |
| **AI Intelligence Suite** (optional) | $8,000 – $18,000 | $3,600 – $8,400 / year |
| **Third-party API costs** (OpenAI, SMS) | — | Pass-through or capped (see below) |

> All figures are indicative. Final quote depends on branch count, tenant count, data migration scope, and selected modules.

---

## 1. Core ERP Platform

### 1.1 Platform license (perpetual)

Includes source deployment rights, unlimited users within licensed branches, and all non-AI modules listed in the proposal.

| Tier | Branches / locations | Tenants | License (one-time) |
|------|----------------------|---------|-------------------|
| **Starter** | Up to 3 | 1 | $18,000 |
| **Growth** | Up to 10 | Up to 3 | $32,000 |
| **Enterprise** | Up to 25 | Up to 10 | $52,000 |
| **Corporate** | 25+ | Unlimited | Custom quote |

*Multi-DB / head-office (HO) central control included from Growth tier upward.*

### 1.2 Implementation & go-live (one-time)

| Service | Description | Price range |
|---------|-------------|-------------|
| **Discovery & blueprint** | Process mapping, role design, branch/tenant plan | $3,000 – $6,000 |
| **Environment setup** | Server, Oracle connectivity, SSL, database wizard | $2,500 – $5,000 |
| **Core module configuration** | Master data, GL dimensions, fiscal year, roles | $8,000 – $15,000 |
| **Sales & POS rollout** | Invoicing, counter setup, settlement, printers (QZ) | $6,000 – $12,000 |
| **Purchase & warehouse** | LPO, GRN, stock moves, verification workflows | $5,000 – $10,000 |
| **Finance & accounts** | COA, journals, VAT, bank recon, standard reports | $6,000 – $12,000 |
| **HO & multi-branch** (if applicable) | Central masters, requests, cross-tenant reporting | $5,000 – $10,000 |
| **Data migration** | Legacy Oracle / RFIM schema mapping & validation | $8,000 – $25,000 |
| **UAT & go-live support** | Parallel run, cutover, hypercare (2 weeks) | $4,000 – $8,000 |

**Typical implementation bundle (Growth tier, 5 branches):** **$45,000 – $65,000** one-time

### 1.3 Annual support & maintenance

| Plan | Coverage | Annual fee (% of license) | Min. annual |
|------|----------|----------------------------|-------------|
| **Standard** | Business hours support, patches, minor fixes | 20% of license | $12,000 |
| **Premium** | Extended hours, priority SLA, quarterly health checks | 28% of license | $18,000 |
| **Enterprise** | 24×7 critical incident, dedicated account manager | Custom | $24,000+ |

Includes: security patches, bug fixes, compatibility updates (Python/FastAPI/Oracle driver), and remote assistance.

**Excludes:** new feature development, major module additions, on-site visits (quoted separately).

### 1.4 Training

| Package | Audience | Duration | Price |
|---------|----------|----------|-------|
| **Admin & IT** | System admins, DB setup, roles | 2 days (remote) | $2,000 |
| **Finance team** | Accounts, VAT, reporting | 2 days (remote) | $2,000 |
| **Operations** | Sales, POS, warehouse, purchase | 3 days (remote) | $3,000 |
| **Train-the-trainer** | Client super-users | 1 day + materials | $1,500 |
| **On-site delivery** | Any of the above | Per day | +$1,200 / day + travel |

---

## 2. AI Intelligence Suite (optional)

AI modules are **priced separately** so clients can adopt intelligence features without committing to the full suite on day one.

### 2.1 AI module license (one-time add-on)

| Module | Capability | One-time license |
|--------|------------|------------------|
| **AI Forecast Cockpit** | Sales/purchase forecast, reorder suggestions, analytics dashboards | $4,500 |
| **Smart List Assistant** | Natural-language queries over live Oracle data (read-only) | $5,500 |
| **Document Intelligence Pack** | GRN invoice extract, NL purchase orders, temp invoice analysis | $4,000 |
| **Operational AI Pack** | POS verify insights, Arabic item name assist, HO customer onboarding AI | $3,500 |
| **Full AI Suite** | All modules above (bundle discount) | **$14,000** *(save $3,500)* |

### 2.2 AI implementation (one-time)

| Service | Price |
|---------|-------|
| OpenAI integration & security review | $1,500 |
| Forecast tuning & baseline calibration | $2,000 – $4,000 |
| Smart List schema guardrails & role policies | $2,500 – $4,000 |
| Document AI prompt tuning (GRN/PO templates) | $1,500 – $3,000 |
| User training — AI modules (half day) | $800 |

**Typical AI rollout (Full Suite):** **$8,000 – $12,000** one-time (in addition to license)

### 2.3 AI annual support

| Plan | Annual fee |
|------|------------|
| Per individual AI module | 22% of module license (min. $800 / module) |
| **Full AI Suite** | $3,600 / year (includes model/prompt updates, compatibility) |

### 2.4 Third-party AI API costs (OpenAI)

| Model usage | Billing approach |
|-------------|------------------|
| **Pass-through** | Client billed at cost + 10% admin (recommended for high volume) |
| **Capped monthly** | Fixed $150 / $350 / $750 per month tiers with usage alerts |
| **Client-owned key** | Client supplies `OPENAI_API_KEY`; no markup from vendor |

*Estimated usage (Full Suite, medium distributor): **$80 – $250 / month** depending on Smart List and document volume.*

---

## 3. Integrations & messaging (non-AI)

| Integration | Setup (one-time) | Notes |
|-------------|------------------|-------|
| **SMS (Vodafone Connect / Qatar)** | $800 – $1,500 | Template setup, outstanding alerts |
| **WhatsApp (Twilio)** | $1,000 – $2,000 | PDF outstanding delivery |
| **Tasveek / external wholesale API** | $1,500 – $3,000 | Online stock/pricing sync |
| **QZ Tray printing** | Included in POS rollout | Certificate signing setup |
| **Crystal Reports bridge** | $500 – $1,500 | Legacy report compatibility |

**Messaging usage:** SMS/WhatsApp message fees billed by carrier (pass-through).

---

## 4. Sample packages

### Package A — Core ERP (Growth)

| Item | Amount |
|------|--------|
| Growth license (10 branches, 3 tenants) | $32,000 |
| Implementation bundle | $52,000 |
| Standard support (Year 1) | $12,000 |
| Remote training (Operations + Finance) | $5,000 |
| **Year 1 total** | **$101,000** |
| **Year 2+ (support only)** | **$12,000 / year** |

### Package B — Core ERP + Full AI Suite

| Item | Amount |
|------|--------|
| Everything in Package A | $101,000 |
| Full AI Suite license | $14,000 |
| AI implementation | $10,000 |
| AI support (Year 1) | $3,600 |
| OpenAI capped tier (Year 1) | $4,200 ($350 × 12) |
| **Year 1 total** | **$128,800** |
| **Year 2+ (support + AI + API cap)** | **$19,800 / year** |

### Package C — Phased start (Core now, AI later)

| Phase | Deliverable | Investment |
|-------|-------------|------------|
| **Phase 1** (Months 1–4) | Core ERP go-live | Package A pricing |
| **Phase 2** (Months 5–6) | AI Forecast + Smart List only | +$12,500 license & setup |
| **Phase 3** (Optional) | Document & operational AI packs | +$7,500 license & setup |

---

## 5. Payment terms

| Milestone | % | Typical trigger |
|-----------|---|-----------------|
| Contract signing | 30% | Upon agreement |
| Environment & blueprint complete | 20% | Week 4 |
| UAT sign-off | 30% | Pre go-live |
| Go-live + 30-day hypercare | 20% | Post cutover |

AI add-ons may be invoiced at Phase 2 kickoff if purchased later.

---

## 6. Assumptions & exclusions

**Included in quoted ranges:**
- Remote implementation and configuration
- Standard Oracle schema bootstrap via database wizard
- Documentation for admins and end users (standard)

**Excluded (quoted separately if needed):**
- Oracle Database licenses and infrastructure (VM, OS, backup)
- Oracle Instant Client installation on client servers
- Custom report development beyond standard module reports
- On-site travel unless specified
- Hardware (PDT scanners, receipt printers, POS terminals)
- Penetration testing and formal compliance audits

---

## 7. Sign-off

| | Client | Vendor |
|---|--------|--------|
| **Name** | __________________ | __________________ |
| **Title** | __________________ | __________________ |
| **Date** | __________________ | __________________ |
| **Signature** | __________________ | __________________ |

---

*Pricing confidential — prepared exclusively for [Client Name].*
