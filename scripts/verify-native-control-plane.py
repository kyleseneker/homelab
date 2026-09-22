#!/usr/bin/env python3
"""Boot backed-up static control-plane pods on a fresh, isolated lab machine.

This deliberately uses standalone kubelet: recovered API workloads must never run.
Requires a VM rollback backup, stopped lab worker, host egress block and cached images.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import yaml

COMPONENTS = ('etcd', 'kube-apiserver', 'kube-controller-manager', 'kube-scheduler')
ETCD = 'registry.k8s.io/etcd:3.5.15-0'
ADDRESS = '192.168.10.50'
ROOT = Path('/var/tmp/native-control-plane')


def run(args, timeout=120, data=None):
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    with (ROOT / 'commands.log').open('ab') as log:
        log.write(result.stderr)
    if result.returncode:
        raise RuntimeError('Recovery command failed; inspect private commands.log: ' + args[0])
    return result.stdout


def flag(command, name):
    values = [x.split('=', 1)[1] for x in command if x.startswith(name + '=')]
    if len(values) != 1:
        raise ValueError('Expected one ' + name)
    return values[0]


def standalone(config):
    """Disable API Pod watching and the kubelet API while preserving static settings."""
    config = dict(config)
    config.update(enableServer=False, rotateCertificates=False, serverTLSBootstrap=False)
    config['authentication'] = {'anonymous': {'enabled': False}, 'webhook': {'enabled': False}}
    config['authorization'] = {'mode': 'AlwaysAllow'}
    if config.get('staticPodPath') != '/etc/kubernetes/manifests':
        raise ValueError('Unexpected static Pod directory')
    return config


def empty_manifests(directory):
    # The Debian kubelet package installs this empty marker on fresh machines.
    return all(path.name == '.kubelet-keep' and not path.is_symlink()
               and path.is_file() and path.stat().st_size == 0 for path in directory.glob('*'))


def install(source):
    if Path('/var/lib/etcd').exists() or not empty_manifests(Path('/etc/kubernetes/manifests')):
        raise RuntimeError('Refusing a previously initialized machine')
    if Path('/etc/kubernetes/kubelet.conf').exists() or Path('/etc/kubernetes/admin.conf').exists():
        raise RuntimeError('Fresh guest must not have cluster client credentials')
    if source.stat().st_mode & 0o077:
        raise RuntimeError('Recovery input directory must be private')
    host = source / 'control-plane'
    manifests = {}
    for component in COMPONENTS:
        pod = yaml.safe_load((host / ('etc/kubernetes/manifests/' + component + '.yaml')).read_text())
        containers = pod['spec']['containers']
        image = ETCD if component == 'etcd' else 'registry.k8s.io/' + component + ':v1.31.4'
        if pod['kind'] != 'Pod' or len(containers) != 1 or containers[0]['image'] != image:
            raise RuntimeError('Revalidate changed static control-plane image')
        manifests[component] = pod
    etcd = manifests['etcd']['spec']['containers'][0]['command']
    api = manifests['kube-apiserver']['spec']['containers'][0]['command']
    if flag(api, '--advertise-address') != ADDRESS:
        raise RuntimeError('Unexpected source control-plane identity')
    if flag(etcd, '--data-dir') != '/var/lib/etcd':
        raise RuntimeError('Unexpected etcd data directory')
    run(['systemctl', 'stop', 'kubelet'])
    # The guest block persists across reboot; the host block must already be active.
    rules = '''table inet native_recovery {
 chain output { type filter hook output priority -50; policy drop;
  oifname "lo" accept
  ip daddr 172.26.0.1 tcp sport 22 ct state established accept
 }
 chain input { type filter hook input priority -50; policy drop;
  iifname "lo" accept
  ip saddr 172.26.0.1 tcp dport 22 accept
 }
}'''
    (ROOT / 'isolation.nft').write_text(rules + '\n')
    unit = '''[Unit]
Description=Disconnected native control-plane recovery boundary
Before=containerd.service kubelet.service
[Service]
Type=oneshot
ExecStart=/usr/sbin/nft -f /var/tmp/native-control-plane/isolation.nft
ExecStart=/usr/sbin/ip address add 192.168.10.50/32 dev lo
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
'''
    Path('/etc/systemd/system/native-recovery-isolation.service').write_text(unit)
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', '--now', 'native-recovery-isolation.service'])
    import tarfile
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location('prepare', Path(__file__).with_name('prepare-etcd-recovery.py'))
    prepare = module_from_spec(spec)
    spec.loader.exec_module(prepare)
    with tarfile.open(source / 'pki.tar.gz') as archive:
        prepare.validate_archive(archive, pki=True)
        archive.extractall('/etc/kubernetes')
    for relative in ('etc/kubernetes/controller-manager.conf', 'etc/kubernetes/scheduler.conf',
                     'etc/kubernetes/kubeadm-config.yml', 'etc/kubernetes/audit/audit-policy.yml',
                     'etc/containerd/config.toml', 'etc/default/kubelet', 'var/lib/kubelet/kubeadm-flags.env'):
        target = Path('/') / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(host / relative, target)
    config = standalone(yaml.safe_load((host / 'var/lib/kubelet/config.yaml').read_text()))
    Path('/var/lib/kubelet/config.yaml').write_text(yaml.safe_dump(config))
    Path('/var/log/kubernetes/audit').mkdir(parents=True, exist_ok=True)
    run(['systemctl', 'restart', 'containerd'])
    def mount(src, dst, mode):
        return ['--mount', 'type=bind,src=' + str(src) + ',dst=' + dst + ',options=rbind:' + mode]
    ctr = ['ctr', '-n', 'k8s.io', 'run', '--rm', '--read-only']
    status = json.loads(run(ctr + mount(source, '/input', 'ro') +
                            [ETCD, 'native-snapshot-status', '/usr/local/bin/etcdctl', 'snapshot', 'status',
                             '/input/snapshot.db', '--write-out=json']))
    run(ctr + mount(source, '/input', 'ro') + mount('/var/lib', '/recovery', 'rw') +
        [ETCD, 'native-snapshot-restore', '/usr/local/bin/etcdctl', 'snapshot', 'restore', '/input/snapshot.db',
         '--data-dir=/recovery/etcd', '--name=' + flag(etcd, '--name'),
         '--initial-advertise-peer-urls=' + flag(etcd, '--initial-advertise-peer-urls'),
         '--initial-cluster=' + flag(etcd, '--initial-cluster'), '--bump-revision=1000000000', '--mark-compacted'])
    # Recovered API objects cannot supply Pods to a kubelet without a kubeconfig.
    dropin = Path('/etc/systemd/system/kubelet.service.d/30-native-recovery.conf')
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text('''[Unit]
Requires=native-recovery-isolation.service
After=native-recovery-isolation.service
[Service]
ExecStart=
ExecStart=/usr/bin/kubelet --config=/var/lib/kubelet/config.yaml --container-runtime-endpoint=unix:///run/containerd/containerd.sock --register-node=false
''')
    for component, pod in manifests.items():
        target = Path('/etc/kubernetes/manifests') / (component + '.yaml')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(pod))
    run(['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(ROOT / 'admin.key'),
         '-out', str(ROOT / 'admin.csr'), '-subj', '/CN=native-recovery-check/O=system:masters'])
    (ROOT / 'client.ext').write_text('extendedKeyUsage=clientAuth\n')
    run(['openssl', 'x509', '-req', '-in', str(ROOT / 'admin.csr'), '-CA', '/etc/kubernetes/pki/ca.crt',
         '-CAkey', '/etc/kubernetes/pki/ca.key', '-set_serial', '0x' + os.urandom(16).hex(), '-days', '1',
         '-extfile', str(ROOT / 'client.ext'), '-out', str(ROOT / 'admin.crt')])
    (ROOT / 'source.json').write_text(json.dumps({'snapshot_revision': status['revision'],
        'snapshot_sha256': hashlib.sha256((source / 'snapshot.db').read_bytes()).hexdigest(),
        'machine_id': Path('/etc/machine-id').read_text().strip()}))
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'restart', 'kubelet'])


def verify():
    def api(path):
        return run(['curl', '--silent', '--show-error', '--fail', '--max-time', '5',
                    '--cacert', '/etc/kubernetes/pki/ca.crt', '--cert', str(ROOT / 'admin.crt'),
                    '--key', str(ROOT / 'admin.key'), 'https://' + ADDRESS + ':6443' + path], timeout=10)
    for _ in range(90):
        try:
            if api('/readyz').strip() == b'ok':
                break
        except RuntimeError:
            pass
        time.sleep(2)
    else:
        raise RuntimeError('Native API failed readiness')
    config = run(['systemctl', 'show', 'kubelet', '--property=ExecStart']).decode()
    if '--kubeconfig' in config or '--bootstrap-kubeconfig' in config or '--register-node=false' not in config:
        raise RuntimeError('Kubelet must run without API workload access')
    for unit in ('kubelet', 'containerd', 'native-recovery-isolation'):
        run(['systemctl', 'is-active', '--quiet', unit])
    run(['nft', 'list', 'table', 'inet', 'native_recovery'])
    cri = ['crictl', '--runtime-endpoint', 'unix:///run/containerd/containerd.sock']
    for _ in range(60):
        containers = json.loads(run(cri + ['ps', '-o', 'json']))['containers']
        names = sorted(x['metadata']['name'] for x in containers)
        if names == sorted(COMPONENTS):
            break
        if any(x not in COMPONENTS for x in names):
            raise RuntimeError('Unexpected workload in native runtime')
        time.sleep(2)
    else:
        raise RuntimeError('Expected four running static control-plane containers')
    etcd_id = next(x['id'] for x in containers if x['metadata']['name'] == 'etcd')
    client = cri + ['exec', etcd_id, '/usr/local/bin/etcdctl', '--endpoints=https://127.0.0.1:2379',
                    '--cacert=/etc/kubernetes/pki/etcd/ca.crt',
                    '--cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt',
                    '--key=/etc/kubernetes/pki/etcd/healthcheck-client.key']
    endpoint = json.loads(run(client + ['endpoint', 'status', '--write-out=json']))[0]['Status']
    origin = json.loads((ROOT / 'source.json').read_text())
    if endpoint['header']['revision'] < origin['snapshot_revision'] + 1000000000:
        raise RuntimeError('Native etcd is missing the recovery revision bump')
    counts = {}
    for resource in ('namespaces', 'nodes', 'deployments', 'secrets'):
        prefix = '/apis/apps/v1/' if resource == 'deployments' else '/api/v1/'
        counts[resource] = len(json.loads(api(prefix + resource))['items'])
    leases = json.loads(api('/apis/coordination.k8s.io/v1/namespaces/kube-system/leases'))['items']
    previous = {x['metadata']['name']: x['spec'].get('renewTime') for x in leases
                if x['metadata']['name'] in ('kube-controller-manager', 'kube-scheduler')}
    time.sleep(6)
    leases = json.loads(api('/apis/coordination.k8s.io/v1/namespaces/kube-system/leases'))['items']
    renewed = {x['metadata']['name'] for x in leases if x['metadata']['name'] in previous
               and x['spec'].get('renewTime') != previous[x['metadata']['name']]}
    if renewed != {'kube-controller-manager', 'kube-scheduler'}:
        raise RuntimeError('Recovered controller leases did not renew')
    blocked = []
    for host, port in [('1.1.1.1', 443), ('192.168.10.51', 10250),
                       ('192.168.1.158', 2049), ('172.26.0.1', 22)]:
        try:
            connection = socket.create_connection((host, port), timeout=2)
        except socket.timeout:
            blocked.append(host + ':' + str(port))
        else:
            connection.close()
            raise RuntimeError('Guest egress isolation failed')
    evidence = json.loads((ROOT / 'source.json').read_text())
    evidence.update(restored_revision=endpoint['header']['revision'], boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(), api_ready=True,
                    standalone_kubelet=True, running_containers=names, object_counts=counts, blocked_endpoints=blocked,
                    controller_leases_renewed=True, production_workloads_executed=False,
                    production_cni_tested=False)
    (ROOT / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print('Native static control plane ready; four containers only; controller leases renewed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['install', 'verify'])
    parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0 or socket.gethostname() != 'homelabrestore01-node-1':
        raise RuntimeError('Run only as root on the disposable lab control-plane VM')
    os.umask(0o077)
    if args.operation == 'install':
        if not args.source or ROOT.exists():
            raise RuntimeError('Require input and a fresh drill directory')
        ROOT.mkdir(mode=0o700)
        install(args.source)
    verify()
