from __future__ import annotations

import io
import json
from datetime import UTC, datetime

from interview_evidence.shared.ids import FixedClock
from interview_evidence.shared.metrics import (
    METRIC_NAMESPACE,
    METRIC_SCHEMA_VERSION,
    CloudWatchEmfMetricSink,
    MetricBoundary,
    MetricName,
    OperationalMetrics,
    extract_operational_signals,
)


def test_versioned_operational_metrics_render_cloudwatch_emf_without_tenant_dimensions() -> None:
    stream = io.StringIO()
    metrics = OperationalMetrics(
        CloudWatchEmfMetricSink(stream),
        clock=FixedClock(datetime(2026, 8, 17, 9, 0, tzinfo=UTC)),
    )

    metrics.record_stage_latency(
        boundary=MetricBoundary.API,
        stage="interview",
        operation_version="api-v1",
        elapsed_ms=125.5,
        result="succeeded",
    )
    metrics.record_retry(
        boundary=MetricBoundary.WORKER,
        stage="submission.analysis_requested",
        operation_version="event-v1",
    )
    metrics.record_reconciliation_lag(
        boundary=MetricBoundary.WORKER,
        stage="submission.analysis_requested",
        operation_version="event-v1",
        lag_ms=900,
    )
    metrics.record_queue_age(
        stage="submission.analysis_requested",
        operation_version="event-v1",
        age_ms=1_500,
    )
    metrics.record_degraded_mode(
        boundary=MetricBoundary.API,
        stage="interview",
        operation_version="api-v1",
        mode="search_fallback",
    )

    payloads = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert {payload["MetricName"] for payload in payloads} == {
        metric.value for metric in MetricName
    }
    assert all(payload["MetricSchemaVersion"] == METRIC_SCHEMA_VERSION for payload in payloads)
    assert all(
        payload["_aws"]["CloudWatchMetrics"][0]["Namespace"] == METRIC_NAMESPACE
        for payload in payloads
    )
    assert all("company_id" not in json.dumps(payload).casefold() for payload in payloads)


def test_operational_signal_extraction_reads_only_bounded_metric_fields() -> None:
    signals = extract_operational_signals(
        {
            "degraded_modes": ["search_fallback", "text_only"],
            "retry_count": 2,
            "reconciliation_lag_ms": 875,
            "signed_url": "https://secret.invalid/value",
            "answer_text": "protected applicant answer",
        }
    )

    assert signals.degraded_modes == ("search_fallback", "text_only")
    assert signals.retry_count == 2
    assert signals.reconciliation_lag_ms == 875
