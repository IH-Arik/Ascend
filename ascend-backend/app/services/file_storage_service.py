"""Local-disk encrypted file storage, shared by medical record uploads
(DOCX section 8.8) and message attachments (DOCX section 10, Messaging).

Explicit, honest scope limits:
- **Storage backend is local disk**, not S3/GCS/Azure Blob - a real decision
  made for this dev/prototype pass. Migrating to cloud object storage later
  only requires swapping this service's implementation; nothing above it
  (the medical-records service/routes) needs to change.
- **Encryption at rest is real** (Fernet/AES via the `cryptography` package),
  keyed off `settings.secret_key` - so it rotates together with the same
  `SECRET_KEY` already flagged elsewhere in this project as an unrotated
  placeholder that needs a real value before production.
- **Malware scanning is explicitly a stub, not a real AV integration.**
  `scan_file_stub` only rejects a short list of obviously executable file
  extensions - it is not a substitute for a real scanning service (e.g.
  ClamAV, a cloud AV API) and must not be represented as one.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

from app.core.config import get_settings

BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".sh", ".dll", ".msi", ".ps1"}

CONTENT_TYPE_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".dcm": "application/dicom",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".heic": "image/heic",
}


def guess_content_type(file_name: str) -> str:
    """Return a real MIME type for a known extension, else a generic fallback."""
    return CONTENT_TYPE_BY_EXTENSION.get(Path(file_name).suffix.lower(), "application/octet-stream")


def _get_fernet() -> Fernet:
    """Derive a Fernet key from the app's SECRET_KEY (rotates together)."""
    settings = get_settings()
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def scan_file_stub(file_name: str) -> bool:
    """Return True if the file passes the (stub) malware/type check.

    NOT a real antivirus scan - only blocks a short list of executable
    extensions. Real malware scanning is not implemented in this project.
    """
    return Path(file_name).suffix.lower() not in BLOCKED_EXTENSIONS


class FileStorageService:
    """Save and read encrypted files on local disk.

    `namespace` picks the subdirectory under the shared storage root so
    different callers (medical records, message attachments) never collide,
    while reusing the same encryption/malware-stub logic and the same
    "swap this one service to migrate to cloud storage" scope limit.
    """

    def __init__(self, namespace: str = "medical_records") -> None:
        settings = get_settings()
        self.base_dir = Path(settings.medical_record_storage_dir).parent / namespace
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_file(self, user_id: str, file_name: str, content: bytes) -> str:
        """Encrypt and write a file to disk; return its relative storage path."""
        user_dir = self.base_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}_{Path(file_name).name}.enc"
        target_path = user_dir / stored_name

        encrypted = _get_fernet().encrypt(content)
        target_path.write_bytes(encrypted)
        return str(target_path.relative_to(self.base_dir))

    def read_file(self, storage_path: str) -> bytes:
        """Read and decrypt a file from disk."""
        target_path = self.base_dir / storage_path
        encrypted = target_path.read_bytes()
        return _get_fernet().decrypt(encrypted)
