#!/usr/bin/env python3
"""Prepare private verifier inputs using only a downloaded recovery bundle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import yaml


def checksum(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def validate_archive(archive, pki=False):
    for member in archive.getmembers():
        path = Path(member.name)
        if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
            raise ValueError('Unsafe recovery archive entry')
        if pki:
            allowed = path.parts and path.parts[0] == 'pki'
        else:
            allowed = (str(path).startswith(('etc/kubernetes/', 'var/lib/kubelet/', 'etc/containerd/', 'etc/default/'))
                       or str(path) in ('etc/hostname', 'etc/os-release'))
        if not allowed:
            raise ValueError('Unexpected recovery archive path')


def prepare(manifest, output):
    if output.exists():
        raise ValueError('Refusing an existing recovery output directory')
    document = json.loads(manifest.read_text())
    timestamp = document.get('timestamp', '')
    if document.get('schema') != 1 or not re.fullmatch(r'\d{8}-\d{6}', timestamp):
        raise ValueError('Unsupported recovery manifest')
    expected = {'snapshot-' + timestamp + '.db', 'pki-' + timestamp + '.tar.gz',
                'control-plane-' + timestamp + '.tar.gz'}
    files = document.get('files', [])
    if len(files) != 3 or {item['name'] for item in files} != expected:
        raise ValueError('Manifest must contain exactly one matched recovery set')
    for item in files:
        path = manifest.parent / item['name']
        if path.is_symlink() or not path.is_file() or path.stat().st_size != item['bytes'] or checksum(path) != item['sha256']:
            raise ValueError('Recovery artifact checksum/type mismatch')
    pki = manifest.parent / ('pki-' + timestamp + '.tar.gz')
    config = manifest.parent / ('control-plane-' + timestamp + '.tar.gz')
    with tarfile.open(pki) as archive:
        validate_archive(archive, pki=True)
    with tarfile.open(config) as archive:
        validate_archive(archive)
        # Validate all static-pod inputs before creating output or extracting keys.
        sources = {}
        for component in ('etcd', 'kube-apiserver', 'kube-controller-manager', 'kube-scheduler'):
            pod = yaml.safe_load(archive.extractfile('etc/kubernetes/manifests/' + component + '.yaml'))
            containers = pod['spec']['containers']
            if pod['kind'] != 'Pod' or len(containers) != 1 or containers[0]['name'] != component:
                raise ValueError('Unexpected static-pod manifest')
            sources[component] = {key: containers[0][key] for key in ('image', 'command')}
        audit = archive.extractfile('etc/kubernetes/audit/audit-policy.yml').read()
        os.umask(0o077)
        output.mkdir(mode=0o700)
        (output / 'control-plane').mkdir(mode=0o700)
        archive.extractall(output / 'control-plane')
    shutil.copyfile(manifest.parent / ('snapshot-' + timestamp + '.db'), output / 'snapshot.db')
    shutil.copyfile(pki, output / 'pki.tar.gz')
    (output / 'audit-policy.yml').write_bytes(audit)
    for component, source in sources.items():
        (output / (component + '-source.json')).write_text(json.dumps(source, indent=2) + '\n')
    (output / 'recovery-source.json').write_text(json.dumps(document, indent=2) + '\n')
    print('Prepared verified offline inputs for recovery set ' + timestamp)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.manifest, args.output)
