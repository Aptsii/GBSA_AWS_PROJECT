from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "deploy.yml"


def test_deploy_workflow_requires_saved_plan_and_protected_release_stages() -> None:
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    for job in ("plan:", "apply:", "migrate:", "deploy-ecs:", "deploy-frontends:"):
        assert job in workflow
    assert "terraform plan" in workflow
    assert "terraform apply" in workflow
    assert "actions/upload-artifact" in workflow
    assert "actions/download-artifact" in workflow
    assert "environment:" in workflow
    assert "alembic" in workflow
    assert "aws ecs update-service" in workflow
    assert "aws s3 sync" in workflow
    assert "aws cloudfront create-invalidation" in workflow
    assert "workflow_dispatch:" in workflow


def test_deploy_workflow_uses_oidc_without_static_aws_credentials() -> None:
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "id-token: write" in workflow
    assert "aws-actions/configure-aws-credentials" in workflow
    assert "role-to-assume" in workflow
    assert "AWS_ACCESS_KEY_ID" not in workflow
    assert "AWS_SECRET_ACCESS_KEY" not in workflow
