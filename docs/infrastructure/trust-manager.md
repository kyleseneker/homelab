# trust-manager

trust-manager distributes the public homelab CA certificate from `homelab-ca-secret` in the `cert-manager` namespace into `custom-ca-certs` ConfigMaps in `argocd` and `monitoring`. It complements cert-manager issuance: a valid server certificate still requires the client to trust its issuer.

The Bundle namespace selector is explicit. It does not distribute the private key. ArgoCD and Blackbox mount the resulting ConfigMap; external workstations and media clients follow the [client trust procedure](../getting-started/trust-ca.md).

The trust-package init container has resource limits for the enforced admission policy. Verify Bundle readiness, target ConfigMaps and client reload behavior after changing the issuer. Existing consumers must not pin a separate expired PEM.

Source: `k8s/clusters/homelabk8s01/infrastructure/trust-manager/`. See [ADR-020](../decisions/020-ca-trust-distribution.md).
