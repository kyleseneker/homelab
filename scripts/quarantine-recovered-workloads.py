#!/usr/bin/env python3
"""Remove executable records from an isolated recovery copy before normal kubelets.

Never run against production. Requires the fresh-machine standalone boot drill,
its verified source metadata, and the host-level network boundary. No backup is
modified; removal applies only to the disposable VM's recovered etcd datastore.
"""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import socket
import time

ROOT = Path('/var/tmp/native-control-plane')
# Kubernetes storage prefixes, not namespace or object-name matches.
BUILTIN = frozenset(('pods', 'deployments', 'daemonsets', 'statefulsets', 'replicasets',
                     'jobs', 'cronjobs', 'controllers', 'minions',
                     'mutatingwebhookconfigurations', 'validatingwebhookconfigurations'))
CILIUM = frozenset(('ciliumnodes', 'ciliumendpoints', 'ciliumendpointslices', 'ciliumidentities'))
GROUPS = frozenset(('apps', 'batch', 'apps.k8s.io', 'batch.k8s.io', 'admissionregistration.k8s.io'))


def removal_prefix(key):
    parts = key.split('/')
    if len(parts) < 4 or parts[:2] != ['', 'registry']:
        return None
    if parts[2] in BUILTIN:
        return '/registry/' + parts[2] + '/'
    if len(parts) >= 5 and ((parts[2] in GROUPS and parts[3] in BUILTIN)
                            or (parts[2] == 'cilium.io' and parts[3] in CILIUM)):
        return '/registry/' + parts[2] + '/' + parts[3] + '/'
    return None


def quarantine():
    if os.geteuid() != 0 or socket.gethostname() != 'homelabrestore01-node-1':
        raise RuntimeError('Run only on the disposable recovery control plane')
    if not (ROOT / 'verification.json').exists() or (ROOT / 'quarantine.json').exists():
        raise RuntimeError('Require a verified standalone recovery that is not yet quarantined')
    verification = json.loads((ROOT / 'verification.json').read_text())
    if not verification.get('standalone_kubelet') or not verification.get('api_ready'):
        raise RuntimeError('Standalone boot verification is required')
    if Path('/etc/kubernetes/kubelet.conf').exists():
        raise RuntimeError('Refusing to quarantine after API-connected kubelet bootstrap')
    spec = importlib.util.spec_from_file_location('native', Path(__file__).with_name('verify-native-control-plane.py'))
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    run = native.run
    command = run(['systemctl', 'show', 'kubelet', '--property=ExecStart']).decode()
    if '--kubeconfig' in command or '--register-node=false' not in command:
        raise RuntimeError('Kubelet must still be standalone')
    run(['systemctl', 'is-active', '--quiet', 'native-recovery-isolation'])
    cri = ['crictl', '--runtime-endpoint', 'unix:///run/containerd/containerd.sock']
    stopped = ROOT / 'paused-controllers'
    stopped.mkdir(mode=0o700)
    for component in ('kube-controller-manager', 'kube-scheduler'):
        (Path('/etc/kubernetes/manifests') / (component + '.yaml')).rename(stopped / (component + '.yaml'))
    for _ in range(45):
        containers = json.loads(run(cri + ['ps', '-o', 'json']))['containers']
        names = {x['metadata']['name'] for x in containers}
        if names == {'etcd', 'kube-apiserver'}:
            break
        if names - set(native.COMPONENTS):
            raise RuntimeError('Unexpected workload before quarantine')
        time.sleep(2)
    else:
        raise RuntimeError('Recovered controllers did not stop')
    etcd = next(x['id'] for x in containers if x['metadata']['name'] == 'etcd')
    client = cri + ['exec', etcd, '/usr/local/bin/etcdctl', '--endpoints=https://127.0.0.1:2379',
                    '--cacert=/etc/kubernetes/pki/etcd/ca.crt',
                    '--cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt',
                    '--key=/etc/kubernetes/pki/etcd/healthcheck-client.key']
    keys = json.loads(run(client + ['get', '/registry/', '--prefix', '--keys-only', '--write-out=json']))
    counts = {}
    for item in keys.get('kvs', []):
        prefix = removal_prefix(base64.b64decode(item['key']).decode())
        if prefix:
            counts[prefix] = counts.get(prefix, 0) + 1
    if not counts.get('/registry/pods/') or not counts.get('/registry/deployments/'):
        raise RuntimeError('Expected populated source workload records before quarantine')
    # Controllers are stopped, so they cannot recreate execution records between
    # prefix deletion and the empty-state verification below.
    for prefix in sorted(counts):
        result = json.loads(run(client + ['del', prefix, '--prefix', '--write-out=json']))
        if result.get('deleted') != counts[prefix]:
            raise RuntimeError('Recovered execution records changed during quarantine')
    remaining = json.loads(run(client + ['get', '/registry/', '--prefix', '--keys-only', '--write-out=json']))
    if any(removal_prefix(base64.b64decode(x['key']).decode()) for x in remaining.get('kvs', [])):
        raise RuntimeError('Executable or stale node records remain')
    evidence = {'source_snapshot_sha256': verification['snapshot_sha256'], 'removed_prefix_counts': counts,
                'standalone_kubelet_during_quarantine': True, 'controllers_stopped_during_quarantine': True,
                'execution_records_empty': True}
    (ROOT / 'quarantine.json').write_text(json.dumps(evidence, indent=2) + '\n')
    # Resume only the two static control-plane controllers. Cilium and synthetic
    # workloads must be installed explicitly after normal node registration.
    for path in stopped.iterdir():
        path.rename(Path('/etc/kubernetes/manifests') / path.name)
    stopped.rmdir()
    print('Disposable recovery copy quarantined; executable records and stale node/Cilium identities removed.')


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    os.umask(0o077)
    quarantine()
