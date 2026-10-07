"""Official Meta WhatsApp Cloud API send helpers."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import get_settings
from app.core.logging import logger
from app.utils.phones import digits_only, to_wa_recipient

_PROFILE_TTL = 3600.0
_profile_cache: Dict[str, Any] = {"at": 0.0, "data": {}}


def friendly_send_error(message: str, code: Any = None) -> str:
    text = str(message or "").strip()
    low = text.lower()
    code_s = str(code or "")
    if "re-engagement" in low or code_s == "131047":
        return "WhatsApp blocked this. The customer has not written in 24 hours. Wait for their reply, or send an approved Template."
    if "number of parameters" in low or code_s == "132000":
        return "This template needs different variables. Check the template in Meta, then try again."
    if "access blocked" in low:
        return "WhatsApp API access is blocked. Check the Meta token and app review status."
    return text or "WhatsApp did not accept this message."


def format_display_phone(value: str) -> str:
    digits = digits_only(value)
    if digits.startswith("974") and len(digits) == 11:
        return f"+974 {digits[3:7]} {digits[7:]}"
    if value.startswith("+") and len(value) > 4:
        return value
    if digits:
        return f"+{digits}"
    return value.strip()


class WhatsAppClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.whatsapp_access_token and self.settings.whatsapp_phone_number_id)

    def _url(self, path: str = "messages") -> str:
        version = self.settings.whatsapp_api_version.strip() or "v21.0"
        phone_id = self.settings.whatsapp_phone_number_id.strip()
        return f"https://graph.facebook.com/{version}/{phone_id}/{path}"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.whatsapp_access_token}",
            "Content-Type": "application/json",
        }

    def get_phone_profile(self) -> Dict[str, str]:
        fallback = format_display_phone(self.settings.whatsapp_display_number)
        now = time.time()
        cached = _profile_cache.get("data") or {}
        if cached and now - float(_profile_cache.get("at") or 0) < _PROFILE_TTL:
            return cached
        profile: Dict[str, str] = {
            "display_phone_number": fallback,
            "verified_name": "",
        }
        if self.configured:
            version = self.settings.whatsapp_api_version.strip() or "v21.0"
            phone_id = self.settings.whatsapp_phone_number_id.strip()
            url = f"https://graph.facebook.com/{version}/{phone_id}"
            try:
                with httpx.Client(timeout=12.0) as client:
                    response = client.get(
                        url,
                        headers={"Authorization": f"Bearer {self.settings.whatsapp_access_token}"},
                        params={"fields": "display_phone_number,verified_name"},
                    )
                data = response.json() if response.content else {}
                if response.is_success and isinstance(data, dict):
                    number = format_display_phone(str(data.get("display_phone_number") or fallback))
                    profile = {
                        "display_phone_number": number,
                        "verified_name": str(data.get("verified_name") or ""),
                    }
            except Exception:  # noqa: BLE001
                logger.exception("WhatsApp profile lookup failed")
        _profile_cache["at"] = now
        _profile_cache["data"] = profile
        return profile

    def _post(self, payload: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        if not self.configured:
            return False, "WhatsApp is not configured", {}
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(self._url(), headers=self._headers(), json=payload)
            data = response.json() if response.content else {}
            if response.is_success:
                message_id = ""
                messages = data.get("messages") if isinstance(data, dict) else None
                if isinstance(messages, list) and messages:
                    message_id = str(messages[0].get("id") or "")
                return True, message_id or "sent", data
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict):
                msg = error.get("message") or error.get("error_user_msg") or str(error)
                logger.warning("WhatsApp API error %s: %s", response.status_code, msg)
                return False, friendly_send_error(str(msg), error.get("code")), data
            return False, response.text or f"HTTP {response.status_code}", data
        except Exception as exc:  # noqa: BLE001
            logger.exception("WhatsApp send failed")
            return False, str(exc), {}

    def send_text_message(
        self,
        to_phone: str,
        body: str,
        reply_to_wamid: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        recipient = to_wa_recipient(to_phone)
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": body or " "},
        }
        if reply_to_wamid:
            payload["context"] = {"message_id": reply_to_wamid}
        return self._post(payload)

    def mark_message_read(self, wamid: str) -> Tuple[bool, str, Dict[str, Any]]:
        return self._post(
            {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": wamid,
            }
        )

    def revoke_message(self, wamid: str, to_phone: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "type": "revoke",
            "revoke": {"original_message_id": wamid},
        }
        if to_phone:
            payload["to"] = to_wa_recipient(to_phone)
        return self._post(payload)

    def delete_message(self, wamid: str) -> Tuple[bool, str, Dict[str, Any]]:
        ok, err, data = self._post(
            {
                "messaging_product": "whatsapp",
                "status": "deleted",
                "message_id": wamid,
            }
        )
        if ok:
            return ok, err, data
        return self.revoke_message(wamid)

    def send_image_message(self, to_phone: str, image_url: str, caption: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        recipient = to_wa_recipient(to_phone)
        image: Dict[str, Any] = {}
        media_id = None if (image_url or "").startswith("http") else self._upload_local_media(image_url, "image")
        if media_id:
            image["id"] = media_id
        else:
            image["link"] = image_url
        if caption:
            image["caption"] = caption[:1024]
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "image",
            "image": image,
        }
        return self._post(payload)

    def _upload_local_media(self, media_url: str, media_kind: str) -> Optional[str]:
        from app.core.config import get_settings

        name = (media_url or "").rsplit("/", 1)[-1]
        if not name:
            return None
        path = get_settings().upload_path / name
        if not path.exists():
            return None
        suffix = path.suffix.lower()
        mime = {
            ".ogg": "audio/ogg",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".amr": "audio/amr",
            ".webm": "audio/webm",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".pdf": "application/pdf",
        }.get(suffix, "application/octet-stream")
        try:
            with httpx.Client(timeout=45.0) as client:
                response = client.post(
                    self._url("media"),
                    headers={"Authorization": f"Bearer {self.settings.whatsapp_access_token}"},
                    data={"messaging_product": "whatsapp", "type": media_kind},
                    files={"file": (path.name, path.read_bytes(), mime)},
                )
            data = response.json() if response.content else {}
            if response.is_success and isinstance(data, dict) and data.get("id"):
                return str(data["id"])
            logger.warning("WhatsApp media upload failed: %s", data)
        except Exception:  # noqa: BLE001
            logger.exception("WhatsApp media upload failed")
        return None

    def send_audio_message(self, to_phone: str, audio_url: str) -> Tuple[bool, str, Dict[str, Any]]:
        recipient = to_wa_recipient(to_phone)
        audio: Dict[str, Any] = {}
        media_id = self._upload_local_media(audio_url, "audio")
        if media_id:
            audio["id"] = media_id
        else:
            audio["link"] = audio_url
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "audio",
            "audio": audio,
        }
        return self._post(payload)

    def send_document_message(
        self,
        to_phone: str,
        document_url: str,
        filename: Optional[str] = None,
        caption: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        recipient = to_wa_recipient(to_phone)
        document: Dict[str, Any] = {"link": document_url}
        if filename:
            document["filename"] = filename
        if caption:
            document["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "document",
            "document": document,
        }
        return self._post(payload)

    def send_template_message(
        self,
        to_phone: str,
        template_name: str,
        language_code: str = "en",
        body_params: Optional[List[str]] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        recipient = to_wa_recipient(to_phone)
        template: Dict[str, Any] = {
            "name": template_name,
            "language": {"code": language_code},
        }
        if body_params:
            template["components"] = [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(value)} for value in body_params],
                }
            ]
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": template,
        }
        return self._post(payload)

    def send_location_message(
        self,
        to_phone: str,
        latitude: float,
        longitude: float,
        name: Optional[str] = None,
        address: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        recipient = to_wa_recipient(to_phone)
        location: Dict[str, Any] = {"latitude": latitude, "longitude": longitude}
        if name:
            location["name"] = name
        if address:
            location["address"] = address
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "location",
            "location": location,
        }
        return self._post(payload)

    def send_interactive_message(self, to_phone: str, interactive: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        recipient = to_wa_recipient(to_phone)
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "interactive",
            "interactive": interactive,
        }
        return self._post(payload)

    def download_media(self, media_id: str) -> Tuple[Optional[bytes], Optional[str]]:
        if not self.configured or not media_id:
            return None, None
        version = self.settings.whatsapp_api_version.strip() or "v21.0"
        meta_url = f"https://graph.facebook.com/{version}/{media_id}"
        headers = {"Authorization": f"Bearer {self.settings.whatsapp_access_token}"}
        try:
            with httpx.Client(timeout=30.0) as client:
                meta = client.get(meta_url, headers=headers)
                if not meta.is_success:
                    return None, None
                url = (meta.json() or {}).get("url")
                mime = (meta.json() or {}).get("mime_type")
                if not url:
                    return None, None
                binary = client.get(url, headers=headers)
                if not binary.is_success:
                    return None, None
                return binary.content, mime
        except Exception:  # noqa: BLE001
            logger.exception("WhatsApp media download failed")
            return None, None


whatsapp_client = WhatsAppClient()


def send_text_message(to_phone: str, body: str) -> Tuple[bool, str, Dict[str, Any]]:
    return whatsapp_client.send_text_message(to_phone, body)


def send_image_message(to_phone: str, image_url: str, caption: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
    return whatsapp_client.send_image_message(to_phone, image_url, caption)


def send_audio_message(to_phone: str, audio_url: str) -> Tuple[bool, str, Dict[str, Any]]:
    return whatsapp_client.send_audio_message(to_phone, audio_url)


def send_document_message(
    to_phone: str,
    document_url: str,
    filename: Optional[str] = None,
    caption: Optional[str] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    return whatsapp_client.send_document_message(to_phone, document_url, filename, caption)


def send_template_message(
    to_phone: str,
    template_name: str,
    language_code: str = "en",
    body_params: Optional[List[str]] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    return whatsapp_client.send_template_message(to_phone, template_name, language_code, body_params)


def send_interactive_message(to_phone: str, interactive: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    return whatsapp_client.send_interactive_message(to_phone, interactive)
