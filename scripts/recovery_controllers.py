"""Controller/bootstrap checks used only by the disconnected etcd recovery verifier."""
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import time


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def controller_source(source, component):
    value = json.loads((source / (component + '-source.json')).read_text())
    if value['image'] != 'registry.k8s.io/' + component + ':v1.31.4':
        raise RuntimeError('Revalidate controller tooling for changed images')
    return value


def verify(work, source, address, run, mount, launch, request):
    available_kib = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:")))
    if available_kib < 512 * 1024:
        raise RuntimeError("At least 512 MiB headroom is required before starting recovery controllers")
    started = now()
    controllers = {name: controller_source(source, name) for name in ('kube-controller-manager', 'kube-scheduler')}
    # Distinct identities exercise the recovered RBAC rather than using the admin certificate.
    for component, config in [('kube-controller-manager', 'controller-manager.conf'), ('kube-scheduler', 'scheduler.conf')]:
        key, csr, cert = [work / (component + suffix) for suffix in ('.key', '.csr', '.crt')]
        run(['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key),
             '-out', str(csr), '-subj', '/CN=system:' + component])
        run(['openssl', 'x509', '-req', '-in', str(csr), '-CA', str(work / 'pki/ca.crt'),
             '-CAkey', str(work / 'pki/ca.key'), '-set_serial', '0x' + os.urandom(16).hex(), '-days', '1',
             '-extfile', str(work / 'client.ext'), '-out', str(cert)])
        encode = lambda path: base64.b64encode(path.read_bytes()).decode()
        kubeconfig = {'apiVersion': 'v1', 'kind': 'Config',
                      'clusters': [{'name': 'restored', 'cluster': {'server': 'https://' + address + ':6443',
                                    'certificate-authority-data': encode(work / 'pki/ca.crt')}}],
                      'users': [{'name': component, 'user': {'client-certificate-data': encode(cert), 'client-key-data': encode(key)}}],
                      'contexts': [{'name': 'restored', 'context': {'cluster': 'restored', 'user': component}}],
                      'current-context': 'restored'}
        (work / config).write_text(json.dumps(kubeconfig))
        mounts = mount(work / config, '/etc/kubernetes/' + config)
        if component == 'kube-controller-manager':
            mounts += mount(work / 'pki', '/etc/kubernetes/pki')
        launch('etcd-recovery-' + component, controllers[component]['image'], controllers[component]['command'],
               mounts, (256 if component == 'kube-controller-manager' else 128) * 1024 * 1024)
    leases = {}
    for _ in range(45):
        for component in controllers:
            result = request('/apis/coordination.k8s.io/v1/namespaces/kube-system/leases/' + component, ok=False)
            if result.http_status == 200:
                lease = json.loads(result.stdout)
                if lease['spec'].get('renewTime', '')[:19] >= started[:19]:
                    leases[component] = lease['spec']['holderIdentity']
        if len(leases) == 2:
            break
        time.sleep(2)
    else:
        raise RuntimeError('Recovered controllers did not acquire and renew leader leases')

    node = 'etcd-recovery-check'
    token_id, token_secret = secrets.token_hex(3), secrets.token_hex(8)
    expiration = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat().replace('+00:00', 'Z')
    token = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'bootstrap-token-' + token_id, 'namespace': 'kube-system'},
             'type': 'bootstrap.kubernetes.io/token', 'stringData': {'token-id': token_id, 'token-secret': token_secret,
             'expiration': expiration, 'usage-bootstrap-authentication': 'true', 'usage-bootstrap-signing': 'true',
             'auth-extra-groups': 'system:bootstrappers:kubeadm:default-node-token'}}
    request('/api/v1/namespaces/kube-system/secrets', method='POST', data=token)
    header = work / 'bootstrap.header'
    header.write_text('Authorization: Bearer ' + token_id + '.' + token_secret + '\n')
    key, csr = work / 'node.key', work / 'node.csr'
    run(['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key), '-out', str(csr),
         '-subj', '/CN=system:node:' + node + '/O=system:nodes'])
    signing = {'apiVersion': 'certificates.k8s.io/v1', 'kind': 'CertificateSigningRequest', 'metadata': {'name': node},
               'spec': {'request': base64.b64encode(csr.read_bytes()).decode(),
                        'signerName': 'kubernetes.io/kube-apiserver-client-kubelet',
                        'expirationSeconds': 3600, 'usages': ['digital signature', 'key encipherment', 'client auth']}}
    request('/apis/certificates.k8s.io/v1/certificatesigningrequests', method='POST', data=signing,
            authenticated=False, header=header)
    for _ in range(45):
        signed = json.loads(request('/apis/certificates.k8s.io/v1/certificatesigningrequests/' + node).stdout)
        if signed.get('status', {}).get('certificate'):
            if not any(x['type'] == 'Approved' and x['status'] == 'True' for x in signed['status']['conditions']):
                raise RuntimeError('Signed bootstrap CSR has no approval condition')
            break
        time.sleep(2)
    else:
        raise RuntimeError('Bootstrap CSR was not automatically approved and signed')
    cert = work / 'node.crt'; cert.write_bytes(base64.b64decode(signed['status']['certificate']))
    run(['openssl', 'verify', '-CAfile', str(work / 'pki/ca.crt'), str(cert)])
    identity = {'authenticated': False, 'certificate': (cert, key)}
    request('/api/v1/nodes', method='POST', data={'apiVersion': 'v1', 'kind': 'Node', 'metadata': {
        'name': node, 'labels': {'recovery-test': node}}}, **identity)
    forbidden = request('/api/v1/secrets', ok=False, **identity)
    if forbidden.http_status != 403:
        raise RuntimeError('Bootstrapped node identity must not list unrelated Secrets')

    deployment = {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': node, 'namespace': 'kube-system'},
                  'spec': {'replicas': 1, 'selector': {'matchLabels': {'recovery-test': node}}, 'template': {
                      'metadata': {'labels': {'recovery-test': node}}, 'spec': {'automountServiceAccountToken': False,
                      'nodeSelector': {'recovery-test': node}, 'containers': [{'name': 'fixture', 'image': 'registry.k8s.io/pause:3.10.2',
                      'resources': {'requests': {'cpu': '10m', 'memory': '16Mi'}}, 'securityContext': {
                      'runAsNonRoot': True, 'runAsUser': 65534, 'allowPrivilegeEscalation': False,
                      'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}}}]}}}}
    request('/apis/apps/v1/namespaces/kube-system/deployments', method='POST', data=deployment)
    for _ in range(60):
        stamp = now()
        obj = json.loads(request('/api/v1/nodes/' + node, **identity).stdout)
        obj['status'] = {'capacity': {'cpu': '1', 'memory': '128Mi', 'pods': '5'},
                         'allocatable': {'cpu': '1', 'memory': '128Mi', 'pods': '5'},
                         'conditions': [{'type': 'Ready', 'status': 'True', 'lastHeartbeatTime': stamp,
                                         'lastTransitionTime': stamp, 'reason': 'IsolatedProtocolFixture'}]}
        request('/api/v1/nodes/' + node + '/status', method='PUT', data=obj, **identity)
        pods = json.loads(request('/api/v1/namespaces/kube-system/pods?labelSelector=recovery-test%3D' + node).stdout)['items']
        if len(pods) == 1 and pods[0]['spec'].get('nodeName') == node:
            if pods[0]['status'].get('phase') == 'Running':
                raise RuntimeError('Fixture must not execute without a real recovery kubelet')
            break
        time.sleep(2)
    else:
        raise RuntimeError('Recovered controllers did not create and schedule the fixture Pod')
    request('/api/v1/namespaces/kube-system/secrets/bootstrap-token-' + token_id, method='DELETE')
    return {'controller_leases_renewed': True, 'deployment_replicaset_pod_created': True, 'scheduler_binding': True,
            'bootstrap_csr_autoapproved_and_signed': True, 'node_certificate_registration': True,
            'node_unrelated_secret_list_denied': True, 'kubelet_started': False, 'workload_executed': False}
