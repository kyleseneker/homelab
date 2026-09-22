#!/usr/bin/env python3
"""Enable normal kubelet on the quarantined disposable recovery control plane."""
import argparse
import base64
import importlib.util
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket

import yaml

ROOT = Path('/var/tmp/native-control-plane')


def bootstrap(source, values):
    if os.geteuid() != 0 or socket.gethostname() != 'homelabrestore01-node-1':
        raise RuntimeError('Run only on the disposable control plane')
    quarantine = json.loads((ROOT / 'quarantine.json').read_text())
    if not quarantine.get('execution_records_empty') or Path('/etc/kubernetes/kubelet.conf').exists():
        raise RuntimeError('Require a quarantined, not-yet-joined recovery copy')
    if hashlib.sha256((source / 'snapshot.db').read_bytes()).hexdigest() != quarantine['source_snapshot_sha256']:
        raise RuntimeError('Quarantine evidence does not match the supplied recovery bundle')
    spec = importlib.util.spec_from_file_location('native', Path(__file__).with_name('verify-native-control-plane.py'))
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    run = native.run
    def request(path):
        return json.loads(run(['curl', '--silent', '--show-error', '--fail', '--max-time', '10',
                              '--cacert', '/etc/kubernetes/pki/ca.crt', '--cert', str(ROOT / 'admin.crt'),
                              '--key', str(ROOT / 'admin.key'), 'https://' + native.ADDRESS + ':6443' + path]))
    # Recheck the API immediately before enabling its workload watch.
    for path in ('/api/v1/pods', '/api/v1/replicationcontrollers', '/api/v1/nodes',
                 '/apis/apps/v1/deployments', '/apis/apps/v1/daemonsets', '/apis/apps/v1/statefulsets',
                 '/apis/apps/v1/replicasets', '/apis/batch/v1/jobs', '/apis/batch/v1/cronjobs',
                 '/apis/admissionregistration.k8s.io/v1/mutatingwebhookconfigurations',
                 '/apis/admissionregistration.k8s.io/v1/validatingwebhookconfigurations'):
        if request(path)['items']:
            raise RuntimeError('Quarantine is incomplete: ' + path)
    encode = lambda path: base64.b64encode(Path(path).read_bytes()).decode()
    config = {'apiVersion': 'v1', 'kind': 'Config', 'current-context': 'recovered-network',
              'clusters': [{'name': 'recovered', 'cluster': {'server': 'https://' + native.ADDRESS + ':6443',
                            'certificate-authority-data': encode('/etc/kubernetes/pki/ca.crt')}}],
              'users': [{'name': 'recovery-admin', 'user': {'client-certificate-data': encode(ROOT / 'admin.crt'),
                         'client-key-data': encode(ROOT / 'admin.key')}}],
              'contexts': [{'name': 'recovered-network', 'context': {'cluster': 'recovered', 'user': 'recovery-admin'}}]}
    Path('/etc/kubernetes/admin.conf').write_text(json.dumps(config))
    Path('/root/.kube').mkdir(mode=0o700, exist_ok=True)
    shutil.copyfile('/etc/kubernetes/admin.conf', '/root/.kube/config')
    documents = list(yaml.safe_load_all((source / 'control-plane/etc/kubernetes/kubeadm-config.yml').read_text()))
    cluster = next(x for x in documents if x['kind'] == 'ClusterConfiguration')
    cluster['controlPlaneEndpoint'] = native.ADDRESS + ':6443'
    configuration = ROOT / 'kubeadm-recovered-node.yml'
    configuration.write_text(yaml.safe_dump(cluster))
    # Run only the certificate/kubeconfig phase; never initialize a new etcd or API.
    run(['kubeadm', 'init', 'phase', 'kubeconfig', 'kubelet', '--config', str(configuration)])
    shutil.copyfile(source / 'control-plane/var/lib/kubelet/config.yaml', '/var/lib/kubelet/config.yaml')
    pools = yaml.safe_load(values.read_text())['ipam']['operator']['clusterPoolIPv4PodCIDRList']
    networks = [ipaddress.ip_network(x) for x in pools]
    if not networks or any(x.version != 4 or not x.subnet_of(ipaddress.ip_network('10.0.0.0/8')) for x in networks):
        raise RuntimeError('Revalidate changed production pod ranges')
    allowed = ', '.join(['172.26.0.10', '172.26.0.11'] + [str(x) for x in networks])
    rules = (ROOT / 'isolation.nft').read_text()
    rules = rules.replace('oifname "lo" accept', 'oifname "lo" accept\n  ip daddr { ' + allowed + ' } accept')
    rules = rules.replace('iifname "lo" accept', 'iifname "lo" accept\n  ip saddr { ' + allowed + ' } accept')
    # One nft transaction changes only the guest drill table. The Proxmox boundary
    # remains mandatory: pod/node communication must not enable external access.
    rules = rules.replace('tcp sport 22 ct state established', 'ct state established,related').replace('tcp dport 22 accept', 'accept')
    # Cilium's transparent Gateway proxy replies bypass the ordinary conntrack
    # state match. Permit only HTTP replies to the administering Proxmox host.
    rules = rules.replace('oifname "lo" accept', 'oifname "lo" accept\n  ip daddr 172.26.0.1 tcp sport 80 accept')
    rules = 'add table inet native_recovery\nflush table inet native_recovery\n' + rules
    (ROOT / 'isolation.nft').write_text(rules)
    run(['nft', '-f', str(ROOT / 'isolation.nft')])
    Path('/etc/systemd/system/kubelet.service.d/30-native-recovery.conf').unlink()
    Path('/etc/systemd/system/kubelet.service.d/30-recovery-network.conf').write_text('''[Unit]
Requires=native-recovery-isolation.service
After=native-recovery-isolation.service
''')
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'restart', 'kubelet'])
    print('Normal control-plane kubelet enabled after empty-workload verification; original CA and configuration retained.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cilium-values', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    bootstrap(args.source, args.cilium_values)
