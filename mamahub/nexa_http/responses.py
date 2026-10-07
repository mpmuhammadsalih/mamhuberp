from __future__ import annotations

import io
import os
from typing import Any, BinaryIO, Mapping, Optional, Union

from fastapi.encoders import jsonable_encoder
from starlette.responses import FileResponse, JSONResponse, Response as StarletteResponse
from starlette.responses import StreamingResponse


def jsonify(*args: Any, **kwargs: Any) -> JSONResponse:
    """Build a JSON response. Supports ``jsonify(data, 401)`` (status as second positional)."""
    status_code = 200
    if len(args) >= 2 and isinstance(args[-1], int):
        status_code = args[-1]
        args = args[:-1]
    if len(args) == 1 and isinstance(args[0], (dict, list)):
        content: Any = args[0]
    elif args or kwargs:
        if args:
            raise TypeError("jsonify received unexpected positional arguments.")
        content = kwargs
    else:
        content = {}
    return JSONResponse(content=jsonable_encoder(content), status_code=status_code)


class Response:
    """Flask-like Response factory (plain, streaming iterable, or bytes/str)."""

    def __new__(
        cls,
        content: Any = None,
        status: int = 200,
        headers: Optional[Mapping[str, str]] = None,
        mimetype: Optional[str] = None,
        content_type: Optional[str] = None,
        direct_passthrough: bool = False,
    ) -> StarletteResponse:
        _ = direct_passthrough
        media_type = content_type or mimetype
        hdrs = dict(headers or {})
        if hasattr(content, "__iter__") and not isinstance(content, (str, bytes, memoryview, dict)):
            return StreamingResponse(
                content,
                status_code=status,
                headers=hdrs,
                media_type=media_type,
            )
        if isinstance(content, str):
            body = content.encode("utf-8")
            enc_media = media_type or "text/plain; charset=utf-8"
        elif content is None:
            body = b""
            enc_media = media_type
        else:
            body = content
            enc_media = media_type
        return StarletteResponse(content=body, status_code=status, headers=hdrs, media_type=enc_media)


def _send_file_bytes_body(
    body: bytes,
    *,
    mimetype: Optional[str],
    as_attachment: bool,
    fname: Optional[str],
) -> StarletteResponse:
    headers: dict[str, str] = {}
    if fname:
        disp = "attachment" if as_attachment else "inline"
        safe = str(fname).replace('"', '\\"')
        headers["Content-Disposition"] = f'{disp}; filename="{safe}"'
    return StarletteResponse(
        content=body,
        media_type=mimetype or "application/octet-stream",
        headers=headers,
    )


def _send_file_infer_bytes(path_or_file: Any) -> bytes:
    if isinstance(path_or_file, (bytes, bytearray, memoryview)):
        return bytes(path_or_file)
    if isinstance(path_or_file, io.BytesIO):
        return path_or_file.getvalue()
    read = getattr(path_or_file, "read", None)
    if callable(read):
        chunk = read()
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("send_file: file.read() must return bytes")
        return bytes(chunk)
    raise TypeError(f"send_file: unsupported first argument type {type(path_or_file)!r}")


def send_file(
    path_or_file: Union[str, os.PathLike[str], bytes, bytearray, memoryview, BinaryIO],
    mimetype: Optional[str] = None,
    as_attachment: bool = False,
    download_name: Optional[str] = None,
    attachment_filename: Optional[str] = None,
    conditional: bool = True,
    etag: Union[bool, str] = True,
    last_modified: Optional[Any] = None,
    max_age: Optional[int] = None,
    cache_timeout: Optional[int] = None,
) -> StarletteResponse:
    fname = download_name or attachment_filename
    _ = (conditional, etag, last_modified, max_age, cache_timeout)
    if isinstance(path_or_file, (str, os.PathLike)):
        return FileResponse(
            os.fspath(path_or_file),
            media_type=mimetype,
            filename=fname if as_attachment else None,
            content_disposition_type="attachment" if as_attachment else "inline",
        )
    body = _send_file_infer_bytes(path_or_file)
    return _send_file_bytes_body(body, mimetype=mimetype, as_attachment=as_attachment, fname=fname)
