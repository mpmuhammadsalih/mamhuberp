from app.utils.phones import normalize_whatsapp, to_e164


def test_qatar_phone_normalization() -> None:
    assert to_e164("55551234") == "+97455551234"
    assert normalize_whatsapp("+974 5555 1234") == "97455551234"
