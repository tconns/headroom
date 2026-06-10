from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_DIR = ROOT / "docker" / "vps-hub"


def read(path: str) -> str:
    return (DEPLOY_DIR / path).read_text(encoding="utf-8")


def test_vps_hub_files_exist() -> None:
    expected = [
        "docker-compose.yml",
        ".env.example",
        "README.md",
        "scripts/smoke-test.py",
        "scripts/backup.sh",
        "scripts/restore.sh",
    ]

    for rel in expected:
        assert (DEPLOY_DIR / rel).exists(), f"missing {rel}"


def test_compose_declares_proxy_service_and_persistent_state() -> None:
    compose = read("docker-compose.yml")

    assert "services:" in compose
    assert "headroom-proxy:" in compose
    assert "8787" in compose
    assert "HEADROOM_WORKSPACE_DIR=/data/headroom" in compose
    assert "OPENAI_TARGET_API_URL=${OPENAI_TARGET_API_URL}" in compose
    assert "OPENAI_API_KEY=${OPENAI_API_KEY}" in compose
    assert "headroom_data:/data/headroom" in compose
    assert "restart: unless-stopped" in compose
    assert "readyz" in compose


def test_env_example_has_required_keys_without_real_secrets() -> None:
    env = read(".env.example")

    required = [
        "HEADROOM_HOST=0.0.0.0",
        "HEADROOM_PORT=8787",
        "HEADROOM_WORKSPACE_DIR=/data/headroom",
        "OPENAI_TARGET_API_URL=https://your-9router.example.com/v1",
        "OPENAI_API_KEY=replace-with-9router-key",
        "HEADROOM_REQUIRE_RUST_CORE=true",
    ]
    for item in required:
        assert item in env

    forbidden = ["sk-", "AIza", "anthropic-", "ghp_"]
    for token in forbidden:
        assert token not in env


def test_operator_readme_documents_security_and_rollout() -> None:
    readme = read("README.md")

    required = [
        "Cloudflare",
        "Dokploy",
        "GitHub",
        "docker/vps-hub/docker-compose.yml",
        "9Router",
        "OPENAI_BASE_URL",
        "OPENAI_TARGET_API_URL",
        "Cloudflare Access",
        "backup",
        "rollback",
        "/readyz",
    ]
    for item in required:
        assert item in readme


def test_scripts_are_intentionally_secret_free() -> None:
    for rel in ["scripts/smoke-test.py", "scripts/backup.sh", "scripts/restore.sh"]:
        text = read(rel)
        assert "replace-with-9router-key" not in text
        assert "sk-" not in text
