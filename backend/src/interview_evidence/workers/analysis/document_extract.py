from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from interview_evidence.shared.aws_clients.ports import ProtectedBytes, ProtectedText

_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")


@dataclass(frozen=True, slots=True)
class ExtractedSection:
    page: int
    title: str | None
    text: ProtectedText
    start_offset: int


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    content_hash: str
    media_type: str
    sections: tuple[ExtractedSection, ...]


class DocumentExtractor:
    __slots__ = ()

    def extract(self, content: ProtectedBytes, *, media_type: str) -> ExtractedDocument:
        raw = content.reveal()
        if media_type not in {"text/plain", "text/markdown", "application/pdf"}:
            raise ValueError("unsupported document media type")
        text = raw.decode("utf-8", errors="replace")
        pages = text.split("\f")
        sections: list[ExtractedSection] = []
        offset = 0
        for page_number, page in enumerate(pages, start=1):
            current_title: str | None = None
            buffer: list[str] = []
            section_offset = offset
            for line in page.splitlines():
                heading = _HEADING.match(line)
                if heading:
                    self._append_section(
                        sections,
                        page_number,
                        current_title,
                        buffer,
                        section_offset,
                    )
                    current_title = heading.group(1).strip()
                    buffer = []
                    section_offset = offset
                else:
                    buffer.append(line)
                offset += len(line) + 1
            self._append_section(sections, page_number, current_title, buffer, section_offset)
        if not sections:
            sections.append(ExtractedSection(1, None, ProtectedText(""), 0))
        return ExtractedDocument(
            content_hash=hashlib.sha256(raw).hexdigest(),
            media_type=media_type,
            sections=tuple(sections),
        )

    @staticmethod
    def _append_section(
        sections: list[ExtractedSection],
        page: int,
        title: str | None,
        buffer: list[str],
        start_offset: int,
    ) -> None:
        value = "\n".join(buffer).strip()
        if value:
            sections.append(ExtractedSection(page, title, ProtectedText(value), start_offset))
