from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import ClassVar
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from interview_evidence.submission_analysis.domain.submission import SourceType

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9가-힣._ -]+")
_SECRET_QUERY_KEYS = {"access_token", "api_key", "apikey", "password", "secret", "token"}


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    source_type: SourceType
    filename: str
    media_type: str
    byte_size: int
    sha256: str


class SubmissionValidator:
    __slots__ = ("_max_file_bytes",)

    _ALLOWED_MEDIA: ClassVar[dict[SourceType, set[str]]] = {
        SourceType.COVER_LETTER: {"text/plain", "text/markdown", "application/pdf"},
        SourceType.RESUME: {"text/plain", "text/markdown", "application/pdf"},
        SourceType.PDF: {"application/pdf"},
    }

    def __init__(self, *, max_file_bytes: int = 25 * 1024 * 1024) -> None:
        if max_file_bytes < 1:
            raise ValueError("maximum file size must be positive")
        self._max_file_bytes = max_file_bytes

    def validate_upload(
        self,
        *,
        source_type: str | SourceType,
        filename: str,
        media_type: str,
        byte_size: int,
        sha256: str,
    ) -> ValidatedUpload:
        checked_type = SourceType(source_type)
        if checked_type not in self._ALLOWED_MEDIA:
            raise ValueError("URL submissions do not use upload intents")
        if not 1 <= byte_size <= self._max_file_bytes:
            raise ValueError("file size exceeds the configured limit")
        checked_media = media_type.casefold().strip()
        if checked_media not in self._ALLOWED_MEDIA[checked_type]:
            raise ValueError("media type is not allowed for this source type")
        if not _SHA256.fullmatch(sha256):
            raise ValueError("sha256 must be a lowercase digest")
        checked_filename = self.sanitize_filename(filename)
        return ValidatedUpload(
            source_type=checked_type,
            filename=checked_filename,
            media_type=checked_media,
            byte_size=byte_size,
            sha256=sha256,
        )

    def validate_public_url(self, value: str, *, git_only: bool = False) -> str:
        parsed = urlsplit(value.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("public sources require an HTTPS URL")
        if parsed.username or parsed.password:
            raise ValueError("source URLs cannot contain credentials")
        host = parsed.hostname.casefold().rstrip(".")
        if host == "localhost" or host.endswith(".localhost") or self._is_non_public_ip(host):
            raise ValueError("source URL must resolve to a public host")
        query = parse_qsl(parsed.query, keep_blank_values=True)
        if any(key.casefold() in _SECRET_QUERY_KEYS for key, _ in query):
            raise ValueError("source URL cannot contain secret query parameters")
        if git_only and host not in {"github.com", "gitlab.com", "bitbucket.org"}:
            raise ValueError("v1 supports public Git hosting providers only")
        return urlunsplit(("https", host, parsed.path.rstrip("/"), parsed.query, ""))

    @staticmethod
    def sanitize_filename(value: str) -> str:
        name = PurePath(value).name.strip()
        name = _SAFE_FILENAME.sub("_", name)
        if not name or len(name) > 255:
            raise ValueError("filename is invalid")
        return name

    @staticmethod
    def _is_non_public_ip(host: str) -> bool:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return False
        return not address.is_global
