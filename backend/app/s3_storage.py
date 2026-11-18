"""Private S3 object storage helpers.

Policy: the database stores only S3 object *keys*. Authenticated API responses
hand out short-lived presigned GET URLs generated from those keys. Permanent
public S3 URLs are never stored or returned.
"""
import logging
from typing import Optional
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

# Default lifetime of a presigned GET URL returned by the API.
DEFAULT_URL_EXPIRY = 3600

_client_cache: dict = {}


def get_s3_client(settings):
    import boto3

    region = settings.AWS_REGION
    if region not in _client_cache:
        _client_cache[region] = boto3.client("s3", region_name=region)
    return _client_cache[region]


def object_key(value: Optional[str]) -> Optional[str]:
    """Normalize a stored value or client-supplied value to a bare S3 object key.

    Accepts a bare key, a legacy permanent S3 URL, or a presigned URL (e.g. one the
    frontend echoes back on update) and returns just the key.
    """
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    if v.startswith(("http://", "https://")):
        parsed = urlparse(v)
        path = unquote(parsed.path).lstrip("/")
        host = (parsed.hostname or "").lower()
        # Path-style URL (s3.<region>.amazonaws.com/<bucket>/<key>): drop the bucket segment.
        if host.startswith("s3.") or host.startswith("s3-") or host == "s3.amazonaws.com":
            path = path.split("/", 1)[1] if "/" in path else ""
        return path or None
    return v.lstrip("/")


def presigned_get_url(
    settings, value: Optional[str], expiry: int = DEFAULT_URL_EXPIRY
) -> Optional[str]:
    """Return a temporary presigned GET URL for a stored key (or legacy URL).

    Returns None (never a permanent public URL) if no key is stored or signing fails.
    """
    key = object_key(value)
    if not key or not settings.AWS_S3_BUCKET_NAME:
        return None
    try:
        return get_s3_client(settings).generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_S3_BUCKET_NAME, "Key": key},
            ExpiresIn=expiry,
        )
    except Exception:
        logger.warning("Failed to generate presigned URL for key %s", key)
        return None
