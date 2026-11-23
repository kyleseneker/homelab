# Network Policies

Every pod outside `kube-system` starts in default deny in both directions, with only cluster DNS allowed. Namespace and workload policies add the paths each app needs, so a new namespace starts closed rather than open. Cluster-wide policies also deny every pod access to infrastructure administration.

## Layout

| Where | What |
|-------|------|
| `infrastructure/network-policies/baseline.yml` | Cluster-wide default deny, the world ingress deny and the DNS allow |
| `infrastructure/network-policies/<namespace>.yml` | The namespace baseline: the ingress and egress every pod in the namespace shares |
| `infrastructure/network-policies/infrastructure-admin.yml` | Cluster-wide denies of infrastructure administration |
| `infrastructure/network-policies/cidr-groups.yml` | Named external addresses |
| `<app>/networkpolicy.yml` | Rules for that app's workloads only, in the app's own Argo CD application |

Argo CD is installed from `k8s/bootstrap/argocd`, outside the ApplicationSet, so its component rules also live in `argocd.yml`, where Argo CD keeps them in sync.

## Allowed Paths

| Namespace | Principal ingress paths | Principal egress paths |
|-----------|-------------------------|------------------------|
| `media` | Gateway, same namespace, monitoring, the Authentik server on proxy backend ports | DNS, same namespace, HTTPS; VPN workload has broader internet access |
| `auth` | Gateway on 9000, same namespace; Grafana/ArgoCD OIDC to server on 9000; Prometheus on 9300 | DNS, same namespace, Kubernetes API; the server to its proxy backends |
| `monitoring` | Gateway, same namespace, cluster access to Prometheus, the Authentik server to Alertmanager on 9093 | DNS, same namespace, API; workload-specific scrape, OIDC, alert and probe exceptions; unpoller to the UniFi console on 192.168.10.1:443 |
| `vault` | Cluster/API/host | DNS, same namespace, API, HTTPS for KMS |
| `external-secrets` | Cluster/API/host | DNS, same namespace, API, Vault on 8200 |
| `kyverno` | Cluster/API/host | DNS, same namespace, API |
| `backups` | Same namespace, monitoring | DNS, API and configured backup endpoints |
| `home-automation` | Gateway and Prometheus on 8123 | DNS, public HTTPS |
| `argocd` | Argo CD's upstream per-component policies; world denied | DNS, same namespace, API; HTTPS from the repo server and notifications controller; the server to Authentik on 9000 for OIDC |
| `cert-manager` | Prometheus on 9402; the API server to the webhook on 10250 | DNS, API; the controller to HTTPS for ACME and Route53, and DNS to 1.1.1.1 and 9.9.9.9 for DNS-01 checks |
| `goldilocks` | Authentik's outpost to the dashboard on 8080 | DNS, API |
| `intel-gpu-operator` | The API server to the webhook on 9443 | DNS, API |
| `local-path-storage`, `nfs-provisioner` | None | DNS, API |

The manifests are the detailed source of truth. Rules select pod labels and **pod target ports**, which may differ from Service ports.

## Named Addresses

Policies refer to addresses outside the cluster through `CiliumCIDRGroup` objects in `cidr-groups.yml`, with `toCIDRSet: [{cidrGroupRef: <name>}]`, instead of repeating literal CIDRs. The groups carry an ArgoCD sync wave of `-1`, so they exist before the policies that use them; a deny rule naming a missing group matches nothing.

| Group | CIDR | Address |
|-------|------|---------|
| `nas` | 192.168.10.10/32 | UNAS Pro |
| `proxmox-host` | 192.168.10.2/32 | Proxmox host |
| `unifi-gateway` | 192.168.10.1/32 | Dream Router 7 on the Homelab VLAN |
| `management-vlan` | 192.168.99.0/24 | Management VLAN |

Exception lists (`except`) accept only literal CIDRs, so Home Assistant's internet egress still lists the private ranges it excludes.

## Enforcement Model

`baseline`, a CiliumClusterwideNetworkPolicy, selects every pod with a namespace label outside `kube-system`. Cilium's own health, ingress and host endpoints carry no namespace label, so the gateway is not selected. It enables default deny in both directions, denies ingress from `world` and allows egress to cluster DNS. Every other policy only adds allows. Cilium combines allow rules additively, so another broad allow can defeat an intended narrow boundary.

Cilium also enforces Kubernetes `NetworkPolicy` objects and adds their allows to these. Argo CD's upstream install ships narrow per-component ingress policies, which stay as its ingress layer. Charts that ship broad ones have them turned off: Authentik's PostgreSQL subchart admitted 5432 from any pod and allowed all egress.

Kubelet probes from the pod's own node are always allowed. Admission webhooks need ingress from `kube-apiserver` and `remote-node`, because the API server on the control-plane node can reach them from its Cilium internal address.

A pod that calls an app by its external hostname, such as Argo CD's OIDC issuer `https://auth.home.seneker.io`, goes through the gateway's Envoy. Envoy checks the pod's egress policy against the backend pod, not the gateway address, and answers HTTP 403 when it is not allowed; Hubble shows no drop. Allow egress to the backend pod and port.

Authentik's database is only reachable through its same-namespace rule. OIDC clients no longer receive a namespace-wide allowance to every port. The embedded outpost runs in the Authentik server pods, so a proxied app needs egress from `authentik-server` and ingress from those pods on the app's port; nothing else in `auth` reaches the backends.

NFS volumes are mounted by the kubelet on the node, outside any pod's policy, so no pod needs NFS egress. See [Adding an App to SSO](../runbooks/adding-app-to-sso.md).

## Infrastructure Administration

`deny-infrastructure-admin`, a CiliumClusterwideNetworkPolicy, selects every pod and denies egress to:

- The Proxmox host's SSH (22), rpcbind (111), SPICE proxy (3128) and web UI (8006) on 192.168.10.2. NUT (3493) and node-exporter (9100) stay reachable for monitoring.
- The NAS's SSH (22) and web UI (80, 443) on 192.168.10.10. NFS and SNMP stay reachable.
- The whole Management VLAN, 192.168.99.0/24.

`deny-gateway-console` denies the UniFi console on 192.168.10.1:443 to every pod except unpoller in `monitoring`. The gateway firewall opens that port to the nodes for unpoller, and pod traffic leaves the cluster from node addresses, so without it any pod could reach the console's login. It has two rules: one for pods not labelled `unpoller`, one for pods labelled `unpoller` outside `monitoring` ([unpoller](unpoller.md#access-to-the-console)).

Deny rules take precedence over any allow rule. Both policies set `enableDefaultDeny` to false in both directions: they also select `kube-system`, which `baseline` leaves out, and without it Cilium would put those pods into default-deny egress, because a policy with egress rules of any kind enables it. They do not cover host-network pods or the nodes themselves; the Proxmox host firewall and the zone firewall cover those ([ADR-016](../decisions/016-vlan-segmentation.md)).

## Remaining Boundaries

`kube-system` has no policies, by design, and `default` runs no pods. Same-namespace access and several infrastructure cluster allowances remain broad. HTTPS access to `world` is not an external-host allowlist and should not be treated as management-network isolation. Network firewalls and Cilium connection tests are required before claiming that boundary is enforced.

## Verification

Inspect the effective policies and flow verdicts rather than deleting protection to test connectivity:

```bash
kubectl get ciliumnetworkpolicies -A
hubble observe --namespace <namespace> --verdict DROPPED
```

Test both the expected path and a forbidden path, including an unrelated pod attempting PostgreSQL on 5432, before and after rollout. A successful auth redirect does not test the protected backend. ArgoCD restores out-of-band policy changes; permanent policy changes belong in Git.

Argo CD applies its own policies. If one cuts the repo server off from GitHub, Argo CD cannot sync the fix: delete the policy with `kubectl`, then correct it in Git.

## Changing Policies Safely

- **A new namespace** starts closed. Ship its baseline file and the app's `networkpolicy.yml` with the app, then list what is still missing with `hubble observe --namespace <namespace> --verdict DROPPED`.
- **Narrowing or removing a rule**: Hubble's policy verdicts name the policy that allowed each flow (`hubble observe --namespace <namespace> --type policy-verdict -o json`, fields `egress_allowed_by` and `ingress_allowed_by`). Watch long enough to cover periodic jobs, and read open connections from conntrack (`cilium-dbg bpf ct list global` on each agent), because long-lived connections such as watches on the API server open no new flows while you watch. Remove the rule once nothing relies on it.
- **Comparing before and after**: `cilium-dbg bpf policy get <endpoint-id>` on the endpoint's node shows the rules Cilium actually enforces. A refactor that should change nothing should leave it identical.
