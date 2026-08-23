# ADR-018: \*arr Configuration as Code

## Status

Accepted

## Context

The delivery pipeline rebuilds every layer from bare metal up to running containers. It stops
at the pod boundary: quality profiles, indexers, download clients, root folders and library
definitions live in each application's SQLite database, entered by hand through a web UI. A
rebuilt Sonarr comes back empty, and nothing in Git describes what it should contain.

These applications share a shape. Each exposes a REST API over its own configuration, each
authenticates with an API key, and each stores state in a database that no backup of the
manifests can reconstruct.

## Decision

Reconcile application configuration with a purpose-built Kubernetes operator,
[kyleseneker/media-operator](https://github.com/kyleseneker/media-operator), under the API
group `media-operator.dev/v1alpha1`.

Configuration is declared in CRs beside the manifests that deploy the app, and a controller
converges the app's live state toward them.

### Taxonomy

Fifteen kinds across nine API groups -- `pvr` (Sonarr, Radarr, Lidarr, Readarr), `downloads`,
`indexers`, `mediaservers`, `requests`, `subtitles`, `transcode`, `automation`, `curation`.
Each group ships as its own chart and manager, so an application that is not deployed costs
nothing to run.

Indexers are declared only against Prowlarr. Prowlarr's own sync fans them into Sonarr and
Radarr, which removes the largest ordering hazard between instances.

### Reconcile semantics

- **Adopt by name.** A resource that already exists is matched and updated rather than
  duplicated, so the operator can be introduced to a populated instance.
- **Merge partial arrays.** A CR that omits entries leaves them alone rather than deleting
  them, so partial adoption is possible.
- **Prune only what is recorded.** Deletion is limited to `.status.managedResources`, so a
  resource created outside the operator is never removed.
- **Unreachable is not an error.** A health check gates every reconcile; an unreachable app
  requeues without returning an error, which keeps it out of exponential backoff while an
  application restarts.
- **Finalizers with a per-CR `deletionPolicy`** (`orphan` or `delete`) and a give-up path, so
  a dead application cannot wedge `kubectl delete` or an ArgoCD prune.
- **`driftPolicy: observe`** records drift without writing, so a CR can be adopted against a
  live instance and measured before the operator is given write authority.

### Guarding against silent success

These APIs accept a payload containing keys they do not recognise, ignore them, and answer
2xx. A field the operator maps to the wrong name is therefore inert while the CR reports
`Synced=True`. Three mechanisms address this:

- **Contract tests** assert that every field a spec declares reaches the payload builder.
  Adding a field without wiring it fails the build rather than doing nothing at runtime.
- **Schema validation** checks free-form resource fields against the app's own
  `GET /api/vN/<kind>/schema` before writing, naming the offending field and listing the ones
  the implementation accepts. An app that serves no schema skips validation rather than
  blocking the write.
- **`drift_corrected_total`** counts rewrites. A resource corrected repeatedly is either
  being edited outside the operator or is not accepting the write at all; an alert fires when
  one never settles.

Alongside `app_api_request_duration_seconds`, `app_api_errors_total`, `resources_pruned_total`,
`managed_resources` and `config_synced`, this makes reconciliation observable rather than
assumed.

## Alternatives Considered

- **Crossplane with provider-terraform.** Reaches fuller coverage without hand-written field
  mappings, because the Terraform providers for these applications already exist. Rejected on
  two grounds: it teaches composition rather than controllers, which inverts the learning goal
  this cluster exists for, and Kyverno's `require-resource-limits` in Enforce mode rejects
  Crossplane's synthesised provider Deployments until `crossplane-system` is excluded --
  weakening an admission policy to install a tool is a poor trade.
- **Recyclarr and Configarr alone.** Both sync TRaSH guide data well and Recyclarr is retained
  for exactly that. Neither models root folders, download clients or library definitions, and
  running one of them across the surface the operator owns would put two controllers on the
  same resources.
- **Init containers or Jobs posting to each API.** No reconciliation, no drift detection, no
  adoption semantics. Every failure is silent and every change is a fresh script.

## Consequences

- Field mappings are written by hand, and a mapping can be wrong in ways the target API will
  not report. The guards above exist because of that, not in spite of it.
- The operator is a second artefact to version, release and roll out; the cluster pins each
  chart by version like any other dependency.
- Configuration that no CRD models is still click-ops, and stays invisible to Git until a kind
  covers it.
