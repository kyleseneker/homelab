# Pushgateway

Holds results pushed by batch jobs until Prometheus scrapes them. The [restore test](restore-test.md) is its only client; Prometheus documents this, the outcome of a service-level batch job, as the Pushgateway's intended use.

## Details

| Field | Value |
|-------|-------|
| Chart | `prometheus-pushgateway` from prometheus-community |
| Namespace | `monitoring` |
| Service | `pushgateway-prometheus-pushgateway:9091` |
| Persistence | `/data/pushgateway.data` on an `nfs-client` claim, so results survive a restart |
| Scraping | ServiceMonitor with `honorLabels: true`, so pushed `job`, `target` and `source` labels are kept |
| Network | Ingress on 9091 from the restore test in `backups`; Prometheus scrapes it from inside `monitoring` |

The Pushgateway never forgets a pushed series. A target removed from the restore test keeps its last values until its group is deleted:

```bash
kubectl -n monitoring port-forward svc/pushgateway-prometheus-pushgateway 9091
curl -X DELETE http://localhost:9091/metrics/job/restore_test/target/<target>/source/local
```
