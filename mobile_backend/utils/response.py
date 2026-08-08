from starlette.responses import JSONResponse


def success(data=None, message="OK", status_code=200, save_nonce: str | None = None):
    content: dict = {"success": True, "message": message, "data": data}
    if save_nonce:
        content["save_nonce"] = save_nonce
    return JSONResponse(status_code=status_code, content=content)


def failure(message="Request failed", status_code=400, error_code=None):
    payload = {"success": False, "message": message}
    if error_code:
        payload["error_code"] = error_code
    return JSONResponse(status_code=status_code, content=payload)


def http_error_content(message: str, error_code: str | None = None) -> dict:
    body: dict = {"success": False, "message": message}
    if error_code:
        body["error_code"] = error_code
    return body
