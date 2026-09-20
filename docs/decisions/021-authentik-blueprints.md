# ADR-021: Authentik Application Configuration with Blueprints

## Status

Accepted

## Context

[ADR-010](010-authentik-sso.md) selects Authentik for authentication. Deploying its containers does not recreate the providers, applications and outpost associations that connect it to the homelab's services. Keeping these shared settings only in the database makes rebuilding authentication depend on manual UI configuration.

## Decision

Declare Authentik providers, applications and outpost associations in a Git-managed blueprint ConfigMap mounted into Authentik. Authentik applies the blueprint and resolves relationships between its objects. Secret values enter through environment-backed inputs supplied by the existing Vault and External Secrets path.

The blueprint owns these shared application settings. User accounts and interactive account administration remain in Authentik's database.

## Alternatives Considered

- **Manual UI configuration**: Convenient for initial setup, but leaves shared service configuration outside Git and requires repeating it after a database loss.
- **Terraform provider**: Provides declarative management but adds a separate execution, state and credential lifecycle for objects Authentik can configure natively.
- **API bootstrap scripts**: Require custom object lookup, ordering and update logic that blueprints already provide.

## Rationale

- **Native mechanism**: Blueprints express Authentik objects and their relationships without an additional controller.
- **Reproducible integrations**: Provider, application and outpost configuration is versioned alongside the workloads it protects.
- **Clear ownership**: Shared application settings have one declarative owner, while secret values remain outside Git.

## Consequences

- UI edits to blueprint-managed settings can be replaced when the blueprint is applied; persistent changes belong in Git.
- Blueprints do not replace PostgreSQL backups for users, sessions and other runtime state.
- Initial administrator access and required client secrets must be available during bootstrap, before applications can rely on Authentik login.
