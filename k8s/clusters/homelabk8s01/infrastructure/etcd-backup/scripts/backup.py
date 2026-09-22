"""Publish matched etcd, PKI and host configuration with a completion manifest."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

PATTERN = re.compile(r'^(snapshot|pki|control-plane|recovery)-(\d{8}-\d{6})\.(db|tar\.gz|json)$')
CONFIG_FILES = {
    **{'kubernetes/manifests/' + name + '.yaml': 'etc/kubernetes/manifests/' + name + '.yaml'
       for name in ('etcd', 'kube-apiserver', 'kube-controller-manager', 'kube-scheduler')},
    **{'kubernetes/' + name: 'etc/kubernetes/' + name for name in
       ('controller-manager.conf', 'scheduler.conf', 'kubeadm-config.yml', 'audit/audit-policy.yml')},
    'kubelet-config.yaml': 'var/lib/kubelet/config.yaml',
    'kubeadm-flags.env': 'var/lib/kubelet/kubeadm-flags.env',
    'kubelet-extra.env': 'etc/default/kubelet',
    'containerd.toml': 'etc/containerd/config.toml',
    'hostname': 'etc/hostname',
    'os-release': 'etc/os-release',
}


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def regular(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Recovery source must be a regular file: ' + str(path))


def private_copy(source, destination):
    with source.open('rb') as src, destination.open('xb') as dst:
        shutil.copyfileobj(src, dst)
    destination.chmod(0o640)


def artifact_time(name):
    match = PATTERN.fullmatch(name)
    if match and match.group(3) == {'snapshot': 'db', 'pki': 'tar.gz', 'control-plane': 'tar.gz', 'recovery': 'json'}[match.group(1)]:
        return match.group(2)
    return None


def expired(names, keep=7):
    """Keep seven completed sets; retain legacy pairs until seven sets exist."""
    completed = sorted((name[9:-5] for name in names
                        if re.fullmatch(r'recovery-\d{8}-\d{6}\.json', name)), reverse=True)
    if len(completed) < keep:
        return []
    boundary = completed[keep - 1]
    return sorted((name for name in names if artifact_time(name)
                   and artifact_time(name) < boundary),
                  key=lambda name: (not name.startswith('recovery-'), name))


def prepare(source, work, archive):
    os.umask(0o077)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    stage = work / timestamp
    stage.mkdir(mode=0o750)
    stage.chmod(0o750)
    regular(work / 'snapshot.db')
    for name in CONFIG_FILES:
        regular(source / name)
    pki = source / 'kubernetes/pki'
    if not pki.is_dir() or pki.is_symlink():
        raise ValueError('PKI must be a directory')
    entries = sorted(pki.rglob('*'))
    if not entries:
        raise ValueError('PKI is empty')
    for entry in entries:
        if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
            raise ValueError('PKI must contain only regular files and directories')
    private_copy(work / 'snapshot.db', stage / ('snapshot-' + timestamp + '.db'))
    with tarfile.open(stage / ('pki-' + timestamp + '.tar.gz'), 'w:gz') as output:
        output.add(pki, arcname='pki', recursive=False)
        for entry in entries:
            output.add(entry, arcname='pki/' + str(entry.relative_to(pki)), recursive=False)
    with tarfile.open(stage / ('control-plane-' + timestamp + '.tar.gz'), 'w:gz') as output:
        for name, target in CONFIG_FILES.items():
            output.add(source / name, arcname=target, recursive=False)
    files = []
    for path in sorted(stage.iterdir()):
        path.chmod(0o640)
        files.append({'name': path.name, 'bytes': path.stat().st_size, 'sha256': digest(path)})
    manifest = stage / ('recovery-' + timestamp + '.json')
    manifest.write_text(json.dumps({'schema': 1, 'timestamp': timestamp,
                                   'hostname': (source / 'hostname').read_text().strip(), 'files': files}, indent=2) + '\n')
    manifest.chmod(0o640)
    # Publish locally only after the complete set exists. Never select files by mtime.
    for item in files:
        private_copy(stage / item['name'], archive / item['name'])
    private_copy(manifest, archive / manifest.name)
    pointer = work / 'current'
    pointer.write_text(timestamp + '\n'); pointer.chmod(0o640)
    for name in expired([p.name for p in archive.iterdir()]):
        (archive / name).unlink()
    print('Prepared matched recovery set ' + timestamp, flush=True)


class S3:
    def __init__(self, bucket):
        self.bucket = bucket

    def call(self, args):
        result = subprocess.run(['aws', 's3api'] + args + ['--bucket', self.bucket], capture_output=True,
                                env=dict(os.environ, AWS_PAGER='', AWS_CLI_AUTO_PROMPT='off', AWS_EC2_METADATA_DISABLED='true'),
                                timeout=300)
        if result.returncode:
            raise RuntimeError('S3 operation failed: ' + args[0])
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def put(self, name, path):
        # On a container retry, accept an existing key only after downloading and
        # checking its bytes. Never replace an object with a timestamp collision.
        try:
            self.call(['put-object', '--key', 'etcd-snapshots/' + name, '--body', str(path), '--if-none-match', '*'])
        except RuntimeError:
            self.verify(name, path)

    def verify(self, name, path):
        with tempfile.TemporaryDirectory() as temporary:
            downloaded = Path(temporary) / 'readback'
            self.call(['get-object', '--key', 'etcd-snapshots/' + name, str(downloaded)])
            if downloaded.stat().st_size != path.stat().st_size or digest(downloaded) != digest(path):
                raise ValueError('S3 read-back checksum mismatch')

    def names(self):
        objects = self.call(['list-objects-v2', '--prefix', 'etcd-snapshots/']).get('Contents', [])
        return [item['Key'].removeprefix('etcd-snapshots/') for item in objects]

    def delete(self, name):
        self.call(['delete-object', '--key', 'etcd-snapshots/' + name])


def upload(work, client):
    timestamp = (work / 'current').read_text().strip()
    if not re.fullmatch(r'\d{8}-\d{6}', timestamp):
        raise ValueError('Invalid recovery timestamp')
    stage = work / timestamp
    manifest = stage / ('recovery-' + timestamp + '.json')
    document = json.loads(manifest.read_text())
    expected = {'snapshot-' + timestamp + '.db', 'pki-' + timestamp + '.tar.gz',
                'control-plane-' + timestamp + '.tar.gz'}
    if (document['schema'] != 1 or document['timestamp'] != timestamp or len(document['files']) != 3
            or {f['name'] for f in document['files']} != expected):
        raise ValueError('Recovery manifest does not describe one matched set')
    for item in document['files']:
        path = stage / item['name']
        if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise ValueError('Local recovery checksum mismatch')
    for item in document['files']:
        path = stage / item['name']
        client.put(path.name, path)
        client.verify(path.name, path)
    # Readers discover complete backups through this marker, written last.
    client.put(manifest.name, manifest)
    client.verify(manifest.name, manifest)
    for name in expired(client.names()):
        client.delete(name)
    print('Uploaded and read-back verified complete recovery set ' + timestamp, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['prepare', 'upload'])
    args = parser.parse_args()
    if args.operation == 'prepare':
        prepare(Path('/source'), Path('/work'), Path('/snapshots'))
    else:
        upload(Path('/work'), S3(os.environ['S3_BUCKET']))
