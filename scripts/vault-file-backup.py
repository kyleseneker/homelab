#!/usr/bin/env python3
"""Copy the standalone Vault file backend while its only writer is stopped."""
import argparse
import json
import os
import signal
from pathlib import Path
import subprocess
import tarfile
import tempfile
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kubeconfig', required=True)
    parser.add_argument('--output', required=True, help='New private .tar.gz file')
    args = parser.parse_args()

    def interrupted(signum, frame):
        raise KeyboardInterrupt('Backup interrupted; attempting production recovery')

    signal.signal(signal.SIGTERM, interrupted)
    os.umask(0o077)
    output = Path(args.output).resolve()
    if output.exists() or not output.parent.is_dir():
        parser.error('Output must be a new file in an existing private directory')
    base = ['kubectl', '--kubeconfig', args.kubeconfig, '--request-timeout=30s']

    def run(*arguments, data=None, stdout=subprocess.PIPE):
        result = subprocess.run(base + list(arguments), input=data, stdout=stdout,
                                stderr=subprocess.PIPE, timeout=240, check=False)
        if result.returncode:
            # The create request contains only the public reader manifest.
            if arguments[:2] == ('create', '-f'):
                print(result.stderr.decode(), flush=True)
            # Do not echo potentially sensitive Kubernetes responses.
            raise RuntimeError('kubectl operation failed: ' + ' '.join(arguments[:3]))
        return result.stdout

    def get(namespace, kind, name):
        return json.loads(run('-n', namespace, 'get', kind, name, '-o', 'json'))

    appset = get('argocd', 'applicationset', 'cluster-apps')
    if 'argocd.argoproj.io/skip-reconcile' not in appset['spec'].get('preservedFields', {}).get('annotations', []):
        raise RuntimeError('ApplicationSet must preserve the maintenance pause annotation')
    app = get('argocd', 'application', 'vault')
    if 'argocd.argoproj.io/skip-reconcile' in app['metadata'].get('annotations', {}):
        raise RuntimeError('Vault reconciliation is already paused; resolve it first')
    if app.get('operation') or app.get('status', {}).get('operationState', {}).get('phase') in ('Running', 'Terminating'):
        raise RuntimeError('Vault has an active Argo operation')
    sts = get('vault', 'statefulset', 'vault')
    if sts['spec']['replicas'] != 1:
        raise RuntimeError('Expected exactly one standalone Vault replica')
    status = json.loads(run('-n', 'vault', 'exec', 'vault-0', '--', 'vault', 'status', '-format=json'))
    if status['storage_type'] != 'file' or status['sealed'] or not status['initialized']:
        raise RuntimeError('Expected initialized, unsealed file-backend Vault')
    pod = get('vault', 'pod', 'vault-0')
    image = next(c['image'] for c in pod['spec']['containers'] if c['name'] == 'vault')
    reader = 'vault-file-backup-' + uuid.uuid4().hex[:12]
    manifest = {
        'apiVersion': 'v1', 'kind': 'Pod',
        'metadata': {'name': reader, 'namespace': 'vault',
                     'labels': {'app.kubernetes.io/name': 'vault-file-backup'}},
        'spec': {
            'nodeName': pod['spec']['nodeName'], 'restartPolicy': 'Never',
            'automountServiceAccountToken': False,
            'securityContext': {'runAsNonRoot': True, 'runAsUser': 100, 'runAsGroup': 1000,
                                'seccompProfile': {'type': 'RuntimeDefault'}},
            'containers': [{'name': 'reader', 'image': image, 'command': ['sleep', '3600'],
                            'securityContext': {'allowPrivilegeEscalation': False,
                                                'readOnlyRootFilesystem': True,
                                                'capabilities': {'drop': ['ALL']}},
                            'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'},
                                          'limits': {'cpu': '250m', 'memory': '128Mi'}},
                            'volumeMounts': [{'name': 'data', 'mountPath': '/source', 'readOnly': True}]}],
            'volumes': [{'name': 'data', 'persistentVolumeClaim': {'claimName': 'data-vault-0', 'readOnly': True}}]}}
    paused = False
    stopped = False
    created = False
    staged = None
    try:
        created = True
        run('create', '-f', '-', data=json.dumps(manifest).encode())
        run('-n', 'vault', 'wait', '--for=condition=Ready', 'pod/' + reader, '--timeout=120s')
        # Recheck after the reader starts; Argo may have refreshed meanwhile.
        app = get('argocd', 'application', 'vault')
        if app.get('operation') or 'argocd.argoproj.io/skip-reconcile' in app['metadata'].get('annotations', {}):
            raise RuntimeError('Vault reconciliation changed during preparation')
        # Guard concurrent changes with resourceVersion before claiming the pause.
        patch = [{'op': 'test', 'path': '/metadata/resourceVersion', 'value': app['metadata']['resourceVersion']}]
        if 'annotations' not in app['metadata']:
            patch.append({'op': 'add', 'path': '/metadata/annotations', 'value': {}})
        patch.append({'op': 'add', 'path': '/metadata/annotations/argocd.argoproj.io~1skip-reconcile', 'value': 'true'})
        run('-n', 'argocd', 'patch', 'application', 'vault', '--type=json', '-p', json.dumps(patch))
        paused = True
        stopped = True
        run('-n', 'vault', 'scale', 'statefulset/vault', '--current-replicas=1', '--replicas=0')
        run('-n', 'vault', 'wait', '--for=delete', 'pod/vault-0', '--timeout=120s')
        if get('vault', 'statefulset', 'vault')['spec']['replicas'] != 0:
            raise RuntimeError('Vault replica count changed during backup')
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix='.vault-backup-', delete=False) as stream:
            staged = Path(stream.name)
            run('-n', 'vault', 'exec', reader, '--', 'tar', '-czf', '-', '-C', '/source', '.', stdout=stream)
        if get('vault', 'statefulset', 'vault')['spec']['replicas'] != 0:
            raise RuntimeError('Vault restarted during backup; discard this copy')
        if get('argocd', 'application', 'vault')['metadata'].get('annotations', {}).get('argocd.argoproj.io/skip-reconcile') != 'true':
            raise RuntimeError('Reconciliation pause was removed during backup')
        with tarfile.open(staged, 'r:gz') as archive:
            members = archive.getmembers()
            if not any(m.name.startswith('./core/') and m.isfile() for m in members):
                raise RuntimeError('Archive has no Vault core data')
            for member in members:
                if member.isfile():
                    with archive.extractfile(member) as content:
                        while content.read(1024 * 1024):
                            pass
        # Atomic, no-clobber publication on the same filesystem.
        os.link(staged, output)
        print('Encrypted file-backend archive validated and saved privately.', flush=True)
    finally:
        # Restore availability before removing the reader or reconciliation pause.
        # If restart fails, leave reconciliation paused for explicit recovery.
        if stopped:
            run('-n', 'vault', 'scale', 'statefulset/vault', '--replicas=1')
            run('-n', 'vault', 'wait', '--for=create', 'pod/vault-0', '--timeout=120s')
            run('-n', 'vault', 'wait', '--for=condition=Ready', 'pod/vault-0', '--timeout=180s')
            restored = json.loads(run('-n', 'vault', 'exec', 'vault-0', '--', 'vault', 'status', '-format=json'))
            if restored['sealed'] or restored['cluster_id'] != status['cluster_id']:
                raise RuntimeError('Vault restart health/identity check failed; reconciliation remains paused')
            print('Production Vault restarted and auto-unsealed with its original identity.', flush=True)
        if paused:
            run('-n', 'argocd', 'annotate', 'application', 'vault', 'argocd.argoproj.io/skip-reconcile-')
        if created:
            run('-n', 'vault', 'delete', 'pod', reader, '--ignore-not-found', '--wait=false')
        if staged:
            staged.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
