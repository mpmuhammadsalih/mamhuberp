# Nexus ERP — Client Proposal Package

This folder contains a client-ready proposal for **Nexus ERP**, built on the Nexa Dynamics FastAPI platform.

## Contents

| File | Purpose |
|------|---------|
| [Nexus-ERP-Client-Proposal.md](./Nexus-ERP-Client-Proposal.md) | Full proposal — executive summary, modules, architecture, implementation |
| [PRICING.md](./PRICING.md) | Detailed pricing — **Core ERP** and **AI Add-ons** listed separately |
| [Nexus-ERP-Client-Proposal.html](./Nexus-ERP-Client-Proposal.html) | Browser version with professional layout |
| [Nexus-ERP-Client-Proposal.pdf](./Nexus-ERP-Client-Proposal.pdf) | **Ready-to-send PDF** (generated from HTML) |

## How to use

1. **Review** — Edit company name, client name, dates, and pricing in `PRICING.md` before sending.
2. **Present** — Open `Nexus-ERP-Client-Proposal.html` in a browser, or use the PDF below.
3. **Regenerate PDF** — After editing HTML:
   ```powershell
   python client-proposal\generate_pdf.py
   ```

## Notes for sales

- Core ERP pricing covers platform license, implementation, and annual support.
- AI pricing is **optional** and itemized separately — clients can adopt AI modules incrementally.
- OpenAI API usage is typically **pass-through** or capped monthly; see pricing doc.
- Replace placeholder `[Client Name]` and `[Your Company]` before delivery.
