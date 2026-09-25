"""HTTP client. Requests run only outside an active camera sampling window."""
import json
import os
import urllib.request
import urllib.error
from urllib.parse import urlsplit
from uuid import UUID


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def validate_url(url):
    parsed = urlsplit(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use an HTTP(S) digital twin URL without credentials, query or fragment")


def describe_http_error(error, url, key):
    """Keep HTTP status/retry semantics; expose bounded API detail, not input/headers."""
    detail = "No JSON error detail returned"
    try:
        body = json.loads(error.read(8192))
        value = body.get("detail") if isinstance(body, dict) else None
        if isinstance(value, str):
            detail = value
        elif isinstance(value, list):
            detail = "; ".join(
                f"{'.'.join(map(str, item.get('loc', [])))}: {item.get('msg', 'invalid value')}"
                for item in value[:8] if isinstance(item, dict)) or detail
    except (ValueError, OSError):
        pass
    if key:
        detail = detail.replace(key, "[redacted]")
    detail = " ".join(detail.split())[:1000]
    hint = ""
    if detail == "Product type has no qc_variant_mapping":
        hint = "; configure the product type's A-D variant in the digital twin (GET /qc/variants; admin PUT /qc/variants/{product_type_id})"
    error.msg = f"POST {urlsplit(url).path}: {detail}{hint}"


def post_json(url, payload, headers=None):
    validate_url(url)
    key = os.environ.get("QC_API_KEY")
    if not key:
        raise ValueError("Set QC_API_KEY to the digital twin's INBOUND_API_KEY")
    request = urllib.request.Request(url, method="POST",
        data=json.dumps(payload, allow_nan=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": key, **(headers or {})})
    try:
        response = urllib.request.build_opener(NoRedirect).open(request, timeout=5)
    except urllib.error.HTTPError as error:
        try:
            describe_http_error(error, url, key)
        finally:
            error.close()
        raise
    with response as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected digital twin response: {response.status}")
        data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("Digital twin response is too large")
        return json.loads(data)


class TwinClient:
    def __init__(self, url, station_id):
        validate_url(url)
        if not os.environ.get("QC_API_KEY"):
            raise ValueError("Set QC_API_KEY for digital twin integration")
        self.url = url.rstrip("/")
        self.station_id = station_id

    @property
    def endpoint(self):
        return self.url + "/qc/results"

    def claim(self):
        result = post_json(self.url + "/qc/claim", {"station_id": self.station_id})
        if result is None:
            return None
        if not isinstance(result, dict) or result.get("station_id") != self.station_id or result.get("expected_variant") not in ("A", "B", "C", "D"):
            raise ValueError("Invalid digital twin inspection context")
        for key in ("product_instance_id", "order_id", "arrival_event_id"):
            if type(result.get(key)) is not int or result[key] < 1:
                raise ValueError(f"Invalid digital twin context: {key}")
        result["inspection_id"] = str(UUID(result["inspection_id"]))
        return result
