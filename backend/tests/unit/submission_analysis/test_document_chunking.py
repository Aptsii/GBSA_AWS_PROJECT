from __future__ import annotations

import hashlib

from interview_evidence.shared.aws_clients.ports import ProtectedBytes
from interview_evidence.submission_analysis.domain.source import SourceLocation
from interview_evidence.workers.analysis.document_chunker import DocumentChunker
from interview_evidence.workers.analysis.document_extract import DocumentExtractor


def test_document_extraction_and_chunking_preserve_locations_and_hashes() -> None:
    content = (
        "# 프로젝트 경험\n\n결제 장애를 분석했습니다.\n\n# 기술 선택\n\nPostgreSQL을 선택했습니다."
    )
    extracted = DocumentExtractor().extract(
        ProtectedBytes(content.encode()), media_type="text/markdown"
    )
    chunks = DocumentChunker(max_characters=32, overlap_characters=8).chunk(extracted)

    assert extracted.content_hash == hashlib.sha256(content.encode()).hexdigest()
    assert len(chunks) >= 2
    assert all(chunk.source_hash == extracted.content_hash for chunk in chunks)
    assert all(
        chunk.chunk_hash == hashlib.sha256(chunk.text.reveal().encode()).hexdigest()
        for chunk in chunks
    )
    assert chunks[0].location == SourceLocation(page=1, section="프로젝트 경험", start_offset=0)


def test_chunking_is_deterministic_for_the_same_source() -> None:
    content = ProtectedBytes("첫 문단입니다.\n\n두 번째 문단입니다.".encode())
    extractor = DocumentExtractor()
    chunker = DocumentChunker(max_characters=20, overlap_characters=4)

    first = chunker.chunk(extractor.extract(content, media_type="text/plain"))
    second = chunker.chunk(extractor.extract(content, media_type="text/plain"))

    assert first == second
