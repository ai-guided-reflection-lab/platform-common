"""Canvas LTI 1.1 course-navigation launches, using ClubALL's shared sign-in."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, quote, urlencode, urlsplit
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import settings
from platform_app import lti, store

router = APIRouter(prefix="/api/lti", tags=["lti-1.1"])
LAUNCH_PATH = "/api/lti/1.1/launch"
TIMESTAMP_WINDOW = 300


def _https_origin(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return bool(
            parsed.scheme == "https" and parsed.hostname and not parsed.username
            and not parsed.password and not parsed.path and not parsed.query
            and not parsed.fragment and (parsed.port is None or parsed.port > 0)
        )
    except ValueError:
        return False


def enabled() -> bool:
    return bool(
        settings.LTI11_CONSUMER_KEY and settings.LTI11_SHARED_SECRET
        and _https_origin(settings.LTI_PUBLIC_BASE_URL)
        and _https_origin(settings.LTI_CANVAS_ISSUER)
    )


def _require_enabled():
    if not enabled():
        raise HTTPException(503, "Canvas LTI 1.1 is not configured on this server.")


def _digest(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def _verify(pairs: list[tuple[str, str]]) -> dict[str, str]:
    """Verify OAuth 1.0 per RFC 5849, signing all query and form parameters."""
    params = dict(pairs)
    if len(params) != len(pairs):
        raise HTTPException(400, "Duplicate Canvas launch parameters.")
    required = (
        "oauth_consumer_key", "oauth_signature", "oauth_timestamp", "oauth_nonce",
        "user_id", "context_id", "resource_link_id", "roles",
    )
    if any(not params.get(name, "").strip() for name in required):
        raise HTTPException(422, "Canvas launch is missing required parameters.")
    if (params.get("lti_message_type") != "basic-lti-launch-request"
            or params.get("lti_version") != "LTI-1p0"):
        raise HTTPException(422, "Expected an LTI 1.1 basic launch.")
    if (params.get("oauth_signature_method") != "HMAC-SHA1"
            or params.get("oauth_version", "1.0") != "1.0" or params.get("oauth_token")):
        raise HTTPException(401, "Unsupported Canvas OAuth parameters.")
    if not hmac.compare_digest(params["oauth_consumer_key"].encode(), settings.LTI11_CONSUMER_KEY.encode()):
        raise HTTPException(401, "Invalid Canvas consumer key.")
    try:
        timestamp = int(params["oauth_timestamp"])
    except ValueError:
        raise HTTPException(401, "Invalid Canvas launch timestamp.") from None
    if abs(time.time() - timestamp) > TIMESTAMP_WINDOW:
        raise HTTPException(401, "Canvas launch timestamp is expired or in the future.")

    def encode(value: str) -> str:
        return quote(value, safe="~-._")

    normalized = "&".join(f"{key}={value}" for key, value in sorted(
        (encode(key), encode(value)) for key, value in pairs if key != "oauth_signature"
    ))
    # Use the configured external URL; do not trust Host or forwarded headers.
    parsed = urlsplit(settings.LTI_PUBLIC_BASE_URL)
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    if parsed.port and parsed.port != 443:
        host += f":{parsed.port}"
    url = f"https://{host}{LAUNCH_PATH}"
    base = "&".join(encode(value) for value in ("POST", url, normalized))
    key = encode(settings.LTI11_SHARED_SECRET) + "&"
    expected = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest())
    if not hmac.compare_digest(expected, params["oauth_signature"].encode()):
        raise HTTPException(401, "Canvas launch signature could not be verified.")
    return params


def _claims(params: dict[str, str]) -> dict[str, object]:
    # LTI 1.1 roles may be short names or LIS URNs. Match exact known roles.
    roles = {value.strip() for value in params["roles"].split(",")}
    instructors = {"Instructor", "TeachingAssistant", "Administrator", "ContentDeveloper"}
    instructors |= {f"urn:lti:role:ims/lis/{role}" for role in ("Instructor", "TeachingAssistant", "ContentDeveloper")}
    instructors |= {"urn:lti:instrole:ims/lis/Administrator", "urn:lti:sysrole:ims/lis/Administrator"}
    if roles & instructors:
        role = "Instructor"
    elif roles & {"Learner", "Student", "urn:lti:role:ims/lis/Learner"}:
        role = "Learner"
    else:
        raise HTTPException(403, "Canvas did not provide a supported course role.")
    # Never trust a posted issuer or merge 1.1 context IDs with 1.3 IDs.
    registration = _digest(settings.LTI_CANVAS_ISSUER, settings.LTI11_CONSUMER_KEY)
    return {
        "iss": f"urn:cluball:lti11:{registration}",
        "sub": params["user_id"],
        "name": params.get("lis_person_name_full") or "Canvas user",
        "email": params.get("lis_person_contact_email_primary", ""),
        lti.ROLES_CLAIM: [role],
        lti.CONTEXT_CLAIM: {
            "id": params["context_id"],
            "label": params.get("context_label", "CANVAS"),
            "title": params.get("context_title", "Canvas course"),
        },
    }


def _consume_nonce(params: dict[str, str]):
    nonce_hash = _digest(settings.LTI_CANVAS_ISSUER, settings.LTI11_CONSUMER_KEY, params["oauth_nonce"])
    expires = int(params["oauth_timestamp"]) + TIMESTAMP_WINDOW + 1
    with store.connection() as conn:
        conn.execute("DELETE FROM lti11_nonces_platform WHERE expires_at < NOW()")
        inserted = conn.execute(
            """INSERT INTO lti11_nonces_platform (nonce_hash, expires_at)
               VALUES (%s, to_timestamp(%s)) ON CONFLICT DO NOTHING RETURNING nonce_hash""",
            (nonce_hash, expires),
        ).fetchone()
    if not inserted:
        raise HTTPException(401, "Canvas launch was already used. Launch again from Canvas.")


@router.get("/canvas-config.xml")
def canvas_configuration():
    _require_enabled()
    launch = escape(settings.LTI_PUBLIC_BASE_URL + LAUNCH_PATH)
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<cartridge_basiclti_link xmlns="http://www.imsglobal.org/xsd/imslticc_v1p0"
 xmlns:blti="http://www.imsglobal.org/xsd/imsbasiclti_v1p0"
 xmlns:lticm="http://www.imsglobal.org/xsd/imslticm_v1p0">
 <blti:title>ClubALL Learning Platform</blti:title>
 <blti:description>Course-grounded Socratic, reflection, and tutoring assignments.</blti:description>
 <blti:launch_url>{launch}</blti:launch_url>
 <blti:secure_launch_url>{launch}</blti:secure_launch_url>
 <blti:extensions platform="canvas.instructure.com">
  <lticm:property name="privacy_level">public</lticm:property>
  <lticm:options name="course_navigation">
   <lticm:property name="url">{launch}</lticm:property>
   <lticm:property name="text">ClubALL</lticm:property>
   <lticm:property name="enabled">true</lticm:property>
   <lticm:property name="default">enabled</lticm:property>
   <lticm:property name="windowTarget">_blank</lticm:property>
  </lticm:options>
 </blti:extensions>
</cartridge_basiclti_link>'''
    return Response(xml, media_type="application/xml")


@router.post("/1.1/launch")
async def launch(request: Request):
    _require_enabled()
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Expected a form-encoded Canvas launch.")
    # Bound parsing work and avoid accepting unsigned parameters in another source.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65536:
            raise HTTPException(413, "Canvas launch is too large.")
    try:
        pairs = parse_qsl(body.decode("utf-8"), keep_blank_values=True, max_num_fields=200, errors="strict")
        pairs += parse_qsl(request.url.query, keep_blank_values=True, max_num_fields=200, errors="strict")
    except (UnicodeError, ValueError):
        raise HTTPException(400, "Invalid Canvas launch encoding.") from None
    params = _verify(pairs)
    claims = _claims(params)
    _consume_nonce(params)
    code, course_id = lti._provision_launch(claims, deployment_id="lti11")
    response = RedirectResponse(
        f"/?{urlencode({'lti': 'verified', 'code': code, 'course': course_id})}", status_code=303,
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
