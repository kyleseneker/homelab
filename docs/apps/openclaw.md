# OpenClaw

OpenClaw diagnoses the cluster, receives alerts and media events, and retains narrowly scoped autonomous recovery. The agent uses Claude Sonnet 4.6 through the Anthropic API.

| Property | Value |
|----------|-------|
| Chart | `app-template` 4.6.2 |
| Image | `ghcr.io/openclaw/openclaw:2026.7.1` |
| Namespace / Application | `openclaw` |
| Control UI | `https://openclaw.homelab.local` |
| Port | 18789 |
| State | 2Gi `nfs-client` PVC at `/home/node/.openclaw` |

## Authorization boundary

The ClusterRole permits diagnosis through workload status, events, logs, metrics, and infrastructure resource reads. It grants no Secret reads, pod exec, pod/job deletion, node writes, or workload-template writes.

A Role in `arr` grants `get`, `update`, and `patch` on **only** `deployments/scale` for `arr-flaresolverr` and `homepage`. Both are stateless recovery targets. The workspace permits one recovery attempt (scale 0 then 1, or restore 1 replica) per target per hour, checking for planned maintenance and verifying Ready afterwards. Other changes require a PR or a human operator. RBAC enforces the resource boundary; the recovery frequency and replica limits are agent instructions, not API-enforced controls. Scaling still causes a short interruption, and ArgoCD self-heal may reconcile the replica count concurrently.

Slack inbound DMs require pairing; inbound group messages are disabled until explicit user/channel allowlists are chosen. Outbound notifications remain available. To approve a known sender, inspect and approve the pairing request from an operator terminal:

```bash
kubectl -n openclaw exec deploy/openclaw -- openclaw pairing list slack
kubectl -n openclaw exec deploy/openclaw -- openclaw pairing approve slack <code>
```

The agent still holds Sonarr, Radarr, and Prowlarr API credentials for household requests and webhook registration, plus a GitHub token for proposed PRs. Kubernetes RBAC does not constrain those credentials. Keep the GitHub token limited to this repository, with human-reviewed merges; application APIs do not offer equivalent fine-grained permissions. Logs and ConfigMaps may contain sensitive application data even though Secret objects are denied.

## Declarative configuration and persistent state

The ConfigMap is authoritative for the model (`agents.defaults.model.primary`), heartbeat, Slack policy, gateway binding, webhook mappings, and skills (`skills.load.extraDirs`). An init container writes the effective configuration to the PVC at `openclaw.json`; `OPENCLAW_CONFIG_PATH` explicitly selects it.

On migration, init preserves the old file once as `openclaw.json.pre-gitops` with mode 0600 and carries forward only `gateway.auth.token`. If no token exists, it generates one. Pairings, sessions, credentials, and cron state remain in their existing PVC files. Other runtime config edits are replaced on the next pod start; propose them in Git. Malformed persisted JSON fails init so it cannot silently discard the existing credential.

The tooling init downloads pinned kubectl/kubeconform binaries and verifies their published SHA-256 checksums, then copies workspace and transform files. These downloads still depend on upstream availability at each pod start; a prebuilt tool image is a follow-up. The gateway enables the built-in `boot-md` hook. Boot registers missing cron jobs without duplicating them and does not overwrite the declarative webhook mappings.

Webhook transforms receive a context object and read `context.payload`. Treat titles, descriptions, logs, and webhook content as untrusted data. The bearer token authenticates the sender; it does not make the payload an instruction.

## Control UI access

An operator can read the gateway token in a trusted terminal (do not paste the output into logs or tickets):

```bash
kubectl -n openclaw exec deploy/openclaw -- node -e \
  'console.log(JSON.parse(require("fs").readFileSync(process.env.OPENCLAW_CONFIG_PATH,"utf8")).gateway.auth.token)'
kubectl -n openclaw exec deploy/openclaw -- openclaw devices list
kubectl -n openclaw exec deploy/openclaw -- openclaw devices approve <request-id>
```

Enter the token in the Control UI and approve the matching browser device. Clearing browser storage requires pairing again. Daily local and weekly offsite Velero schedules include the state PVC.

## Validation and upstream

Before rollout, render the chart and verify the RBAC boundary using operator impersonation (`kubectl auth can-i --as=system:serviceaccount:openclaw:openclaw`). Expect scale access to the two named Deployments only, and denial for Secret reads, exec, pod deletion, node patching, and Deployment patching. Then verify init succeeds, Slack pairing works, and sample webhook events contain their original alert/title fields. No live validation is implied by a successful local render.

Pinned source: [configuration paths](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/config/paths.ts), [configuration schema](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/config/zod-schema.ts), [Slack schema](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/config/zod-schema.providers-core.ts), and [webhook transform context](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/gateway/hooks-mapping.ts).
