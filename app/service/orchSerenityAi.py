from fastapi import HTTPException
import logging
import httpx
import json
from app.core.config import settings

logger = logging.getLogger(__name__)


async def forward_to_n8n(http: httpx.AsyncClient, session_id: str, text: str) -> dict:
    """Forward plain payload to n8n webhook and normalize common n8n response shapes.

    n8n often returns an array of execution results like [{"json": {...}}].
    This function will attempt to extract a usable dict (the inner `json`) or
    return a reasonable fallback containing raw text.
    """
    if not settings.N8N_WEBHOOK_URL:
        raise HTTPException(500, "N8N_WEBHOOK_URL not set")

    headers = {"content-type": "application/json"}
    if settings.N8N_INTERNAL_TOKEN:
        headers["X-Internal-Token"] = settings.N8N_INTERNAL_TOKEN

    payload = {"session_id": session_id, "text": text}

    resp = await http.post(settings.N8N_WEBHOOK_URL, headers=headers, json=payload)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, f"n8n error: {resp.text}")

    # Try to parse JSON and normalize common n8n shapes
    try:
        data = resp.json()
    except Exception:
        logger.debug("n8n non-json response: %s", resp.text)
        return {"raw": resp.text}

    # n8n often returns a list like [{"json": {...}}]
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            # preferred: { json: {...} }
            if "json" in first and isinstance(first["json"], dict):
                return first["json"]
            # fallback: maybe the dict already contains fields
            return first

    # Special-case: some n8n flows return a Set-like structure where values are
    # grouped by type under `values`, e.g.:
    # { 'keepOnlySet': True, 'values': { 'string':[{'name':'text','value':...}], 'boolean':[...], 'json':[...]} }
    if isinstance(data, dict):
        vals = data.get("values")
        if isinstance(vals, dict):
            normalized = {}
            for vtype, entries in vals.items():
                if not isinstance(entries, list):
                    continue
                for e in entries:
                    name = e.get("name")
                    val = e.get("value")
                    if name is None:
                        continue
                    if vtype == "json":
                        try:
                            normalized[name] = json.loads(val)
                        except Exception:
                            normalized[name] = val
                    elif vtype == "boolean":
                        # n8n may use truthy values; normalize to bool
                        normalized[name] = bool(val)
                    else:
                        normalized[name] = val
            if normalized:
                return normalized
        return data

    # anything else, include both raw text and parsed form for debugging
    logger.debug("n8n returned unexpected shape: %r", data)
    return {"raw": resp.text, "parsed": data}