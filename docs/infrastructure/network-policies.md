# Network Policies

CiliumNetworkPolicies control ingress and egress in `arr`, `auth`, `monitoring`, `vault`, `external-secrets`, `kyverno`, `backups` and `openclaw`. This is partial namespace coverage, not cluster-wide default deny.

## Allowed Paths

| Namespace | Principal ingress paths | Principal egress paths |
|-----------|-------------------------|------------------------|
| `arr` | Gateway, same namespace, monitoring, OpenClaw, Authentik on proxy backend ports | DNS, same namespace, HTTPS, NFS, OpenClaw; VPN workload has broader internet access |
| `auth` | Gateway on 9000, same namespace; Grafana/ArgoCD OIDC to server on 9000; Authentik metrics from monitoring on 9300 | DNS, same namespace, Kubernetes API, NFS, explicit proxy backends |
| `monitoring` | Gateway, same namespace, Authentik on 9090/9093, cluster access to Prometheus | DNS, same namespace, API, NFS; workload-specific scrape, OIDC, alert and probe exceptions |
| `vault` | Cluster/API/host | DNS, same namespace, API, HTTPS for KMS, NFS |
| `external-secrets` | Cluster/API/host | DNS, same namespace, API, Vault on 8200 |
| `kyverno` | Cluster/API/host | DNS, same namespace, API |
| `backups` | Same namespace, monitoring | DNS, API, NFS and configured backup endpoints |
| `openclaw` | See the application policy and [OpenClaw](../apps/openclaw.md) | Scoped application endpoints and external integrations |

The manifests in `infrastructure/network-policies/` are the detailed source of truth. Rules select pod labels and **pod target ports**, which may differ from Service ports.

## Enforcement Model

The named `*-default-deny` policies explicitly deny ingress from `world`. Allow rules select the same endpoints and permit required sources. An egress allow rule enables default-deny for other egress on selected endpoints; `egressDeny` is not required. Cilium combines allow rules additively, so another broad allow can defeat an intended narrow boundary.

Authentik's database is only reachable through its same-namespace rule. OIDC clients no longer receive a namespace-wide allowance to every port. The proxy needs both egress from `auth` and ingress on each backend's namespace. See [Adding an App to SSO](../runbooks/adding-app-to-sso.md).

## Remaining Boundaries

`kube-system`, `argocd`, `cert-manager`, `goldilocks`, `intel-gpu-operator`, storage provisioners and other namespaces have no policies here. Same-namespace access and several infrastructure cluster allowances remain broad. HTTPS access to `world` is not an external-host allowlist and should not be treated as management-network isolation. Network firewalls and Cilium connection tests are required before claiming that boundary is enforced.

## Verification

Inspect the effective policies and flow verdicts rather than deleting protection to test connectivity:

```bash
kubectl get ciliumnetworkpolicies -A
hubble observe --namespace <namespace> --verdict DROPPED
```

Test both the expected path and a forbidden path, including an unrelated pod attempting PostgreSQL on 5432, before and after rollout. A successful auth redirect does not test the protected backend. ArgoCD restores out-of-band policy changes; permanent policy changes belong in Git.
