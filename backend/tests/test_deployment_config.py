"""Static contracts for versioned production deployment resources."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _workflow(name: str) -> dict:
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows" / name).read_text())
    workflow["on"] = workflow.pop(True, workflow.get("on"))
    return workflow


def test_render_blueprint_contains_only_free_api() -> None:
    blueprint = yaml.safe_load((REPO_ROOT / "render.yaml").read_text())
    assert len(blueprint["services"]) == 1
    assert "databases" not in blueprint
    assert "envVarGroups" not in blueprint

    api = blueprint["services"][0]
    assert api["name"] == "finsight-api"
    assert api["type"] == "web"
    assert api["runtime"] == "docker"
    assert api["plan"] == "free"
    assert api["region"] == "singapore"
    assert api["branch"] == "QA"
    assert api["dockerfilePath"] == "./docker/Dockerfile.backend"
    assert api["dockerContext"] == "./backend"
    assert api["healthCheckPath"] == "/health/db"
    assert api["autoDeployTrigger"] == "checksPass"
    assert "preDeployCommand" not in api
    assert "disk" not in api

def test_render_blueprint_prompts_for_external_secrets() -> None:
    blueprint = yaml.safe_load((REPO_ROOT / "render.yaml").read_text())
    entries = {item["key"]: item for item in blueprint["services"][0]["envVars"]}

    assert entries["JWT_SECRET"] == {"key": "JWT_SECRET", "generateValue": True}
    assert entries["DATABASE_URL"] == {"key": "DATABASE_URL", "sync": False}
    assert entries["CORS_ORIGINS"] == {"key": "CORS_ORIGINS", "sync": False}
    assert entries["GEMINI_API_KEY"] == {"key": "GEMINI_API_KEY", "sync": False}
    assert "TRADING_ECONOMICS_API_KEY" not in entries


def test_eod_workflow_uses_ist_schedule_and_runtime_runner() -> None:
    workflow = _workflow("eod.yml")
    schedule = workflow["on"]["schedule"]

    assert schedule == [
        {"cron": "45 16 * * 1-5", "timezone": "Asia/Kolkata"},
        {"cron": "45 18 * * 1-5", "timezone": "Asia/Kolkata"},
        {"cron": "45 20 * * 1-5", "timezone": "Asia/Kolkata"},
    ]
    assert "workflow_dispatch" in workflow["on"]

    job = workflow["jobs"]["run-eod"]
    assert job["env"]["DATABASE_URL"] == "${{ secrets.DATABASE_URL }}"
    assert "GEMINI_API_KEY" not in job["env"]
    assert job["defaults"]["run"]["working-directory"] == "backend"
    commands = [step.get("run") for step in job["steps"]]
    assert "python -m pip install -r requirements.txt" in commands
    assert "python -m app.scheduler.runner" in commands


def test_vercel_configuration_uses_reproducible_install() -> None:
    config = json.loads((REPO_ROOT / "frontend/vercel.json").read_text())

    assert config["framework"] == "nextjs"
    assert config["installCommand"] == "npm ci"
    assert config["buildCommand"] == "npm run build"


def test_runtime_images_are_non_root_and_health_checked() -> None:
    for name in ("Dockerfile.backend", "Dockerfile.frontend"):
        dockerfile = (REPO_ROOT / "docker" / name).read_text()
        assert " AS runtime" in dockerfile
        assert "USER finsight" in dockerfile
        assert "HEALTHCHECK" in dockerfile

    backend = (REPO_ROOT / "docker/Dockerfile.backend").read_text()
    assert "COPY --chown=finsight:finsight . ." not in backend
    assert "requirements-dev.txt" not in backend


def test_backend_start_command_honors_platform_port_and_execs_server() -> None:
    command = (REPO_ROOT / "backend/scripts/start_web.sh").read_text()

    assert '"${PORT:-8000}"' in command
    assert "python -m alembic upgrade head" in command
    assert command.index("alembic upgrade head") < command.index("exec uvicorn")
    assert "exec uvicorn" in command
    assert "--proxy-headers" in command


def test_compose_faiss_tmpfs_is_writable_by_non_root_backend() -> None:
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())

    assert compose["services"]["backend"]["tmpfs"] == [
        "/app/data:mode=0770,uid=10001,gid=10001"
    ]


def test_ci_scopes_production_frontend_origin_to_build_only() -> None:
    workflow = _workflow("ci.yml")
    frontend = workflow["jobs"]["frontend"]
    steps = {step.get("name"): step for step in frontend["steps"]}

    assert "env" not in frontend
    assert "env" not in steps["Test frontend defaults"]
    assert steps["Build production frontend"]["env"] == {
        "FRONTEND_BUILD_ENV": "production",
        "NEXT_PUBLIC_API_URL": "https://api.finsight.example",
    }

    containers = workflow["jobs"]["containers"]
    assert set(containers["needs"]) == {"backend", "frontend"}
