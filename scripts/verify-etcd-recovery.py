#!/usr/bin/env python3
"""Verify an offsite etcd/PKI pair on the lab control plane, with loopback-only networking.

Run as root on homelabrestore01-node-1 with a private input directory containing
snapshot.db, pki.tar.gz, etcd-source.json, kube-apiserver-source.json, audit-policy.yml.
Source JSON files contain only the image and command from the original static pods.
Never points kubelet, a scheduler or a controller manager at the recovered API.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import tarfile
import time

NETNS = 'homelab-etcd-recovery'
ETCD_IMAGE = 'registry.k8s.io/etcd:3.5.15-0'
API_IMAGE = 'registry.k8s.io/kube-apiserver:v1.31.4'
BUMP = 1000000000


def validate_archive(members):
    for member in members:
        path = Path(member.name)
        if (path.is_absolute() or '..' in path.parts or not path.parts
                or path.parts[0] != 'pki' or not (member.isfile() or member.isdir())):
            raise ValueError('PKI archive must contain only files/directories below pki/')


def flag(command, name):
    matches = [arg.split('=', 1)[1] for arg in command if arg.startswith(name + '=')]
    if len(matches) != 1:
        raise ValueError('Expected exactly one ' + name)
    return matches[0]


def main(source, work):
    if os.geteuid() != 0 or socket.gethostname() != 'homelabrestore01-node-1':
        raise RuntimeError('Run only as root on homelabrestore01-node-1')
    if work.exists() or Path('/run/netns', NETNS).exists():
        raise RuntimeError('Existing drill directory/network namespace must be inspected first')
    source = source.resolve()
    if source.stat().st_mode & 0o077:
        raise RuntimeError('Input directory must be private (0700)')
    for name in ('snapshot.db', 'pki.tar.gz', 'etcd-source.json', 'kube-apiserver-source.json', 'audit-policy.yml'):
        p = source / name
        if not p.is_file() or p.is_symlink():
            raise RuntimeError('Missing or unsafe input: ' + name)
    etcd = json.loads((source / 'etcd-source.json').read_text())
    api = json.loads((source / 'kube-apiserver-source.json').read_text())
    if etcd['image'] != ETCD_IMAGE or api['image'] != API_IMAGE:
        raise RuntimeError('Revalidate recovery tooling for changed control-plane images')
    address = flag(api['command'], '--advertise-address')
    if address != '192.168.10.50':
        raise RuntimeError('Expected the original production control-plane identity')
    def interrupted(signum, frame):
        raise KeyboardInterrupt("Recovery drill interrupted; cleaning up isolated tasks")

    signal.signal(signal.SIGTERM, interrupted)
    os.umask(0o077)
    work.mkdir(mode=0o700)
    (work / 'audit').mkdir()
    with tarfile.open(source / 'pki.tar.gz') as archive:
        validate_archive(archive.getmembers())
        archive.extractall(work)
    log = (work / 'commands.log').open('wb')
    processes = []
    network_created = False
    ctr = ['ctr', '-n', 'k8s.io']

    def run(args, ok=True, timeout=120):
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        log.write(result.stderr)
        log.flush()
        if ok and result.returncode:
            raise RuntimeError('Drill command failed; details are in the private work directory: ' + args[0])
        return result

    def namespace():
        links = json.loads(run(['ip', '-n', NETNS, '-j', 'link', 'show']).stdout)
        routes = json.loads(run(['ip', '-n', NETNS, '-j', 'route', 'show']).stdout)
        if [link['ifname'] for link in links] != ['lo'] or routes:
            raise RuntimeError('Drill network must have only loopback and no external routes')

    def mount(src, dst, writable=False):
        return ['--mount', 'type=bind,src=' + str(src) + ',dst=' + dst + ',options=rbind:' + ('rw' if writable else 'ro')]

    def launch(name, image, command, mounts, memory):
        namespace()
        output = (work / (name + '.log')).open('wb')
        args = ctr + ['run', '--rm', '--read-only', '--seccomp', '--memory-limit', str(memory),
                      '--cpu-quota', '100000', '--cpu-period', '100000',
                      '--with-ns', 'network:/run/netns/' + NETNS] + mounts + [image, name] + command
        process = subprocess.Popen(args, stdout=output, stderr=subprocess.STDOUT)
        processes.append((name, process, output))

    def client(args, ok=True):
        command = ctr + ['run', '--rm', '--read-only', '--with-ns', 'network:/run/netns/' + NETNS]
        command += mount(work / 'pki', '/pki')
        return run(command + [ETCD_IMAGE, 'etcd-recovery-client', '/usr/local/bin/etcdctl',
                              '--endpoints=https://127.0.0.1:2379', '--cacert=/pki/etcd/ca.crt',
                              '--cert=/pki/etcd/healthcheck-client.crt', '--key=/pki/etcd/healthcheck-client.key'] + args, ok)

    def request(path, authenticated=True, ok=True):
        args = ['ip', 'netns', 'exec', NETNS, 'curl', '--silent', '--show-error', '--fail',
                '--max-time', '20', '--cacert', str(work / 'pki/ca.crt')]
        if authenticated:
            args += ['--cert', str(work / 'admin.crt'), '--key', str(work / 'admin.key')]
        return run(args + ['https://' + address + ':6443' + path], ok, 30)

    try:
        run(['ip', 'netns', 'add', NETNS]); network_created = True
        run(['ip', '-n', NETNS, 'link', 'set', 'lo', 'up'])
        run(['ip', '-n', NETNS, 'addr', 'add', address + '/32', 'dev', 'lo'])
        namespace()
        command = ctr + ['run', '--rm', '--read-only'] + mount(source, '/input')
        status = json.loads(run(command + [ETCD_IMAGE, 'etcd-recovery-status', '/usr/local/bin/etcdctl',
                                         'snapshot', 'status', '/input/snapshot.db', '--write-out=json']).stdout)
        # Use the binary actually shipped by kubeadm's pinned image. Do not skip hashes.
        command = ctr + ['run', '--rm', '--read-only'] + mount(source, '/input') + mount(work, '/recovery', True)
        run(command + [ETCD_IMAGE, 'etcd-recovery-restore', '/usr/local/bin/etcdctl', 'snapshot', 'restore',
                       '/input/snapshot.db', '--data-dir=/recovery/data', '--name=' + flag(etcd['command'], '--name'),
                       '--initial-advertise-peer-urls=' + flag(etcd['command'], '--initial-advertise-peer-urls'),
                       '--initial-cluster=' + flag(etcd['command'], '--initial-cluster'),
                       '--bump-revision=' + str(BUMP), '--mark-compacted'])
        launch('etcd-recovery-server', ETCD_IMAGE, etcd['command'],
               mount(work / 'pki', '/etc/kubernetes/pki') + mount(work / 'data', '/var/lib/etcd', True), 384 * 1024 * 1024)
        for _ in range(30):
            if client(['endpoint', 'health'], ok=False).returncode == 0:
                break
            time.sleep(2)
        else:
            raise RuntimeError('Restored etcd did not become healthy')
        endpoint = json.loads(client(['endpoint', 'status', '--write-out=json']).stdout)[0]['Status']
        if endpoint['header']['revision'] < status['revision'] + BUMP:
            raise RuntimeError('Revision bump was not applied')
        stale = client(['get', '/registry/namespaces/default', '--rev=' + str(status['revision'])], ok=False)
        if stale.returncode == 0 or b'compacted' not in stale.stderr:
            raise RuntimeError('Old revision was not compacted')
        counts = {}
        for resource in ('namespaces', 'nodes', 'deployments', 'secrets'):
            counts[resource] = json.loads(client(['get', '/registry/' + ('minions' if resource == 'nodes' else resource) + '/',
                                                 '--prefix', '--keys-only', '--write-out=json']).stdout)['count']
        # Generate a temporary client identity from the recovered CA, never print keys.
        run(['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(work / 'admin.key'),
             '-out', str(work / 'admin.csr'), '-subj', '/CN=etcd-recovery-check/O=system:masters'])
        (work / 'client.ext').write_text('extendedKeyUsage=clientAuth\n')
        run(['openssl', 'x509', '-req', '-in', str(work / 'admin.csr'), '-CA', str(work / 'pki/ca.crt'),
             '-CAkey', str(work / 'pki/ca.key'), '-set_serial', '0x' + os.urandom(16).hex(), '-days', '1',
             '-extfile', str(work / 'client.ext'), '-out', str(work / 'admin.crt')])
        api_command = api['command'] + ['--bind-address=' + address]
        launch('etcd-recovery-api', API_IMAGE, api_command,
               mount(work / 'pki', '/etc/kubernetes/pki') + mount(work / 'audit', '/var/log/kubernetes/audit', True)
               + mount(source / 'audit-policy.yml', '/etc/kubernetes/audit/audit-policy.yml'), 768 * 1024 * 1024)
        for _ in range(60):
            if request('/readyz', ok=False).stdout.strip() == b'ok':
                break
            time.sleep(2)
        else:
            raise RuntimeError('Recovered API server did not become ready')
        actual = {}
        for resource in counts:
            path = ('/apis/apps/v1/' if resource == 'deployments' else '/api/v1/') + resource
            items = json.loads(request(path).stdout)['items']
            actual[resource] = len(items)
            if actual[resource] != counts[resource] or not actual[resource]:
                raise RuntimeError('API/etcd object counts differ: ' + resource)
        if request('/api/v1/secrets', authenticated=False, ok=False).returncode == 0:
            raise RuntimeError('Unauthenticated secret access unexpectedly succeeded')
        namespace()
        evidence = {'snapshot_revision': status['revision'], 'restored_revision': endpoint['header']['revision'],
                    'snapshot_sha256': hashlib.sha256((source / 'snapshot.db').read_bytes()).hexdigest(),
                    'snapshot_hash_verified': True, 'revision_bumped': True, 'old_revision_compacted': True,
                    'original_pki_tls_verified': True, 'etcd_healthy': True, 'api_ready': True,
                    'object_counts': actual, 'anonymous_secret_access_denied': True,
                    'network': 'loopback only; no external routes', 'controllers_started': False}
        (work / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps(evidence), flush=True)
    finally:
        failed_cleanup = []
        for name, process, output in reversed(processes):
            run(ctr + ['tasks', 'kill', '--signal', 'SIGTERM', name], ok=False)
            try:
                process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                run(ctr + ['tasks', 'kill', '--signal', 'SIGKILL', name], ok=False)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    failed_cleanup.append(name)
            output.close()
        if network_created and not failed_cleanup:
            run(['ip', 'netns', 'delete', NETNS])
        log.close()
        if failed_cleanup:
            raise RuntimeError('Inspect surviving drill tasks before removing private material')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path, help='New private directory; never an existing data directory')
    args = parser.parse_args()
    main(args.source, args.work)
