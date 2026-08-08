#!/usr/bin/env python3
"""
Browser-driven POS checkout (Playwright).

Exercises the real UI: login, gates, Test barcode, Payment modal, Card/Cash tender, Validate, receipt close.

Environment
-----------
POS_E2E_BASE_URL     Base URL (default http://127.0.0.1:5002 — matches FLASK_PORT in .env)
POS_E2E_USER         Login username (required)
POS_E2E_PASSWORD     Login password (required)
POS_E2E_PAYMENT      cash | card (default card — selects Card row so tender auto-fills)
POS_E2E_SKIP_SAVE    1 = stop after opening payment modal (no Validate, no invoice)
HEADLESS             0 = show browser (default 1)
POS_E2E_REPORT       Report JSON path (default ./pos_e2e_report.json in cwd)

Setup
-----
  pip install -r e2e/requirements-e2e.txt
  playwright install chromium

Run (app must be up)
--------------------
  set POS_E2E_USER=...
  set POS_E2E_PASSWORD=...
  python e2e/pos_browser_checkout.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

try:
    from playwright.sync_api import TimeoutError as PWTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Install Playwright: pip install -r e2e/requirements-e2e.txt && playwright install chromium", file=sys.stderr)
    raise


def _env_bool(key: str, default: bool = False) -> bool:
    v = (os.environ.get(key) or "").strip().lower()
    if v in ("1", "true", "yes", "y"):
        return True
    if v in ("0", "false", "no", "n"):
        return False
    return default


def _log(steps: List[Dict[str, Any]], name: str, ok: bool, detail: Any = None, ms: float | None = None) -> None:
    row: Dict[str, Any] = {"step": name, "ok": ok}
    if ms is not None:
        row["ms"] = round(ms, 2)
    if detail is not None:
        row["detail"] = detail
    steps.append(row)
    print(f"[{'OK' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail is not None else ""))


def _dismiss_fullscreen_gate(page) -> None:
    gate = page.locator("#posFullscreenGate:not(.hidden)")
    if gate.count() == 0:
        return
    dismiss = page.locator("#posFullscreenGateDismiss")
    if dismiss.count():
        dismiss.click()
    else:
        page.locator("#posFullscreenGateBtn").click()


def _open_shift_modal_visible(page, timeout_ms: int = 2500) -> bool:
    try:
        page.wait_for_selector("#posOpenShiftRequiredModal:not(.hidden)", timeout=timeout_ms)
        return True
    except PWTimeoutError:
        return False


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)
    except ImportError:
        pass

    base = (os.environ.get("POS_E2E_BASE_URL") or "http://127.0.0.1:5002").rstrip("/")
    user = (os.environ.get("POS_E2E_USER") or "").strip()
    password = os.environ.get("POS_E2E_PASSWORD") or ""
    payment = (os.environ.get("POS_E2E_PAYMENT") or "card").strip().lower()
    skip_save = _env_bool("POS_E2E_SKIP_SAVE", False)
    headless = _env_bool("HEADLESS", True)
    report_path = Path(os.environ.get("POS_E2E_REPORT") or "pos_e2e_report.json")

    steps: List[Dict[str, Any]] = []
    t0 = time.perf_counter()

    if not user or not password:
        _log(steps, "config", False, "Set POS_E2E_USER and POS_E2E_PASSWORD")
        report_path.write_text(json.dumps({"ok": False, "steps": steps}, indent=2), encoding="utf-8")
        return 2

    def timed(name: str, fn: Callable[[], Any]) -> Any:
        a = time.perf_counter()
        try:
            out = fn()
            _log(steps, name, True, None, (time.perf_counter() - a) * 1000)
            return out
        except Exception as e:
            _log(steps, name, False, str(e), (time.perf_counter() - a) * 1000)
            raise

    overall_ok = True
    save_json: Dict[str, Any] | None = None

    with sync_playwright() as p:

        def launch_browser():
            return p.chromium.launch(headless=headless)

        browser = timed("launch chromium", launch_browser)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        try:

            def do_login():
                page.goto(f"{base}/auth/login?next=/pos-billing", wait_until="domcontentloaded")
                page.fill("#login-username", user)
                page.fill("#login-password", password)
                page.click('form.form button[type="submit"]')
                page.wait_for_url("**/pos-billing**", timeout=120000)

            timed("login", do_login)

            def dismiss_gate():
                _dismiss_fullscreen_gate(page)
                page.wait_for_timeout(350)

            timed("dismiss fullscreen gate (if any)", dismiss_gate)

            if _open_shift_modal_visible(page, 3000):
                _log(
                    steps,
                    "open-shift gate",
                    False,
                    "POS requires an open shift for this counter — open Counter operations first or bind counter.",
                )
                overall_ok = False
                raise RuntimeError("Open shift required")

            timed(
                "wait POS shell",
                lambda: page.wait_for_selector("#btnPosBarcodeTest", state="visible", timeout=60000),
            )

            def add_test_line():
                page.click("#btnPosBarcodeTest")
                page.wait_for_function(
                    "() => { const t = document.getElementById('posNetTotal'); "
                    "return t && parseFloat((t.textContent||'0').replace(/,/g,'')) > 0.001; }",
                    timeout=60000,
                )

            timed("add line via Test barcode", add_test_line)

            def open_payment():
                page.click("#btnCheckout")
                page.wait_for_selector("#checkoutModal:not(.hidden)", timeout=15000)

            timed("open Payment modal", open_payment)

            if payment == "cash":

                def pay_cash_fill():
                    page.evaluate(
                        """() => {
                        const cash = document.getElementById('pay_t_CASH') || document.getElementById('pay_cash');
                        const due = document.getElementById('checkout_total_due');
                        const row = document.querySelector('.payment-method-row[data-category="cash"]')
                            || document.querySelector('.payment-method-row[data-method="cash"]');
                        if (row) row.click();
                        if (!cash || !due) throw new Error('payment fields missing');
                        cash.value = (due.textContent || '0').trim().replace(/,/g, '');
                        cash.dispatchEvent(new Event('input', { bubbles: true }));
                    }"""
                    )

                timed("select Cash + match tender", pay_cash_fill)
            else:
                timed(
                    "select Card (auto remainder)",
                    lambda: page.click(
                        '.payment-method-row[data-tender-code="CARD"], .payment-method-row[data-category="card"]'
                    ),
                )

            timed(
                "validation message ready",
                lambda: page.wait_for_function(
                    """() => {
                    const el = document.getElementById('checkout_validation_msg');
                    const t = (el && el.textContent) ? el.textContent.trim() : '';
                    return t.includes('Amount matches') || t.includes('Validate') || t.includes('Change');
                }""",
                    timeout=15000,
                ),
            )

            if skip_save:
                _log(steps, "skip save (POS_E2E_SKIP_SAVE)", True, "Stopped before Validate")
            else:

                def click_validate():
                    page.click("#btnCheckoutConfirm")

                with page.expect_response(
                    lambda r: "/pos-billing/save" in (r.url or "") and r.request.method == "POST",
                    timeout=120000,
                ) as resp_info:
                    timed("Validate (checkout)", click_validate)
                resp = resp_info.value
                try:
                    save_json = resp.json()
                except Exception:
                    save_json = {"http_status": resp.status, "note": "non-json body"}
                save_ok = resp.ok and isinstance(save_json, dict) and bool(save_json.get("success"))
                _log(
                    steps,
                    "save response",
                    save_ok,
                    save_json if isinstance(save_json, dict) else {"status": resp.status},
                )
                if not save_ok:
                    overall_ok = False

                def close_receipt_if_any():
                    try:
                        page.wait_for_selector("#receiptPreviewModal:not(.hidden)", timeout=25000)
                        page.locator('#receiptPreviewModal [data-close="receiptPreviewModal"]').first.click(timeout=10000)
                    except PWTimeoutError:
                        pass

                timed("close receipt preview (if any)", close_receipt_if_any)

        except Exception as exc:
            overall_ok = False
            if "Open shift required" not in str(exc):
                _log(steps, "aborted", False, str(exc))
            shot = Path(os.environ.get("POS_E2E_SCREENSHOT") or "pos_e2e_failure.png")
            try:
                page.screenshot(path=str(shot), full_page=True)
                _log(steps, "screenshot", True, str(shot))
            except Exception as se:
                _log(steps, "screenshot", False, str(se))
        finally:
            context.close()
            browser.close()

    report = {
        "ok": overall_ok,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        "base_url": base,
        "payment": payment,
        "skip_save": skip_save,
        "steps": steps,
        "save_response": save_json,
    }
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nReport written to {report_path.resolve()}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
