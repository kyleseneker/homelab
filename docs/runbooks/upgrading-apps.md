# Upgrading Applications

This runbook covers the process for upgrading application versions in the cluster. All upgrades are performed through Git commits -- ArgoCD handles the rollout automatically.

## Updating an Image Tag

Most upgrades involve bumping the container image tag in the application's `values.yaml` file.

1. Open the app's `values.yaml` file.
2. Locate the `image.tag` field under `controllers.main.containers.main.image`.
3. Change the tag to the new version.
4. Commit and push the change.
5. ArgoCD detects the change and syncs the application automatically.

### Example: Upgrading Sonarr

To upgrade Sonarr from `4.0.17` to `4.0.18`, edit `k8s/clusters/homelabk8s01/apps/arr/sonarr/values.yaml`:

```yaml
controllers:
  main:
    containers:
      main:
        image:
          repository: lscr.io/linuxserver/sonarr
          tag: 4.0.18  # was 4.0.17
```

Commit and push:

```bash
git add k8s/clusters/homelabk8s01/apps/arr/sonarr/values.yaml
git commit -m "upgrade sonarr to 4.0.18"
git push
```

ArgoCD will detect the change within its polling interval and roll out the new version.

## Updating the Helm Chart Version

When a new version of the bjw-s app-template chart (or any other Helm chart) is released:

1. Check the chart's changelog for breaking changes. For app-template, see the [bjw-s releases page](https://github.com/bjw-s-labs/helm-charts/releases).
2. Update the `chartVersion` field in the app's `config.yaml`:

    ```yaml
    chartVersion: "4.7.0"
    ```

3. Commit and push.

!!! warning
    Helm chart major version bumps often include breaking changes to the values schema. Always read the changelog and test with a single application before updating all apps.

## Checking for Updates

Check upstream releases for available updates:

| Application | Release Source |
|-------------|---------------|
| Sonarr, Radarr, Prowlarr, Bazarr | [LinuxServer.io Fleet](https://fleet.linuxserver.io/) |
| Jellyfin | [Jellyfin Releases](https://github.com/jellyfin/jellyfin/releases) |
| Seerr | [Seerr Releases](https://github.com/seerr-team/seerr/releases) |
| qBittorrent | [LinuxServer.io Fleet](https://fleet.linuxserver.io/) |
| Tdarr | [Tdarr Releases](https://github.com/HaveAGitGat/Tdarr/releases) |
| Homepage | [Homepage Releases](https://github.com/gethomepage/homepage/releases) |
| Recyclarr | [Recyclarr Releases](https://github.com/recyclarr/recyclarr/releases) |

## Rolling Back

If an upgrade causes issues, roll back using one of these methods:

### Git Revert

Revert the commit that introduced the upgrade:

```bash
git revert <commit-hash>
git push
```

ArgoCD will sync the application back to the previous version.

### ArgoCD UI

1. Open the ArgoCD UI at `https://argocd.homelab.local`.
2. Select the application.
3. Click **History and Rollback**.
4. Select the previous successful sync and click **Rollback**.

!!! note
    A Git revert is preferred over an ArgoCD rollback because it keeps the Git repository (the source of truth) consistent with the cluster state. An ArgoCD rollback will be overwritten on the next sync if the Git repo still contains the newer version.

## Post-Upgrade Verification

After any upgrade:

1. Check that the pod is running:

    ```bash
    kubectl get pods -n arr -l app.kubernetes.io/instance=arr-sonarr
    ```

2. Check pod logs for errors:

    ```bash
    kubectl logs -n arr -l app.kubernetes.io/instance=arr-sonarr
    ```

3. Verify the web UI loads by navigating to the app's URL (e.g., `https://sonarr.homelab.local`).
4. Check ArgoCD sync status to confirm the app is `Healthy` and `Synced`.
