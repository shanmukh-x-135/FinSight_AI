"""Static contracts for versioned production deployment resources."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_render_blueprint_contains_api_cron_and_database() -> None:
    blueprint = yaml.safe_load((REPO_ROOT / "render.yaml").read_text())
    services = {service["name"]: service for service in blueprint["services"]}

    api = services["finsight-api"]
    assert api["type"] == "web"
    assert api["runtime"] == "docker"
    assert api["branch"] == "main"
    assert api["healthCheckPath"] == "/health/db"
    assert api["preDeployCommand"] == "alembic upgrade head"
    assert api["autoDeployTrigger"] == "checksPass"

    cron = services["finsight-eod"]
    assert cron["type"] == "cron"
    assert cron["branch"] == "main"
    assert cron["schedule"] == "15 11,13,15 * * 1-5"
    assert cron["dockerCommand"] == "python -m app.scheduler.runner"

    database_config = blueprint["databases"][0]
    assert database_config["postgresMajorVersion"] == "16"
    assert database_config["ipAllowList"] == []
    for service in services.values():
        database = next(
            item for item in service["envVars"] if item.get("key") == "DATABASE_URL"
        )
        assert database["fromDatabase"]["property"] == "connectionString"


def test_blueprint_never_commits_secret_values() -> None:
    blueprint = yaml.safe_load((REPO_ROOT / "render.yaml").read_text())
    group = blueprint["envVarGroups"][0]["envVars"]
    entries = {item["key"]: item for item in group}

    assert entries["JWT_SECRET"] == {"key": "JWT_SECRET", "generateValue": True}
    assert all("sync" not in item for item in group)

    for service in blueprint["services"]:
        service_entries = {item.get("key"): item for item in service["envVars"]}
        assert service_entries["CORS_ORIGINS"] == {
            "key": "CORS_ORIGINS",
            "sync": False,
        }
        assert "GEMINI_API_KEY" not in service_entries
        assert "TRADING_ECONOMICS_API_KEY" not in service_entries


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
    assert "exec uvicorn" in command
    assert "--proxy-headers" in command


def test_compose_faiss_tmpfs_is_writable_by_non_root_backend() -> None:
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())

    assert compose["services"]["backend"]["tmpfs"] == [
        "/app/data:mode=0770,uid=10001,gid=10001"
    ]


def test_ci_scopes_production_frontend_origin_to_build_only() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
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
