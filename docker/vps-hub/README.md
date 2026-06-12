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

## Repository layout

This folder is an overlay deployment profile for your fork. It does not replace the existing root `Dockerfile`, root `docker-compose.yml`, `docker/`, `headroom/`, `crates/`, `docs/`, or `wiki/` layout.

Use this file in Dokploy:

```text
docker/vps-hub/docker-compose.yml
```

Do not select the repository root `docker-compose.yml` for the 4 GB VPS MVP because that broader stack includes services such as Qdrant and Neo4j.

## Dokploy setup

Use Dokploy's Compose app flow against the same GitHub repository you push this codebase to.

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
HEADROOM_TELEMETRY=off
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

### 1. Zero-Config Proxy (Recommended)

Route your agent's LLM API traffic directly through the Headroom VPS Proxy. The proxy automatically injects relevant memories from the shared store and provides the necessary memory tools (`memory_save`, `memory_search`) without needing any local MCP configuration.

Configure your agent (Aider, Claude Code, etc.) with the following environment variables:

```env
OPENAI_BASE_URL=https://headroom.<domain>/v1
OPENAI_API_KEY=<your-9router-or-upstream-key>
```

For Anthropic/Claude Code:

```env
ANTHROPIC_BASE_URL=https://headroom.<domain>
ANTHROPIC_API_KEY=<your-anthropic-key>
```

### 2. Local MCP Bridge (For Cursor / Windsurf)

If you prefer to call upstream LLMs directly but want to use Headroom's memory and compression tools via the MCP panel (e.g. in Cursor), configure a local stdio shim that routes to your remote VPS.

Add this to your Cursor MCP settings or `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "headroom-ccr": {
      "command": "python",
      "args": [
        "-m",
        "headroom.ccr.mcp_server"
      ],
      "env": {
        "HEADROOM_PROXY_URL": "https://headroom.<domain>"
      }
    },
    "headroom-memory": {
      "command": "python",
      "args": [
        "-m",
        "headroom.memory.mcp_server",
        "--db",
        "/data/headroom/memory.db"
      ],
      "env": {
        "HEADROOM_PROXY_URL": "https://headroom.<domain>"
      }
    }
  }
}
```

*Note: Ensure the `headroom` CLI or python module is installed on your local machine (`pip install "headroom-ai[mcp]"`).*

## Shared Memory Configuration

The VPS proxy is configured with:
- `--memory`: Enables persistent memory.
- `--memory-storage global`: Shares a single memory database (`memory.db`) across all sessions and agents.
- `--memory-db-path /data/headroom/memory.db`: Persists the DB inside the Docker volume.

All agents routing through the proxy will write to and read from this centralized memory store, achieving cross-agent state persistence.

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
