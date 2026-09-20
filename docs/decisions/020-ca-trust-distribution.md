# ADR-020: Internal CA Trust Distribution with trust-manager

## Status

Accepted

## Context

cert-manager issues certificates from the internal CA selected in [ADR-005](005-cert-manager-self-signed-ca.md). In-cluster TLS clients also need to trust that CA. Embedding a separate PEM in each consumer gives the same trust material multiple update paths and makes CA rotation prone to stale copies.

## Decision

Use trust-manager to distribute the public CA certificate from `homelab-ca-secret` in the `cert-manager` namespace. A Bundle produces `custom-ca-certs` ConfigMaps in explicitly selected consumer namespaces: `argocd` and `monitoring`.

Consumers mount the generated bundle and configure their TLS clients to use it. trust-manager owns the generated ConfigMaps; the private CA key remains in the issuer Secret.

## Alternatives Considered

- **Embed a PEM in each consumer's manifests**: Requires coordinating every consumer update when the CA changes.
- **Copy the CA with scripts or Jobs**: Adds a separate synchronization mechanism and its own failure handling.
- **Disable TLS verification for internal endpoints**: Removes certificate identity validation and prevents probes from detecting trust failures.

## Rationale

- **One trust source**: Consumers receive the certificate associated with the internal issuer rather than independently maintained copies.
- **Declarative distribution**: The Bundle and namespace selection are managed through the existing GitOps workflow.
- **Public material only**: Consumers receive a ConfigMap containing the CA certificate, without access to its private key.

## Consequences

- Trust distribution depends on trust-manager and the source Secret. Consumers must mount the bundle before using internal TLS endpoints.
- Updating a ConfigMap does not guarantee every client reloads it; consumer reload behavior is part of CA rotation.
- This covers selected cluster namespaces. Workstations, TVs and other external clients still need their own trust-installation process.
