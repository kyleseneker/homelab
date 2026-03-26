# Contributing

Thanks for your interest in this project! While this is a personal homelab repo, contributions, suggestions, and bug reports are welcome.

## Getting Started

1. Fork the repository and clone your fork
2. Install prerequisites listed in the [quick start guide](docs/getting-started/quick-start.md)
3. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```
4. Install Ansible dependencies:
   ```bash
   make deps
   ```

## Development Workflow

1. Create a feature branch from `main`
2. Make your changes
3. Ensure pre-commit hooks pass (yamllint, trailing whitespace, gitleaks, terraform fmt)
4. Validate Kubernetes manifests:
   ```bash
   # CI runs kubeconform automatically, but you can test locally:
   kubeconform -strict -kubernetes-version 1.32.0 k8s/
   ```
5. Open a pull request against `main`

## Conventions

- **Kubernetes manifests** use the [bjw-s app-template](https://github.com/bjw-s-labs/helm-charts/tree/main/charts/library/common) Helm chart where possible
- **Commits** follow [Conventional Commits](https://www.conventionalcommits.org/) (e.g., `feat(sonarr): add readOnlyRootFilesystem`)
- **Secrets** never go in git — use Vault + External Secrets Operator (see [secrets docs](docs/architecture/secrets.md))

## Documentation

Docs are built with MkDocs. To preview locally:

```bash
make docs-serve
```

## Questions?

Open an issue — happy to discuss ideas, architecture decisions, or suggestions.
