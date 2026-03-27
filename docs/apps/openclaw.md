# OpenClaw

OpenClaw is an AI agent platform that provides autonomous cluster operations and media stack management. A single agent handles both infrastructure and media pipeline responsibilities.

## Agent

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `ghcr.io/openclaw/openclaw:2026.3.7` |
| Port | 18789 |
| HTTPRoute | `openclaw.homelab.local` |
| Namespace | `openclaw` |
| ArgoCD app | `openclaw` |
| Sync wave | 2 |

The agent has cluster-wide RBAC for operational tasks: pod management, workload restarts, job cleanup, and node patching. It receives alerts from AlertManager via webhook and webhook notifications from *arr applications. It manages the full media pipeline from requests to playback.

**Init container:** Downloads `kubectl` and `kubeconform` into an emptyDir, then copies workspace configuration files from ConfigMaps into the persistent state directory.

## Security

- **Pod Security Standards:** `restricted` (enforce, audit, warn)
- **Security context:** Non-root (UID 1000), read-only root filesystem, all capabilities dropped, seccomp RuntimeDefault
- **Network policies:** Egress to K8s API, GitHub, Slack, Anthropic, and arr namespace.
- **RBAC:** ClusterRole with operational permissions cluster-wide.

## Storage

| Volume | Type | Mount Path | Notes |
|--------|------|------------|-------|
| `data` | PVC (`nfs-client`, 2Gi) | `/home/node/.openclaw` | Persistent agent state |
| `config` | ConfigMap | `/config/config.json5` | Agent configuration (read-only) |
| `skills` | ConfigMap | `/skills/` | Skill definitions (read-only) |
| `tools` | emptyDir | `/usr/local/bin/tools` | Downloaded CLI tools (ops only) |
| `tmp` | emptyDir | `/tmp` | Runtime temp files |

## Configuration

Agent configuration is managed via `openclaw config set` commands that write to the PVC-backed state directory. The initial configuration is seeded from ConfigMaps during the init container phase, but **PVC-persisted settings override ConfigMap values**. See the workspace ConfigMap (`openclaw-workspace`) for the boot sequence.

Key runtime settings (persisted on PVC, not in ConfigMaps):

- `gateway.bind` — must be `lan` (not `0.0.0.0`, which auto-migrates to `loopback`)
- `gateway.controlUi.allowedOrigins` — must include `https://openclaw.homelab.local`
- `gateway.auth.token` — auto-generated on first boot, used for Control UI auth

## Control UI Access

The Control UI is at `https://openclaw.homelab.local`. First-time setup:

1. Get the gateway token:
   ```bash
   kubectl --kubeconfig ./kubeconfig exec -n openclaw deploy/openclaw -- \
     grep -A1 '"token"' /home/node/.openclaw/openclaw.json
   ```
2. Open the Control UI, paste the token in settings, and click Connect.
3. The UI will show "pairing required" — approve it:
   ```bash
   # List pending requests
   kubectl --kubeconfig ./kubeconfig exec -n openclaw deploy/openclaw -- \
     openclaw devices list

   # Approve by request ID
   kubectl --kubeconfig ./kubeconfig exec -n openclaw deploy/openclaw -- \
     openclaw devices approve <request-id>
   ```
4. Refresh the browser. The token and device pairing persist across sessions (stored in browser localStorage and PVC respectively).

**Note:** Clearing browser data or switching browsers requires re-pairing. The gateway token itself doesn't change.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| AlertManager | Sends alerts via webhook |
| *arr stack | Monitors and receives webhooks from arr apps |
| Vault + ESO | API keys and webhook tokens stored as ExternalSecrets |

## Upstream

- OpenClaw is built on [Claude Code](https://claude.ai/claude-code) by Anthropic
