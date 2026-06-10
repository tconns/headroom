# Headroom VPS Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight, Dokploy-friendly Headroom VPS hub deployment that routes agent traffic through Headroom and 9Router, persists state on the VPS, and prepares a later shared-memory bridge.

**Architecture:** Start with one Docker Compose deployment for `headroom-proxy` using a persistent `/data/headroom` volume and 9Router as the OpenAI-compatible upstream. Add operator docs, env templates, smoke tests, and backup scripts before implementing remote MCP/shared memory. Keep the MVP within a 4 GB RAM VPS by avoiding Neo4j, Qdrant, ML extras, and multi-worker proxy.

**Tech Stack:** Docker Compose, Dokploy, Cloudflare, Headroom proxy, SQLite/local filesystem state, PowerShell/bash-friendly docs, Python smoke tests.

---

## File Structure

Use the existing repository layout and add a self-contained deployment folder that can be pushed to GitHub and consumed directly by Dokploy. Do not move existing `headroom/`, `crates/`, `docs/`, `wiki/`, or root Docker files.

Current repo anchors:

- Root `Dockerfile`: already builds the Headroom runtime image.
- Root `docker-compose.yml`: existing broader compose stack with Qdrant/Neo4j; do not use for the 4 GB VPS MVP.
- `docker/docker-compose.native.yml`: existing native-wrapper compose path; keep untouched.
- `headroom/proxy/server.py`: existing proxy runtime.
- `headroom/ccr/mcp_server.py`: existing compression/retrieval MCP runtime.
- `headroom/memory/mcp_server.py`: existing memory MCP runtime.
- `docs/superpowers/specs/`: design docs created by this workflow.

Add only this new deployment area under the existing `docker/` folder:

- Create `docker/vps-hub/docker-compose.yml`: Compose service for Dokploy Git deploy or manual Docker Compose.
- Create `docker/vps-hub/.env.example`: safe environment template for 9Router and Headroom settings.
- Create `docker/vps-hub/README.md`: operator guide for GitHub → Dokploy, Cloudflare, client config, rollback, and troubleshooting.
- Create `docker/vps-hub/scripts/smoke-test.py`: verifies `/readyz`, OpenAI-compatible chat completion, optional streaming.
- Create `docker/vps-hub/scripts/backup.sh`: daily backup script for `/data/headroom` state.
- Create `docker/vps-hub/scripts/restore.sh`: restore script from a backup tarball.
- Create `tests/test_vps_hub_assets.py`: repository test that validates required files, env keys, compose syntax text, GitHub/Dokploy instructions, and no accidental secrets.
- Modify `docs/superpowers/specs/2026-06-10-headroom-vps-hub-design.md`: add a short link to the implementation assets after they exist.

Do not modify core proxy code in this MVP unless smoke testing proves the existing `OPENAI_TARGET_API_URL` path cannot route to 9Router.

---

### Task 1: Add asset validation tests

**Files:**

- Create: `tests/test_vps_hub_assets.py`

- [ ] **Step 1: Write failing tests for deployment assets**

Create `tests/test_vps_hub_assets.py` with:

```python
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
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
python -m pytest tests/test_vps_hub_assets.py -q
```

Expected: FAIL because `docker/vps-hub/*` does not exist yet.

- [ ] **Step 3: Commit failing test**

```bash
git add tests/test_vps_hub_assets.py
git commit -m "test: add VPS hub asset checks"
```

---

### Task 2: Add Dokploy-compatible Compose and env template

**Files:**

- Create: `docker/vps-hub/docker-compose.yml`
- Create: `docker/vps-hub/.env.example`
- Test: `tests/test_vps_hub_assets.py`

- [ ] **Step 1: Create Compose file**

Create `docker/vps-hub/docker-compose.yml`:

```yaml
services:
  headroom-proxy:
    image: ${HEADROOM_IMAGE:-ghcr.io/chopratejas/headroom:latest}
    restart: unless-stopped
    command:
      - "--host"
      - "${HEADROOM_HOST:-0.0.0.0}"
      - "--port"
      - "${HEADROOM_PORT:-8787}"
    environment:
      - HEADROOM_HOST=${HEADROOM_HOST:-0.0.0.0}
      - HEADROOM_PORT=${HEADROOM_PORT:-8787}
      - HEADROOM_WORKSPACE_DIR=/data/headroom
      - HEADROOM_REQUIRE_RUST_CORE=${HEADROOM_REQUIRE_RUST_CORE:-true}
      - OPENAI_TARGET_API_URL=${OPENAI_TARGET_API_URL}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
      - GEMINI_API_KEY=${GEMINI_API_KEY:-}
      - OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT:-}
    ports:
      - "${HEADROOM_PORT:-8787}:8787"
    volumes:
      - headroom_data:/data/headroom
    healthcheck:
      test: ["CMD", "curl", "--fail", "--silent", "http://127.0.0.1:8787/readyz"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s

volumes:
  headroom_data:
```

- [ ] **Step 2: Create env example**

Create `docker/vps-hub/.env.example`:

```env
# Headroom runtime
HEADROOM_IMAGE=ghcr.io/chopratejas/headroom:latest
HEADROOM_HOST=0.0.0.0
HEADROOM_PORT=8787
HEADROOM_WORKSPACE_DIR=/data/headroom
HEADROOM_REQUIRE_RUST_CORE=true

# 9Router OpenAI-compatible upstream
OPENAI_TARGET_API_URL=https://your-9router.example.com/v1
OPENAI_API_KEY=replace-with-9router-key

# Optional upstream/provider keys. Leave blank unless your 9Router path needs them.
ANTHROPIC_API_KEY=
GEMINI_API_KEY=

# Optional observability endpoint. Leave blank for MVP.
OTEL_EXPORTER_OTLP_ENDPOINT=
```

- [ ] **Step 3: Run asset tests**

Run:

```bash
python -m pytest tests/test_vps_hub_assets.py -q
```

Expected: still FAIL because README and scripts are missing.

- [ ] **Step 4: Commit Compose and env template**

```bash
git add docker/vps-hub/docker-compose.yml docker/vps-hub/.env.example
git commit -m "feat: add VPS hub compose template"
```

---

### Task 3: Add smoke test script

**Files:**

- Create: `docker/vps-hub/scripts/smoke-test.py`
- Test: `tests/test_vps_hub_assets.py`

- [ ] **Step 1: Create smoke test script**

Create `docker/vps-hub/scripts/smoke-test.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def request_json(url: str, api_key: str | None, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any] | str]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, data=data, headers=headers, method="GET" if payload is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            body = res.read().decode("utf-8", errors="replace")
            try:
                return res.status, json.loads(body)
            except json.JSONDecodeError:
                return res.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test a Headroom VPS hub deployment.")
    parser.add_argument("--base-url", required=True, help="Public Headroom URL, e.g. https://headroom.example.com")
    parser.add_argument("--api-key", default=None, help="API key accepted by Headroom/9Router")
    parser.add_argument("--model", default="gpt-4o-mini", help="Model name routed by 9Router")
    parser.add_argument("--skip-chat", action="store_true", help="Only check /readyz")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    status, ready = request_json(f"{base}/readyz", None)
    if status >= 400:
        print(f"readyz failed: HTTP {status}: {ready}", file=sys.stderr)
        return 1
    print(f"readyz ok: {ready}")

    if args.skip_chat:
        return 0

    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": "You are a concise health-check assistant."},
            {"role": "user", "content": "Reply with exactly: headroom-ok"},
        ],
        "temperature": 0,
        "max_tokens": 20,
    }
    status, body = request_json(f"{base}/v1/chat/completions", args.api_key, payload)
    if status >= 400:
        print(f"chat completion failed: HTTP {status}: {body}", file=sys.stderr)
        return 1

    text = ""
    if isinstance(body, dict):
        choices = body.get("choices") or []
        if choices:
            text = str((choices[0].get("message") or {}).get("content") or "")
    if "headroom-ok" not in text.lower():
        print(f"unexpected chat response: {body}", file=sys.stderr)
        return 1

    print("chat completion ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run asset tests**

Run:

```bash
python -m pytest tests/test_vps_hub_assets.py -q
```

Expected: still FAIL because README and backup/restore scripts are missing.

- [ ] **Step 3: Commit smoke test script**

```bash
git add docker/vps-hub/scripts/smoke-test.py
git commit -m "test: add VPS hub smoke test script"
```

---

### Task 4: Add backup and restore scripts

**Files:**

- Create: `docker/vps-hub/scripts/backup.sh`
- Create: `docker/vps-hub/scripts/restore.sh`
- Test: `tests/test_vps_hub_assets.py`

- [ ] **Step 1: Create backup script**

Create `docker/vps-hub/scripts/backup.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${HEADROOM_STATE_DIR:-/data/headroom}"
BACKUP_DIR="${HEADROOM_BACKUP_DIR:-/data/headroom/backups}"
RETENTION_DAYS="${HEADROOM_BACKUP_RETENTION_DAYS:-7}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="${BACKUP_DIR}/headroom-${STAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

tar \
  --exclude="${BACKUP_DIR}" \
  -czf "${ARCHIVE}" \
  -C "$(dirname "${STATE_DIR}")" \
  "$(basename "${STATE_DIR}")"

find "${BACKUP_DIR}" -type f -name 'headroom-*.tar.gz' -mtime "+${RETENTION_DAYS}" -delete

printf 'backup created: %s\n' "${ARCHIVE}"
```

- [ ] **Step 2: Create restore script**

Create `docker/vps-hub/scripts/restore.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  printf 'usage: %s /path/to/headroom-backup.tar.gz\n' "$0" >&2
  exit 2
fi

ARCHIVE="$1"
STATE_DIR="${HEADROOM_STATE_DIR:-/data/headroom}"
RESTORE_PARENT="$(dirname "${STATE_DIR}")"

if [ ! -f "${ARCHIVE}" ]; then
  printf 'backup archive not found: %s\n' "${ARCHIVE}" >&2
  exit 1
fi

mkdir -p "${RESTORE_PARENT}"

if [ -e "${STATE_DIR}" ]; then
  SAFETY_COPY="${STATE_DIR}.pre-restore.$(date -u +%Y%m%dT%H%M%SZ)"
  mv "${STATE_DIR}" "${SAFETY_COPY}"
  printf 'existing state moved to: %s\n' "${SAFETY_COPY}"
fi

tar -xzf "${ARCHIVE}" -C "${RESTORE_PARENT}"
printf 'restore complete: %s\n' "${STATE_DIR}"
```

- [ ] **Step 3: Run asset tests**

Run:

```bash
python -m pytest tests/test_vps_hub_assets.py -q
```

Expected: still FAIL because README is missing.

- [ ] **Step 4: Commit backup scripts**

```bash
git add docker/vps-hub/scripts/backup.sh docker/vps-hub/scripts/restore.sh
git commit -m "feat: add VPS hub backup scripts"
```

---

### Task 5: Add Dokploy operator README

**Files:**

- Create: `docker/vps-hub/README.md`
- Test: `tests/test_vps_hub_assets.py`

- [ ] **Step 1: Create operator README**

Create `docker/vps-hub/README.md`:

````markdown
# Headroom VPS Hub Deployment

This deployment runs Headroom as a personal VPS hub behind Cloudflare and Dokploy.
It is sized for one 4 GB RAM / 2 CPU VPS and intentionally avoids Neo4j, Qdrant, ML extras, and image/OCR compression.

## Architecture

```text
AI agents / apps
  -> https://headroom.<domain>/v1
  -> Headroom proxy
  -> 9Router OpenAI-compatible endpoint
  -> upstream LLM provider
```

Persistent state lives in the Docker volume mounted at `/data/headroom`.

## Dokploy setup

Use Dokploy's Compose app flow against the same GitHub repository you push this codebase to. The deployment assets live under `docker/vps-hub/`; keep the existing root `Dockerfile`, root `docker-compose.yml`, `docker/`, `headroom/`, `crates/`, `docs/`, and `wiki/` layout unchanged.

### 1. Push repository to GitHub

1. Commit the `docker/vps-hub/` folder.
2. Push this repository to GitHub.
3. Confirm GitHub contains `docker/vps-hub/docker-compose.yml`.
4. Do not push real `.env` files or 9Router keys.

### 2. Create the Dokploy app

1. Open Dokploy dashboard.
2. Choose the target project.
3. Click **Create Service**.
4. Select **Compose**.
5. Name it `headroom-proxy`.
6. Choose **GitHub/Git repository** as the source.
7. Select this Headroom repository and the branch you deploy from, for example `main`.

### 3. Set Compose path

Set the Compose file path to:

```text
docker/vps-hub/docker-compose.yml
```

Do not select the repository root `docker-compose.yml`; it starts the broader stack with Qdrant/Neo4j and is not the 4 GB VPS MVP path.

If Dokploy does not support a compose path for your source mode, use manual Compose and paste the contents of `docker/vps-hub/docker-compose.yml`.

### 4. Add environment variables

Copy values from `docker/vps-hub/.env.example` into Dokploy environment settings.

Required values:

```env
HEADROOM_IMAGE=ghcr.io/chopratejas/headroom:latest
HEADROOM_HOST=0.0.0.0
HEADROOM_PORT=8787
HEADROOM_WORKSPACE_DIR=/data/headroom
HEADROOM_REQUIRE_RUST_CORE=true
OPENAI_TARGET_API_URL=https://your-9router.example.com/v1
OPENAI_API_KEY=replace-with-9router-key
```

Replace:

- `OPENAI_TARGET_API_URL` with your 9Router `/v1` endpoint.
- `OPENAI_API_KEY` with the key issued by 9Router.

Leave optional provider keys blank unless 9Router or a specific route requires them.

### 5. Configure storage

The compose file creates a Docker named volume:

```text
headroom_data:/data/headroom
```

In Dokploy, confirm the service keeps named volumes across redeploys. Do not use ephemeral storage for `/data/headroom`.

### 6. Configure domain

1. Open the service domain/settings tab.
2. Add a domain such as `headroom.example.com`.
3. Set container/internal port to `8787`.
4. Enable HTTPS through Dokploy if available.
5. Keep Cloudflare SSL mode as **Full** or **Full (strict)**.

### 7. Deploy

1. Click **Deploy**.
2. Watch container logs.
3. Wait for the health check to pass.
4. Open `https://headroom.example.com/readyz`.
5. Expected result: HTTP 200 JSON response.

### 8. First rollback path

Before routing agents, confirm rollback is possible:

1. Note the current image tag in `HEADROOM_IMAGE`.
2. Keep the previous Dokploy deployment revision available.
3. If deploy fails, use Dokploy rollback/redeploy previous revision.
4. If state corruption is suspected, stop the service before restore.

## Cloudflare setup

- Use Full/Strict SSL.
- Prefer Cloudflare Access in front of the Headroom domain.
- Do not expose raw port `8787` directly to the public internet.
- If streaming fails with Cloudflare proxying enabled, test DNS-only mode or adjust Cloudflare timeout/proxy settings.

## Required environment

```env
HEADROOM_IMAGE=ghcr.io/chopratejas/headroom:latest
HEADROOM_HOST=0.0.0.0
HEADROOM_PORT=8787
HEADROOM_WORKSPACE_DIR=/data/headroom
HEADROOM_REQUIRE_RUST_CORE=true
OPENAI_TARGET_API_URL=https://your-9router.example.com/v1
OPENAI_API_KEY=replace-with-9router-key
```

## Health check

```bash
curl -fsS https://headroom.<domain>/readyz
```

Expected: HTTP 200 JSON response.

## Smoke test

```bash
python docker/vps-hub/scripts/smoke-test.py \
  --base-url https://headroom.<domain> \
  --api-key "$OPENAI_API_KEY" \
  --model gpt-4o-mini
```

Expected output includes:

```text
readyz ok
chat completion ok
```

## Client configuration

OpenAI-compatible clients:

```env
OPENAI_BASE_URL=https://headroom.<domain>/v1
OPENAI_API_KEY=<key-accepted-by-headroom-or-9router>
```

Route one low-risk client first. Verify normal completions, streaming, and stats before migrating more agents.

## Security checklist

- Protect the endpoint with Cloudflare Access or equivalent bearer/API key middleware.
- Store secrets only in Dokploy environment variables.
- Do not commit `.env` files.
- Do not expose SQLite, Qdrant, Neo4j, or internal Docker volumes.
- Keep logs and CCR content on short retention until a longer policy is justified.

## Backup

Run inside the VPS or a maintenance container with the Headroom volume mounted:

```bash
HEADROOM_STATE_DIR=/data/headroom \
HEADROOM_BACKUP_DIR=/data/headroom/backups \
bash docker/vps-hub/scripts/backup.sh
```

The script keeps 7 days by default. Override with:

```bash
HEADROOM_BACKUP_RETENTION_DAYS=14 bash docker/vps-hub/scripts/backup.sh
```

## Restore

Stop the Headroom container before restoring.

```bash
HEADROOM_STATE_DIR=/data/headroom \
bash docker/vps-hub/scripts/restore.sh /data/headroom/backups/headroom-YYYYMMDDTHHMMSSZ.tar.gz
```

Restart the service after restore and check `/readyz`.

## Rollback

1. In Dokploy, redeploy the previous image tag or compose revision.
2. If state corruption is suspected, stop the container and restore the latest backup.
3. If 9Router routing fails, point affected clients back to their original provider URL until the proxy is healthy.

## Shared memory phase

The first deployment only prepares persistent state. Add shared memory after proxy stability is proven.

Planned memory flow:

```text
Agent MCP client
  -> local stdio shim when required
  -> VPS memory endpoint or service
  -> /data/headroom/memory.db
```

Use this only after the proxy path is stable for several real sessions.
````

- [ ] **Step 2: Run asset tests**

Run:

```bash
python -m pytest tests/test_vps_hub_assets.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit README**

```bash
git add docker/vps-hub/README.md
git commit -m "docs: add VPS hub deployment guide"
```

---

### Task 6: Link design spec to implementation assets

**Files:**

- Modify: `docs/superpowers/specs/2026-06-10-headroom-vps-hub-design.md`
- Test: `tests/test_vps_hub_assets.py`

- [ ] **Step 1: Update design spec**

Add this section after the `## Rollout Plan` section and before `## Acceptance Criteria`:

```markdown
## Implementation Assets

The first implementation pass should create the deployment assets under `docker/vps-hub/`:

- `docker-compose.yml` for Dokploy/manual Compose deployment;
- `.env.example` for safe environment configuration;
- `README.md` for operator rollout, security, backup, and rollback instructions;
- `scripts/smoke-test.py` for `/readyz` and OpenAI-compatible completion checks;
- `scripts/backup.sh` and `scripts/restore.sh` for local state protection.
```

- [ ] **Step 2: Run tests**

Run:

```bash
python -m pytest tests/test_vps_hub_assets.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit spec link**

```bash
git add docs/superpowers/specs/2026-06-10-headroom-vps-hub-design.md
git commit -m "docs: link VPS hub spec to deployment assets"
```

---

### Task 7: Final local verification

**Files:**

- Verify: `docker/vps-hub/*`
- Verify: `docs/superpowers/specs/2026-06-10-headroom-vps-hub-design.md`
- Verify: `tests/test_vps_hub_assets.py`

- [ ] **Step 1: Run asset test**

```bash
python -m pytest tests/test_vps_hub_assets.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Check git status**

```bash
git status --short
```

Expected: only pre-existing untracked `.codegraph/` and `.cursor/` may remain unless intentionally ignored by the operator. No uncommitted VPS hub files.

- [ ] **Step 3: Manual review checklist**

Confirm:

- `.env.example` contains no real secrets.
- README says Cloudflare Access or equivalent auth is required.
- Compose does not expose Qdrant/Neo4j.
- Compose uses one service only.
- Compose uses persistent `headroom_data` volume.
- Smoke test supports a custom public URL and API key.
- Backup script excludes its own backup directory.
- Restore script moves existing state aside before extracting.

- [ ] **Step 4: Do not deploy automatically**

Stop after local assets are ready. VPS deployment requires operator-provided domain, 9Router URL, 9Router key, and Dokploy access.

---

## Future Plan: Shared Memory Bridge

Create a separate implementation plan after Phase 1 proxy deployment passes real usage. That plan should cover one of these approaches:

1. Local stdio MCP shim that forwards `memory_search` and `memory_save` to an authenticated VPS HTTP endpoint.
2. Native remote MCP transport if the target clients support it reliably.
3. Running selected agents directly on the VPS with local stdio MCP.

Do not combine this with the proxy MVP; it is a separate subsystem and should be independently tested.

---

## Self-Review

Spec coverage:

- Proxy deployment: covered by Tasks 2, 5, 7.
- 9Router upstream: covered by Tasks 2, 3, 5.
- Persistent state: covered by Tasks 2, 4, 5.
- Security: covered by Tasks 5 and 7.
- Backups: covered by Tasks 4, 5, 7.
- Shared memory: intentionally deferred and scoped as a future separate plan.

Placeholder scan:

- No `TBD`, `TODO`, or vague implementation-only steps remain.
- The only placeholder values are safe operator placeholders in `.env.example` and README examples, not incomplete plan work.

Type/path consistency:

- Deployment root is consistently `docker/vps-hub/`.
- State path is consistently `/data/headroom`.
- Public URL examples consistently use `https://headroom.<domain>`.
