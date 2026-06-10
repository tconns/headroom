# Headroom VPS Hub Design

## Goal

Deploy Headroom on one personal VPS as a shared hub for multiple AI agents and machines. The hub should reduce token usage, centralize metrics/state, route LLM traffic through the user's existing 9Router OpenAI-compatible key system, and later support shared memory across agents.

## Context

The VPS has 4 GB RAM, 2 CPU cores, 50 GB storage, Docker, Dokploy, and a Cloudflare-managed domain. This is enough for a personal Headroom deployment if the initial scope stays lightweight.

The codebase already supports a production proxy, Docker deployment, SQLite-backed metrics, CCR retrieval, and MCP servers for compression/retrieval and memory. The safest path is to deploy the proxy first, then add shared memory and MCP bridging.

## Non-goals

- Do not build a public SaaS in the first version.
- Do not run Neo4j or Qdrant initially; they are optional future upgrades and may overrun the 4 GB RAM VPS.
- Do not enable ML or image/OCR compression initially.
- Do not expose raw databases or internal service ports to the internet.

## Recommended Approach

Use a phased version of Approach B: proxy plus shared state first, shared memory second.

### Phase 1: Proxy Hub

Deploy one Dokploy service running `headroom proxy` behind Cloudflare HTTPS.

Traffic flow:

```text
AI agents / apps
  -> https://headroom.<domain>/v1
  -> Headroom proxy on VPS
  -> 9Router OpenAI-compatible endpoint
  -> upstream LLM provider
```

The proxy provides:

- automatic request compression;
- cache alignment;
- CCR storage for original content retrieval;
- request/cost/token metrics;
- health checks and logs.

### Phase 2: Shared Memory

Add shared memory on the same VPS using a persistent SQLite database under the same Headroom state directory.

Traffic flow:

```text
AI agents on each machine
  -> local MCP shim or compatible remote bridge
  -> Headroom memory service/state on VPS
  -> /data/headroom/memory.db
```

The memory tools should expose:

- `memory_save` for persistent facts, decisions, conventions, debugging notes;
- `memory_search` for semantic lookup across prior sessions.

A local shim is preferred if an agent only supports stdio MCP. The shim keeps local MCP compatibility while forwarding memory operations to the VPS.

## Architecture

```text
Cloudflare DNS/TLS
  -> Dokploy route: https://headroom.<domain>
  -> container: headroom-proxy
       internal port: 8787
       command: headroom proxy --host 0.0.0.0 --port 8787
       volume: /data/headroom:/data/headroom
       env:
         HEADROOM_HOST=0.0.0.0
         HEADROOM_WORKSPACE_DIR=/data/headroom
         OPENAI_TARGET_API_URL=https://<9router-host>/v1
         OPENAI_API_KEY=<9router-key>
         HEADROOM_REQUIRE_RUST_CORE=true
  -> 9Router
  -> upstream LLM provider
```

State layout:

```text
/data/headroom/
  metrics.sqlite
  session_stats.jsonl
  memory.db
  ccr/
  logs/
  backups/
```

## Security Requirements

The Headroom proxy sees prompts, tool output, code snippets, logs, and possibly secrets. Treat it as sensitive infrastructure.

Required controls:

- Use HTTPS via Cloudflare.
- Use Cloudflare Full/Strict SSL.
- Protect the endpoint with either Cloudflare Access or a bearer/API key gate.
- Do not publish raw `8787` directly if Dokploy/Cloudflare route is available.
- Do not expose Qdrant, Neo4j, SQLite, or internal volumes.
- Use environment secrets in Dokploy, not committed `.env` files.
- Add retention for logs and CCR content; start with 7-14 days.
- Back up `/data/headroom` daily; encrypt backups if stored off-server.

## 9Router Integration

9Router should be used as the upstream OpenAI-compatible API target.

Minimum expected compatibility:

- `POST /v1/chat/completions`;
- streaming SSE for clients that stream responses;
- ideally `GET /v1/models`;
- optional `POST /v1/responses` if agents use OpenAI Responses API.

Initial configuration:

```env
OPENAI_TARGET_API_URL=https://<9router-host>/v1
OPENAI_API_KEY=<9router-key>
```

If 9Router uses standard `Authorization: Bearer <key>`, no code change should be needed. If it requires custom headers, add a small proxy/header-forwarding extension later.

## Client Configuration

For OpenAI-compatible clients:

```env
OPENAI_BASE_URL=https://headroom.<domain>/v1
OPENAI_API_KEY=<client-or-router-key>
```

For Anthropic-compatible clients, test per client because base URL behavior varies:

```env
ANTHROPIC_BASE_URL=https://headroom.<domain>
ANTHROPIC_API_KEY=<client-or-router-key>
```

If a tool cannot route through the proxy, keep it on the original provider and add MCP memory later.

## Resource Plan

The VPS should start with only lightweight services:

- Headroom proxy: expected hundreds of MB to roughly 1.2 GB RAM depending on dependencies and active requests.
- SQLite state: lightweight.
- Dokploy/Docker overhead: acceptable on 4 GB RAM.

Avoid initially:

- Neo4j;
- Qdrant;
- ML compression extras;
- image/OCR extras;
- multiple proxy workers.

## Observability

MVP should expose/check:

- `/readyz` health check;
- container logs;
- Headroom stats/session summary;
- token savings over time;
- request error rate;
- upstream 9Router failures.

## Backup and Retention

Initial policy:

- Back up `/data/headroom/*.db`, `session_stats.jsonl`, and essential CCR metadata daily.
- Keep 7 daily backups locally.
- Optionally push encrypted backups to external storage.
- Rotate logs after 7-14 days.
- Keep CCR original content short-lived unless retrieval history proves longer retention is needed.

## Rollout Plan

1. Deploy proxy in Dokploy with a persistent volume and 9Router env vars.
2. Put it behind Cloudflare domain and TLS.
3. Add auth protection.
4. Test `/readyz`.
5. Route one low-risk client through the proxy.
6. Verify streaming, normal completions, and stats.
7. Route more agents gradually.
8. Add memory DB and MCP/local shim after proxy is stable.
9. Consider Qdrant/Neo4j only if SQLite/local memory becomes limiting.

## Acceptance Criteria

Phase 1 is complete when:

- `https://headroom.<domain>/readyz` is healthy;
- at least one OpenAI-compatible client can complete through Headroom and 9Router;
- streaming works for at least one streaming client;
- metrics/stats show requests and token savings;
- state persists across container restarts;
- the endpoint is protected by Cloudflare Access or equivalent auth;
- daily backups are configured.

Phase 2 is complete when:

- multiple machines/agents can save memory to the same VPS-backed store;
- multiple machines/agents can search the same memory store;
- memory survives restarts;
- MCP compatibility is handled either by local shim or supported remote MCP transport.

## Open Decisions

- Final domain name for the Headroom route.
- Exact 9Router base URL and whether it requires custom headers.
- Auth method: Cloudflare Access vs bearer key gate.
- Backup target: local-only vs external encrypted storage.
- MCP bridge implementation for clients that only support stdio.
