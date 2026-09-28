"""
File storage for stone photos and videos.

Two backends with the same interface:
  - SupabaseStorage: used when SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are
    set. Files live in a public Supabase Storage bucket. Browsers upload
    straight to Supabase with a short-lived signed URL, so large videos never
    pass through the (small) app server.
  - LocalStorage: local dev and tests. Files are written under MEDIA_DIR and
    served by the app at /media-files/. Uploads go to a signed app endpoint
    that mimics Supabase's signed upload URLs.

Only paths (e.g. "items/12/3f2a.jpg") are stored in the database; public
URLs are derived at read time, so switching backends doesn't break rows.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
import jwt

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # Supabase free plan per-file limit
UPLOAD_URL_TTL = timedelta(hours=2)

IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
VIDEO_TYPES = {"video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm"}
ALLOWED_TYPES = {**IMAGE_TYPES, **VIDEO_TYPES}
DOCUMENT_TYPES = {"application/pdf": "pdf"}
CERTIFICATE_TYPES = {**IMAGE_TYPES, **DOCUMENT_TYPES}
# Everything the bucket accepts.
BUCKET_TYPES = {**ALLOWED_TYPES, **DOCUMENT_TYPES}

LOCAL_MEDIA_URL_PREFIX = "/media-files"


class StorageError(Exception):
    pass


class LocalStorage:
    name = "local"

    def __init__(self, root: Path, secret_fn):
        self.root = root
        self._secret_fn = secret_fn

    def ensure_ready(self):
        self.root.mkdir(parents=True, exist_ok=True)

    def _file(self, path: str) -> Path:
        full = (self.root / path).resolve()
        if self.root.resolve() not in full.parents:
            raise StorageError("Invalid path")
        return full

    def create_upload(self, path: str, content_type: str):
        token = jwt.encode(
            {
                "path": path,
                "ct": content_type,
                "exp": datetime.now(timezone.utc) + UPLOAD_URL_TTL,
            },
            self._secret_fn(),
            algorithm="HS256",
        )
        # Relative to the API origin; the frontend prefixes API_URL.
        return {"url": f"/api/admin/local-upload?token={token}", "method": "PUT"}

    def read_upload_token(self, token: str):
        try:
            payload = jwt.decode(token, self._secret_fn(), algorithms=["HS256"])
        except jwt.PyJWTError:
            raise StorageError("Upload link expired or invalid")
        return payload["path"], payload["ct"]

    def write(self, path: str, chunks):
        target = self._file(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with open(target, "wb") as f:
            for chunk in chunks:
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    f.close()
                    target.unlink(missing_ok=True)
                    raise StorageError("File is larger than 50 MB")
                f.write(chunk)
        return size

    def exists(self, path: str) -> bool:
        return self._file(path).is_file()

    def read(self, path: str) -> bytes:
        try:
            return self._file(path).read_bytes()
        except OSError as exc:
            raise StorageError(f"Couldn't read {path}") from exc

    def put(self, path: str, data: bytes, content_type: str):
        target = self._file(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def public_url(self, path: str) -> str:
        return f"{LOCAL_MEDIA_URL_PREFIX}/{quote(path)}"

    def delete(self, paths):
        for path in paths:
            try:
                self._file(path).unlink(missing_ok=True)
            except StorageError:
                pass


class SupabaseStorage:
    name = "supabase"

    def __init__(self, base_url: str, key: str, bucket: str):
        # Only the project origin matters. People often paste the Data API
        # URL (https://<ref>.supabase.co/rest/v1), which would send storage
        # calls to the database API instead.
        parsed = urlparse(base_url.strip())
        if parsed.scheme and parsed.netloc:
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        self.base_url = base_url.rstrip("/")
        self.api = f"{self.base_url}/storage/v1"
        self.bucket = bucket
        # New-style secret keys (sb_secret_...) go in the apikey header only;
        # legacy service_role keys are JWTs and also go in Authorization.
        self.headers = {"apikey": key}
        if not key.startswith("sb_"):
            self.headers["Authorization"] = f"Bearer {key}"
        self._client = httpx.Client(timeout=20, headers=self.headers)

    def _request(self, method, url, **kwargs):
        try:
            res = self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise StorageError(f"Couldn't reach Supabase Storage: {exc}") from exc
        return res

    def _bucket_settings(self):
        return {
            "public": True,
            "file_size_limit": MAX_UPLOAD_BYTES,
            "allowed_mime_types": sorted(BUCKET_TYPES),
        }

    def ensure_ready(self):
        """Create the public bucket if it doesn't exist yet, and widen its
        allowed file types when new ones are added (e.g. PDF certificates)."""
        res = self._request("GET", f"{self.api}/bucket/{self.bucket}")
        if res.status_code == 200:
            allowed = set(res.json().get("allowed_mime_types") or [])
            if allowed and not set(BUCKET_TYPES) <= allowed:
                upd = self._request(
                    "PUT", f"{self.api}/bucket/{self.bucket}", json=self._bucket_settings()
                )
                if upd.status_code != 200:
                    raise StorageError(f"Couldn't update bucket ({upd.status_code}): {upd.text[:200]}")
                logger.info("Updated allowed file types on bucket %s", self.bucket)
            return
        res = self._request(
            "POST",
            f"{self.api}/bucket",
            json={"id": self.bucket, "name": self.bucket, **self._bucket_settings()},
        )
        if res.status_code not in (200, 201) and "already exists" not in res.text.lower():
            raise StorageError(f"Couldn't create bucket ({res.status_code}): {res.text[:200]}")
        logger.info("Created Supabase Storage bucket %s", self.bucket)

    def create_upload(self, path: str, content_type: str):
        res = self._request(
            "POST", f"{self.api}/object/upload/sign/{self.bucket}/{quote(path)}"
        )
        if res.status_code != 200:
            raise StorageError(f"Couldn't create upload link ({res.status_code}): {res.text[:200]}")
        signed = res.json()["url"]  # "/object/upload/sign/<bucket>/<path>?token=..."
        return {"url": f"{self.api}{signed}", "method": "PUT"}

    def exists(self, path: str) -> bool:
        res = self._request("HEAD", self.public_url(path))
        return res.status_code == 200

    def read(self, path: str) -> bytes:
        res = self._request("GET", self.public_url(path))
        if res.status_code != 200:
            raise StorageError(f"Couldn't read {path} ({res.status_code})")
        return res.content

    def put(self, path: str, data: bytes, content_type: str):
        res = self._request(
            "POST",
            f"{self.api}/object/{self.bucket}/{quote(path)}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )
        if res.status_code not in (200, 201):
            raise StorageError(f"Couldn't save {path} ({res.status_code}): {res.text[:200]}")

    def public_url(self, path: str) -> str:
        return f"{self.api}/object/public/{self.bucket}/{quote(path)}"

    def delete(self, paths):
        paths = [p for p in paths if p]
        if not paths:
            return
        res = self._request("DELETE", f"{self.api}/object/{self.bucket}", json={"prefixes": paths})
        if res.status_code not in (200, 204):
            logger.warning("Couldn't delete media %s: %s %s", paths, res.status_code, res.text[:200])


_storage = None


def get_storage():
    global _storage
    if _storage is None:
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if url and key:
            bucket = os.environ.get("SUPABASE_BUCKET", "stone-media").strip()
            _storage = SupabaseStorage(url, key, bucket)
        else:
            import auth  # local import: auth imports database, not storage

            root = Path(os.environ.get("MEDIA_DIR", Path(__file__).parent / "uploads"))
            _storage = LocalStorage(root, auth._jwt_secret)
    return _storage


def reset_storage():
    global _storage
    _storage = None
