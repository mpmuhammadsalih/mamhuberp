"""Live Phase 1 checks. Prints status codes only — never tokens."""
from __future__ import annotations

import os
import sys

import httpx

BASE = os.environ.get("CRM_BASE", "http://127.0.0.1:8090")


def main() -> int:
    with httpx.Client(timeout=30.0) as client:
        health = client.get(f"{BASE}/api/health")
        print("health", health.status_code)
        webhook = client.get(
            f"{BASE}/api/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "mamahub-whatsapp-verify",
                "hub.challenge": "OK",
            },
        )
        print("webhook", webhook.status_code, webhook.text == "OK")
        login = client.post(
            f"{BASE}/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        print("login", login.status_code, "has_token", "access_token" in login.json())
        if login.status_code != 200:
            print("login_detail", login.text[:200])
            return 1
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        conv = client.get(f"{BASE}/api/conversations", headers=headers)
        print(
            "conversations",
            conv.status_code,
            "count",
            len(conv.json()) if conv.status_code == 200 else conv.text[:160],
        )
        replies = client.get(f"{BASE}/api/quick-replies", headers=headers)
        print(
            "quick_replies",
            replies.status_code,
            "count",
            len(replies.json()) if replies.status_code == 200 else "",
        )
        dash = client.get(f"{BASE}/api/dashboard", headers=headers)
        print("dashboard", dash.status_code)
        products = client.get(
            f"{BASE}/api/products/search",
            params={"q": "Hot Wheels"},
            headers=headers,
        )
        if products.status_code == 200:
            rows = products.json()
            print("products", products.status_code, "count", len(rows))
            if rows:
                print(
                    "first_product",
                    rows[0].get("itemname"),
                    "stock",
                    rows[0].get("currentstock"),
                    "price",
                    rows[0].get("retailprice"),
                )
        else:
            print("products", products.status_code, products.text[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
