from __future__ import annotations

import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from interview_evidence.shared.ids import FixedClock
from interview_evidence.shared.metrics import CloudWatchEmfMetricSink, OperationalMetrics

INFRA_ROOT = Path(__file__).resolve().parents[1]


def _queue_alarm_attribute(name: str) -> str:
    configuration = (INFRA_ROOT / "modules/observability/main.tf").read_text(encoding="utf-8")
    resource = re.search(
        r'resource "aws_cloudwatch_metric_alarm" "queue_age" \{(?P<body>.*?)\n\}',
        configuration,
        re.DOTALL,
    )
    assert resource is not None
    attribute = re.search(rf'{name}\s*=\s*"(?P<value>[^"]+)"', resource.group("body"))
    assert attribute is not None
    return attribute.group("value")


def test_queue_age_emf_matches_terraform_alarm_contract() -> None:
    stream = io.StringIO()
    metrics = OperationalMetrics(
        CloudWatchEmfMetricSink(stream),
        clock=FixedClock(datetime(2026, 8, 17, 9, 0, tzinfo=UTC)),
    )

    metrics.record_queue_age(
        stage="submission.analysis_requested",
        operation_version="event-v1",
        age_ms=1_500,
    )

    payload = json.loads(stream.getvalue())
    emf_contract = payload["_aws"]["CloudWatchMetrics"][0]
    alarm_metric_name = _queue_alarm_attribute("metric_name")
    alarm_unit = _queue_alarm_attribute("unit")

    assert emf_contract["Namespace"] == _queue_alarm_attribute("namespace")
    assert emf_contract["Metrics"] == [
        {
            "Name": alarm_metric_name,
            "Unit": alarm_unit,
        }
    ]
    assert payload[alarm_metric_name] == 1.5
