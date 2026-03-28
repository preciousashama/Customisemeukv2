
import io
import logging
import os
import uuid
import firebase_admin
from firebase_admin import credentials, storage as fb_storage
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

logger = logging.getLogger(__name__)




def _build_credentials():
    """Build Firebase credentials from env vars or JSON fallback."""
    private_key = os.getenv("FIREBASE_PRIVATE_KEY", "").strip()

    if private_key:
        # .env stores \n as literal backslash-n — convert to real newlines
        private_key = private_key.replace("\\n", "\n")
        info = {
            "type":                        "service_account",
            "project_id":                  os.getenv("FIREBASE_PROJECT_ID", ""),
            "private_key_id":              os.getenv("FIREBASE_PRIVATE_KEY_ID", ""),
            "private_key":                 private_key,
            "client_email":                os.getenv("FIREBASE_CLIENT_EMAIL", ""),
            "client_id":                   os.getenv("FIREBASE_CLIENT_ID", ""),
            "auth_uri":                    "https://accounts.google.com/o/oauth2/auth",
            "token_uri":                   "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url":        os.getenv("FIREBASE_CLIENT_CERT_URL", ""),
            "universe_domain":             "googleapis.com",
        }
        missing = [k for k in ("project_id", "private_key", "client_email") if not info[k]]
        if missing:
            raise ImproperlyConfigured(
                f"Firebase credentials incomplete. Missing env vars: "
                f"{', '.join('FIREBASE_' + k.upper() for k in missing)}"
            )
        return credentials.Certificate(info)

    # Fallback: local JSON key file (for development)
    json_path = getattr(settings, "FIREBASE_CREDENTIALS_JSON", None)
    if json_path and os.path.isfile(str(json_path)):
        return credentials.Certificate(str(json_path))

    raise ImproperlyConfigured(
        "Firebase Storage: no credentials found.\n"
        "Option A — set these in .env:\n"
        "  FIREBASE_PRIVATE_KEY, FIREBASE_PROJECT_ID, FIREBASE_CLIENT_EMAIL, etc.\n"
        "Option B — place firebase-credentials.json in your project root."
    )


def _get_bucket():
    """Initialise Firebase app once per process, then return the bucket."""
    if not firebase_admin._apps:
        bucket = getattr(settings, "FIREBASE_STORAGE_BUCKET", "").strip()
        if not bucket:
            raise ImproperlyConfigured(
                "FIREBASE_STORAGE_BUCKET is empty. "
                "Set it to your-project-id.appspot.com in .env"
            )
        cred = _build_credentials()
        firebase_admin.initialize_app(cred, {"storageBucket": bucket})
        logger.info("Firebase Storage ready — bucket: %s", bucket)
    return fb_storage.bucket()



@deconstructible
class FirebaseStorage(Storage):
    """
    Django storage backend that saves files to Firebase Cloud Storage
    and serves them via their public Firebase URL.

    Usage in settings.py:
        DEFAULT_FILE_STORAGE = "customiseapp.firebase_storage.FirebaseStorage"
    """

    def __init__(self, location="media"):
        self.location = location.strip("/")

    # ── Internal helpers ──────────────────────────────────────

    def _blob_name(self, name):
        # Normalise any Windows backslashes
        name = name.replace("\\", "/").strip("/")
        if self.location:
            return f"{self.location}/{name}"
        return name

    def _get_blob(self, name):
        return _get_bucket().blob(self._blob_name(name))

    # ── Core Storage interface ────────────────────────────────

    def _save(self, name, content):
        """
        Called by Django when an image is assigned to an ImageField and
        the model is saved. Uploads to Firebase and returns the stored
        filename. Django writes this filename to the DB column.

        Returns the filename (e.g. "products/abc123.jpg"), NOT the full URL.
        The url() method converts this to a Firebase HTTPS URL when needed.
        """
        # Normalise path separators (Windows safety)
        name = name.replace("\\", "/")

        # Preserve upload_to subdirectory (e.g. "products/") but use a UUID filename
        slash = name.rfind("/")
        directory  = name[:slash + 1] if slash != -1 else ""   # "products/" or ""
        ext        = os.path.splitext(name)[1].lower()          # ".jpg"
        unique_name = f"{directory}{uuid.uuid4().hex}{ext}"     # "products/abc123.jpg"

        blob_path = self._blob_name(unique_name)

        try:
            blob = _get_bucket().blob(blob_path)
            content.seek(0)
            ct = getattr(content, "content_type", None) or "application/octet-stream"
            blob.upload_from_file(content, content_type=ct)
            blob.make_public()                  # makes the file publicly readable
        except Exception as exc:
            logger.error("Firebase upload FAILED: %s → %s | %s", name, blob_path, exc)
            raise SuspiciousFileOperation(
                f"Firebase upload failed for '{name}': {exc}\n"
                f"Check FIREBASE_* vars and FIREBASE_STORAGE_BUCKET in .env."
            ) from exc

        logger.info(
            "Firebase upload OK: %s → %s",
            unique_name, blob.public_url,
        )
        return unique_name   # ← stored in DB column, NOT the full URL

    def _open(self, name, mode="rb"):
        blob = self._get_blob(name)
        buf  = io.BytesIO()
        blob.download_to_file(buf)
        buf.seek(0)
        return buf

    def exists(self, name):
        try:
            return self._get_blob(name).exists()
        except Exception:
            return False

    def url(self, name):
        """
        Returns the public Firebase URL for the stored file.
        Called by {{ product.image.url }} in templates.

        name = what was returned by _save() = e.g. "products/abc123.jpg"
        Returns: https://storage.googleapis.com/BUCKET/media/products/abc123.jpg
        """
        if not name:
            raise ValueError(
                "FirebaseStorage.url() received an empty name. "
                "The image was not saved correctly to Firebase."
            )
        name = name.replace("\\", "/")  # Windows safety
        return self._get_blob(name).public_url

    def delete(self, name):
        """Delete a file from Firebase. Called by image.delete(save=False)."""
        if not name:
            return
        try:
            blob = self._get_blob(name)
            if blob.exists():
                blob.delete()
                logger.info("Firebase deleted: %s", name)
        except Exception as exc:
            logger.warning("Firebase delete failed for '%s': %s", name, exc)

    def size(self, name):
        blob = self._get_blob(name)
        blob.reload()
        return blob.size or 0

    def listdir(self, path):
        blobs = _get_bucket().list_blobs(prefix=self._blob_name(path))
        return [], [os.path.basename(b.name) for b in blobs]