# ADR-002: Vault + External Secrets Operator for Secrets Management

## Status

Accepted (migrated from Sealed Secrets)

## Context

Kubernetes Secrets are base64-encoded, not encrypted. Committing them to Git is a security risk. The cluster needs a way to manage secrets that keeps sensitive values out of the Git repository while remaining compatible with GitOps workflows.

## Decision

Use HashiCorp Vault as the secrets backend with External Secrets Operator (ESO) to sync secrets into Kubernetes. Vault uses AWS KMS for auto-unseal and Kubernetes auth for ESO access.

## Alternatives Considered

- **Sealed Secrets**: The previous solution. Encrypts secrets client-side so they can be committed to Git. Simple but limited: no central audit trail, no dynamic rotation, and secret values are baked into Git history even after rotation.
- **SOPS + age/GPG**: Encrypts YAML values in-place. Works well for small teams but requires key distribution and has no runtime secret store.
- **Plain Kubernetes Secrets**: Not viable for a GitOps workflow where all manifests live in a public or shared repository.

## Rationale

- **Separation of concerns**: Vault stores secrets externally; ESO syncs them declaratively. Secret values never appear in Git.
- **Kubernetes auth**: ESO authenticates to Vault via ServiceAccount tokens. No static credentials to manage.
- **AWS KMS auto-unseal**: Vault automatically unseals on pod restart without manual intervention, which is critical for unattended cluster rebuilds.
- **Rotation without Git commits**: Secrets can be rotated via `vault kv put` without touching any manifest. ESO picks up changes on its refresh interval.
- **Audit trail**: Vault logs all secret access, providing visibility that Sealed Secrets cannot.

## Consequences

- Vault is a stateful service that must be backed up (included in Velero daily schedule).
- AWS KMS dependency means the `vault-aws-kms` Secret must be manually created during cluster bootstrapping before Vault can start.
- More moving parts than Sealed Secrets (Vault + ESO + ClusterSecretStore + ExternalSecret per app).
