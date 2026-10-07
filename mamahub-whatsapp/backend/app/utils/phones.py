"""Phone number helpers for Qatar / E.164 / WhatsApp recipients."""
from __future__ import annotations


def digits_only(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def to_e164(phone: str) -> str:
    cleaned = str(phone or "").strip().replace(" ", "").replace("-", "")
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if cleaned.startswith("00"):
        cleaned = cleaned[2:]
    if cleaned.startswith("974"):
        return "+" + cleaned
    if len(cleaned) == 8 and cleaned.isdigit():
        return "+974" + cleaned
    if cleaned.isdigit():
        return "+" + cleaned
    return ""


def to_wa_recipient(phone: str) -> str:
    return to_e164(phone).lstrip("+")


def normalize_whatsapp(phone: str) -> str:
    return to_wa_recipient(phone)
