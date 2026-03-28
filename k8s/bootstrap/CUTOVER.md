# ApplicationSet Cutover Runbook

**DO NOT push this branch to main until you complete step 3.**

The root app has `prune: true` — if it sees the deleted `application.yml` files
before the ApplicationSet is managing your apps, it will cascade-delete all workloads.

## Steps

All kubectl commands use `--kubeconfig ./kubeconfig`.

### 1. Apply the ApplicationSet (before pushing)

```bash
kubectl apply -k k8s/bootstrap/applicationsets/ --kubeconfig ./kubeconfig
```

The ApplicationSet controller will try to create Applications, but they already
exist (owned by the root app). This is expected — they'll be adopted in step 3.

### 2. Disable pruning on the root app

```bash
kubectl patch app root -n argocd --type merge \
  -p '{"spec":{"syncPolicy":{"automated":{"prune":false}}}}' \
  --kubeconfig ./kubeconfig
```

This prevents the root app from deleting child Applications when it sees the
`application.yml` files are gone after you push.

### 3. Push the branch

```bash
git push origin main
```

The root app will sync and see the deleted files. With pruning disabled, it will
go OutOfSync but won't delete anything.

### 4. Remove the root app finalizer and delete it

```bash
kubectl patch app root -n argocd --type json \
  -p '[{"op":"remove","path":"/metadata/finalizers"}]' \
  --kubeconfig ./kubeconfig

kubectl delete app root -n argocd --kubeconfig ./kubeconfig
```

Removing the finalizer first prevents cascade deletion of child Applications.
After deletion, the child Applications are orphaned.

### 5. Let the ApplicationSet adopt orphaned Applications

The ApplicationSet controller reconciles every ~3 minutes. It will detect that
Applications matching its generated names already exist and adopt them, updating
their specs to the new multi-source configuration.

If apps don't get adopted after a few minutes, force a reconciliation:

```bash
kubectl annotate applicationset cluster-apps -n argocd \
  argocd.argoproj.io/reconcile="$(date +%s)" --overwrite \
  --kubeconfig ./kubeconfig
```

### 6. Verify

```bash
# All apps should show Synced/Healthy
kubectl get apps -n argocd --kubeconfig ./kubeconfig

# Check that apps are owned by the ApplicationSet
kubectl get apps -n argocd -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.ownerReferences[0].name}{"\n"}{end}' \
  --kubeconfig ./kubeconfig

# Spot-check a Helm app has multi-source
kubectl get app minio -n argocd -o jsonpath='{.spec.sources}' --kubeconfig ./kubeconfig | python3 -m json.tool
```

### 7. Apply the bootstrap kustomization update

The argocd-notifications ExternalSecret moved into the bootstrap kustomization:

```bash
kubectl apply -k k8s/bootstrap/argocd/ --kubeconfig ./kubeconfig
```

### 8. Clean up this file

Delete this runbook after successful cutover.

## Rollback

If something goes wrong at any step:

**Before step 3 (haven't pushed yet):**
Just `git checkout main` to restore all deleted files. Delete the ApplicationSet:
```bash
kubectl delete applicationset cluster-apps -n argocd --kubeconfig ./kubeconfig
```

**After step 3 (already pushed):**
Revert the commit and push. Re-enable pruning on root app:
```bash
git revert HEAD && git push origin main
kubectl patch app root -n argocd --type merge \
  -p '{"spec":{"syncPolicy":{"automated":{"prune":true}}}}' \
  --kubeconfig ./kubeconfig
```

**After step 4 (root app deleted):**
Re-apply the root app from the reverted commit:
```bash
git revert HEAD && git push origin main
kubectl apply -f k8s/bootstrap/root-app.yml --kubeconfig ./kubeconfig
```
