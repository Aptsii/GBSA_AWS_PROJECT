from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from time import perf_counter
from typing import Protocol, TextIO

from interview_evidence.shared.ids import Clock, SystemClock
from starlette.types import ASGIApp, Message, Receive, Scope, Send

METRIC_NAMESPACE = "InterviewEvidencePlatform"
METRIC_SCHEMA_VERSION = "1.0"
_MAX_CAPTURED_RESPONSE_BYTES = 65_536
_SAFE_DIMENSION = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")


class MetricName(StrEnum):
    STAGE_LATENCY = "StageLatencyMilliseconds"
    RETRY = "RetryCount"
    RECONCILIATION_LAG = "ReconciliationLagMilliseconds"
    QUEUE_AGE = "QueueAgeMilliseconds"
    DEGRADED_MODE = "DegradedModeCount"


class MetricBoundary(StrEnum):
    API = "api"
    WORKER = "worker"


class MetricUnit(StrEnum):
    COUNT = "Count"
    MILLISECONDS = "Milliseconds"


@dataclass(frozen=True, slots=True)
class OperationalMetric:
    name: MetricName
    value: float
    unit: MetricUnit
    boundary: MetricBoundary
    stage: str
    operation_version: str
    result: str
    mode: str
    observed_at: datetime

    def __post_init__(self) -> None:
        if not isfinite(self.value) or self.value < 0:
            raise ValueError("metric value must be finite and nonnegative")
        for field_name in ("stage", "operation_version", "result", "mode"):
            value = getattr(self, field_name)
            if not _safe_dimension(value):
                raise ValueError(f"{field_name} must be a bounded operational code")


class MetricSink(Protocol):
    def emit(self, metric: OperationalMetric) -> None: ...


class CloudWatchEmfMetricSink:
    __slots__ = ("_stream",)

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream

    def emit(self, metric: OperationalMetric) -> None:
        payload = {
            "_aws": {
                "Timestamp": int(metric.observed_at.timestamp() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": METRIC_NAMESPACE,
                        "Dimensions": [
                            [
                                "MetricSchemaVersion",
                                "Boundary",
                                "Stage",
                                "OperationVersion",
                                "Result",
                                "Mode",
                            ]
                        ],
                        "Metrics": [{"Name": metric.name.value, "Unit": metric.unit.value}],
                    }
                ],
            },
            "MetricSchemaVersion": METRIC_SCHEMA_VERSION,
            "MetricName": metric.name.value,
            "Boundary": metric.boundary.value,
            "Stage": metric.stage,
            "OperationVersion": metric.operation_version,
            "Result": metric.result,
            "Mode": metric.mode,
            metric.name.value: metric.value,
        }
        target = self._stream or sys.stdout
        target.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")
        target.flush()


class InMemoryMetricSink:
    __slots__ = ("metrics",)

    def __init__(self) -> None:
        self.metrics: list[OperationalMetric] = []

    def emit(self, metric: OperationalMetric) -> None:
        self.metrics.append(metric)


class OperationalMetrics:
    __slots__ = ("_clock", "_sink")

    def __init__(self, sink: MetricSink | None = None, *, clock: Clock | None = None) -> None:
        self._sink = sink or CloudWatchEmfMetricSink()
        self._clock = clock or SystemClock()

    def record_stage_latency(
        self,
        *,
        boundary: MetricBoundary,
        stage: str,
        operation_version: str,
        elapsed_ms: float,
        result: str,
    ) -> None:
        self._emit(
            MetricName.STAGE_LATENCY,
            elapsed_ms,
            MetricUnit.MILLISECONDS,
            boundary,
            stage,
            operation_version,
            result,
        )

    def record_retry(
        self,
        *,
        boundary: MetricBoundary,
        stage: str,
        operation_version: str,
        count: int = 1,
    ) -> None:
        self._emit(
            MetricName.RETRY,
            count,
            MetricUnit.COUNT,
            boundary,
            stage,
            operation_version,
            "retrying",
        )

    def record_reconciliation_lag(
        self,
        *,
        boundary: MetricBoundary,
        stage: str,
        operation_version: str,
        lag_ms: float,
    ) -> None:
        self._emit(
            MetricName.RECONCILIATION_LAG,
            lag_ms,
            MetricUnit.MILLISECONDS,
            boundary,
            stage,
            operation_version,
            "succeeded",
        )

    def record_queue_age(
        self,
        *,
        stage: str,
        operation_version: str,
        age_ms: float,
    ) -> None:
        self._emit(
            MetricName.QUEUE_AGE,
            age_ms,
            MetricUnit.MILLISECONDS,
            MetricBoundary.WORKER,
            stage,
            operation_version,
            "succeeded",
        )

    def record_degraded_mode(
        self,
        *,
        boundary: MetricBoundary,
        stage: str,
        operation_version: str,
        mode: str,
    ) -> None:
        self._emit(
            MetricName.DEGRADED_MODE,
            1,
            MetricUnit.COUNT,
            boundary,
            stage,
            operation_version,
            "degraded",
            mode=mode,
        )

    def _emit(
        self,
        name: MetricName,
        value: float,
        unit: MetricUnit,
        boundary: MetricBoundary,
        stage: str,
        operation_version: str,
        result: str,
        *,
        mode: str = "none",
    ) -> None:
        self._sink.emit(
            OperationalMetric(
                name=name,
                value=float(value),
                unit=unit,
                boundary=boundary,
                stage=stage,
                operation_version=operation_version,
                result=result,
                mode=mode,
                observed_at=self._clock.now(),
            )
        )


@dataclass(frozen=True, slots=True)
class OperationalSignals:
    degraded_modes: tuple[str, ...] = ()
    retry_count: int = 0
    reconciliation_lag_ms: float | None = None


def extract_operational_signals(value: object) -> OperationalSignals:
    degraded_modes: list[str] = []
    retry_count = 0
    reconciliation_lag_ms: float | None = None

    def visit(item: object) -> None:
        nonlocal retry_count, reconciliation_lag_ms
        if isinstance(item, Mapping):
            for raw_key, nested in item.items():
                key = str(raw_key).casefold().replace("-", "_")
                if key == "degraded_mode" and isinstance(nested, str):
                    if nested != "none" and _safe_dimension(nested):
                        degraded_modes.append(nested)
                    continue
                if key == "degraded_modes" and isinstance(nested, Sequence) and not isinstance(
                    nested, (str, bytes, bytearray)
                ):
                    for mode in nested:
                        if isinstance(mode, str) and mode != "none" and _safe_dimension(mode):
                            degraded_modes.append(mode)
                    continue
                if key == "retry_count" and isinstance(nested, int) and nested >= 0:
                    retry_count += nested
                    continue
                if key == "reconciliation_lag_ms" and isinstance(nested, (int, float)):
                    checked = float(nested)
                    if isfinite(checked) and checked >= 0:
                        reconciliation_lag_ms = max(reconciliation_lag_ms or 0, checked)
                    continue
                visit(nested)
            return
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for nested in item:
                visit(nested)

    visit(value)
    return OperationalSignals(
        degraded_modes=tuple(dict.fromkeys(degraded_modes)),
        retry_count=retry_count,
        reconciliation_lag_ms=reconciliation_lag_ms,
    )


class OperationalMetricsMiddleware:
    __slots__ = ("_app", "_metrics", "_monotonic")

    def __init__(
        self,
        app: ASGIApp,
        *,
        metrics: OperationalMetrics,
    ) -> None:
        self._app = app
        self._metrics = metrics
        self._monotonic = perf_counter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        started_at = self._monotonic()
        status_code = 500
        content_type = ""
        response_body = bytearray()
        capture_body = True

        async def send_metric_message(message: Message) -> None:
            nonlocal status_code, content_type, capture_body
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = {
                    key.decode("latin-1").casefold(): value.decode("latin-1")
                    for key, value in message.get("headers", [])
                }
                content_type = headers.get("content-type", "")
                capture_body = "json" in content_type.casefold()
            elif message["type"] == "http.response.body" and capture_body:
                body = message.get("body", b"")
                if len(response_body) + len(body) <= _MAX_CAPTURED_RESPONSE_BYTES:
                    response_body.extend(body)
                else:
                    capture_body = False
                    response_body.clear()
            await send(message)

        try:
            await self._app(scope, receive, send_metric_message)
        finally:
            stage = _api_stage(scope)
            result = "succeeded" if 200 <= status_code < 400 else "failed"
            self._metrics.record_stage_latency(
                boundary=MetricBoundary.API,
                stage=stage,
                operation_version="api-v1",
                elapsed_ms=max(0.0, (self._monotonic() - started_at) * 1000),
                result=result,
            )
            signals = _response_signals(response_body) if capture_body else OperationalSignals()
            if signals.retry_count:
                self._metrics.record_retry(
                    boundary=MetricBoundary.API,
                    stage=stage,
                    operation_version="api-v1",
                    count=signals.retry_count,
                )
            if signals.reconciliation_lag_ms is not None:
                self._metrics.record_reconciliation_lag(
                    boundary=MetricBoundary.API,
                    stage=stage,
                    operation_version="api-v1",
                    lag_ms=signals.reconciliation_lag_ms,
                )
            for mode in signals.degraded_modes:
                self._metrics.record_degraded_mode(
                    boundary=MetricBoundary.API,
                    stage=stage,
                    operation_version="api-v1",
                    mode=mode,
                )


def _response_signals(response_body: bytearray) -> OperationalSignals:
    if not response_body:
        return OperationalSignals()
    try:
        payload = json.loads(response_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return OperationalSignals()
    return extract_operational_signals(payload)


def _api_stage(scope: Scope) -> str:
    route = scope.get("route")
    route_path = str(getattr(route, "path", scope.get("path", "")))
    if route_path.startswith("/health"):
        return "health"
    if "/submissions" in route_path:
        return "submission"
    if "/interview-sessions" in route_path:
        return "interview"
    if any(
        marker in route_path
        for marker in ("/reports", "/review", "/privacy", "/final-decisions")
    ):
        return "review"
    if any(
        marker in route_path
        for marker in ("/positions", "/criteria", "/campaigns", "/invitations")
    ):
        return "hiring"
    return "api"


def _safe_dimension(value: str) -> bool:
    return _SAFE_DIMENSION.fullmatch(value) is not None
