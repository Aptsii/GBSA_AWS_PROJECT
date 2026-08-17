from __future__ import annotations

from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_compose_declares_the_complete_local_production_contract() -> None:
    compose = yaml.safe_load((REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert set(services) == {
        "postgres",
        "localstack",
        "dynamodb",
        "opensearch",
        "api",
        "worker",
        "company-console",
        "applicant-interview",
    }
    assert all("healthcheck" in service for service in services.values())
    assert services["api"]["build"]["target"] == "api"
    assert services["worker"]["build"]["target"] == "worker"
    assert services["company-console"]["build"]["target"] == "company-console"
    assert services["applicant-interview"]["build"]["target"] == "applicant-interview"


def test_application_services_wait_for_healthy_dependencies() -> None:
    compose = yaml.safe_load((REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]

    for application in ("api", "worker"):
        dependencies = services[application]["depends_on"]
        assert set(dependencies) == {"postgres", "localstack", "dynamodb", "opensearch"}
        assert {dependency["condition"] for dependency in dependencies.values()} == {
            "service_healthy"
        }
    assert services["company-console"]["depends_on"]["api"]["condition"] == "service_healthy"
    assert services["applicant-interview"]["depends_on"]["api"]["condition"] == "service_healthy"
