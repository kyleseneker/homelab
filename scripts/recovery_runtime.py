"""Real kubelet/CRI check inside the disconnected recovery network namespace.

Called only by verify-etcd-recovery.py after its controller/bootstrap checks.
The recovered controllers are stopped before this module connects a kubelet.
"""
import base64
import json
from pathlib import Path
import time

NETNS = 'homelab-etcd-recovery'
NODE = 'etcd-recovery-check'
POD = 'etcd-runtime-check'
IMAGE = 'registry.k8s.io/pause:3.10.2'
CGROUP = Path('/sys/fs/cgroup/etcd-recovery-pods')
UNITS = ['etcd-recovery-runtime', 'etcd-recovery-kubelet']


def owned_pods(request):
    return json.loads(request('/api/v1/pods?fieldSelector=spec.nodeName%3D' + NODE).stdout)['items']


def runtime_config(root):
    sock = root / 'containerd.sock'
    return f'''version = 4
root = '{root / "data"}'
state = '{root / "state"}'
imports = ['{root / "conf.d/*.toml"}']
disabled_plugins = ['io.containerd.nri.v1.nri']
[plugins.'io.containerd.server.v1.grpc']
  address = '{sock}'
[plugins.'io.containerd.server.v1.ttrpc']
  address = '{root / "containerd.ttrpc"}'
[plugins.'io.containerd.server.v1.grpc-tcp']
  address = ''
[plugins.'io.containerd.server.v1.debug']
  address = ''
[plugins.'io.containerd.server.v1.metrics']
  address = ''
[plugins.'io.containerd.shim.v1.manager']
  socket_dir = '/run/containerd/s'
[plugins.'io.containerd.cri.v1.images'.pinned_images]
  sandbox = '{IMAGE}'
[plugins.'io.containerd.cri.v1.runtime']
  netns_mounts_under_state_dir = true
  enable_cdi = false
[plugins.'io.containerd.cri.v1.runtime'.containerd]
  default_runtime_name = 'runc'
[plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.runc]
  runtime_type = 'io.containerd.runc.v2'
[plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.runc.options]
  SystemdCgroup = false
[plugins.'io.containerd.cri.v1.runtime'.cni]
  bin_dirs = ['/opt/cni/bin']
  conf_dir = '{root / "cni"}'
'''


def isolation_command(command, network=True):
    # Mask original sockets, state, and credentials before parsing config or
    # starting either service. Config v4 retains its built-in conf.d import glob.
    mounts = ('mount -t tmpfs -o mode=0700 tmpfs /run/containerd; '
              'mount -t tmpfs -o mode=0700 tmpfs /var/lib; '
              'mount -t tmpfs -o mode=0700 tmpfs /etc/kubernetes; '
              'mount -t tmpfs -o mode=0700 tmpfs /etc/containerd; ')
    prefix = ['unshare', '--mount', '--propagation', 'private', 'sh', '-ec',
              mounts + 'exec "$@"', 'recovery-isolation']
    # ip netns exec remounts sysfs and hides the cgroup v2 mount.
    return prefix + (['nsenter', '--net=/run/netns/' + NETNS] if network else []) + command


def validate_runtime_config(config, root, host_config_masked=False):
    expected = {
        'io.containerd.server.v1.grpc': str(root / 'containerd.sock'),
        'io.containerd.server.v1.ttrpc': str(root / 'containerd.ttrpc'),
        'io.containerd.server.v1.grpc-tcp': '',
        'io.containerd.server.v1.debug': '',
        'io.containerd.server.v1.metrics': '',
    }
    allowed_imports = {str(root / 'conf.d/*.toml')}
    if host_config_masked:
        allowed_imports.add('/etc/containerd/conf.d/*.toml')
    if (config.get('root') != str(root / 'data') or config.get('state') != str(root / 'state')
            or not set(config.get('imports', [])).issubset(allowed_imports)):
        raise RuntimeError('Effective containerd roots/imports are not isolated')
    plugins = config.get('plugins', {})
    for plugin, address in expected.items():
        if plugins.get(plugin, {}).get('address') != address:
            raise RuntimeError('Effective containerd socket is not isolated: ' + plugin)
    shim_paths = {str(root / 'shim-sockets')}
    if host_config_masked:
        shim_paths.add('/run/containerd/s')
    if plugins.get('io.containerd.shim.v1.manager', {}).get('socket_dir') not in shim_paths:
        raise RuntimeError('Effective containerd shim socket directory is not isolated')


def verify(work, run, request, stop):
    if run(['kubelet', '--version']).stdout.strip() != b'Kubernetes v1.31.4':
        raise RuntimeError('Revalidate runtime recovery for a changed kubelet version')
    runtime_version = run(['containerd', '--version']).stdout.decode().split()
    if not any(v in runtime_version for v in ('v2.3.5', '2.3.5')):
        raise RuntimeError('Revalidate runtime recovery for a changed containerd version')
    for name in ('etcd-recovery-kube-scheduler', 'etcd-recovery-kube-controller-manager'):
        stop(name)
    available_kib = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))
    if available_kib < 640 * 1024 or CGROUP.exists():
        raise RuntimeError('Runtime drill needs 640 MiB headroom and a new dedicated pod cgroup')
    for unit in UNITS:
        if run(['systemctl', 'is-active', unit], ok=False).returncode == 0:
            raise RuntimeError('An earlier drill service is still active')
    # Only the disconnected copy is modified. With its scheduler stopped, no other
    # restored workload can become assigned to this new node during the drill.
    for pod in owned_pods(request):
        request('/api/v1/namespaces/' + pod['metadata']['namespace'] + '/pods/' + pod['metadata']['name'],
                method='DELETE', data={'apiVersion': 'v1', 'kind': 'DeleteOptions', 'gracePeriodSeconds': 0})
    for _ in range(20):
        if not owned_pods(request):
            break
        time.sleep(1)
    else:
        raise RuntimeError('Assigned restored Pods must be removed before starting the recovery kubelet')
    root = work / 'runtime'; root.mkdir(mode=0o700)
    for directory in ('state', 'data', 'cni', 'conf.d', 'kubelet', 'certs', 'pod-logs'):
        (root / directory).mkdir()
    sock = root / 'containerd.sock'
    config = runtime_config(root)
    (root / 'containerd.toml').write_text(config)
    import tomllib
    effective = run(isolation_command(['containerd', '--config', str(root / 'containerd.toml'), 'config', 'dump'], network=False)).stdout.decode()
    validate_runtime_config(tomllib.loads(effective), root, host_config_masked=True)
    original_socket = Path('/run/containerd/containerd.sock').stat().st_ino
    # Loaded solely to satisfy CRI initialization; the fixture uses hostNetwork
    # within the disconnected namespace. This does not test production Cilium.
    (root / 'cni/10-recovery.conflist').write_text(json.dumps({'cniVersion': '1.0.0', 'name': 'recovery-loopback', 'plugins': [{'type': 'loopback'}]}))
    encode = lambda path: base64.b64encode(path.read_bytes()).decode()
    kubeconfig = {'apiVersion': 'v1', 'kind': 'Config',
                  'clusters': [{'name': 'restored', 'cluster': {'server': 'https://192.168.10.50:6443',
                               'certificate-authority-data': encode(work / 'pki/ca.crt')}}],
                  'users': [{'name': NODE, 'user': {'client-certificate-data': encode(work / 'node.crt'),
                             'client-key-data': encode(work / 'node.key')}}],
                  'contexts': [{'name': 'restored', 'context': {'cluster': 'restored', 'user': NODE}}], 'current-context': 'restored'}
    (root / 'kubeconfig').write_text(json.dumps(kubeconfig))
    kubelet = {'apiVersion': 'kubelet.config.k8s.io/v1beta1', 'kind': 'KubeletConfiguration',
               'address': '127.0.0.1', 'readOnlyPort': 0, 'healthzBindAddress': '127.0.0.1',
               'authentication': {'anonymous': {'enabled': False}, 'webhook': {'enabled': True},
                                  'x509': {'clientCAFile': str(work / 'pki/ca.crt')}},
               'authorization': {'mode': 'Webhook'}, 'containerRuntimeEndpoint': 'unix://' + str(sock),
               'cgroupDriver': 'cgroupfs', 'cgroupRoot': '/etcd-recovery-pods', 'cgroupsPerQOS': True,
               'enforceNodeAllocatable': [], 'protectKernelDefaults': True, 'makeIPTablesUtilChains': False,
               'staticPodPath': '', 'podLogsDir': str(root / 'pod-logs'), 'maxPods': 1, 'oomScoreAdj': 0,
               'failSwapOn': True, 'rotateCertificates': False,
               'evictionHard': {'memory.available': '50Mi', 'nodefs.available': '5%', 'nodefs.inodesFree': '5%', 'imagefs.available': '5%'}}
    (root / 'kubelet.json').write_text(json.dumps(kubelet))
    export = root / 'pause.tar'
    run(['ctr', '-n', 'k8s.io', 'images', 'export', '--platform', 'linux/amd64', str(export), IMAGE])
    started = []
    group_created = False

    def service(unit, memory, command):
        started.append(unit)
        run(['systemd-run', '--unit=' + unit, '--collect', '--service-type=exec',
             '--property=MemoryMax=' + memory, '--property=CPUQuota=50%', '--property=TasksMax=256',
             '--property=Delegate=yes', '--property=TimeoutStopSec=15s', '--property=StandardOutput=append:' + str(root / (unit + '.log')),
             '--property=StandardError=append:' + str(root / (unit + '.log'))] + isolation_command(command))

    def cri(args, ok=True):
        return run(['crictl', '--runtime-endpoint=unix://' + str(sock), '--image-endpoint=unix://' + str(sock)] + args, ok)

    try:
        CGROUP.mkdir(); group_created = True
        (CGROUP / 'cgroup.subtree_control').write_text('+cpu +memory +pids')
        (CGROUP / 'memory.max').write_text(str(128 * 1024 * 1024))
        (CGROUP / 'pids.max').write_text('256')
        service(UNITS[0], '192M', ['containerd', '--config', str(root / 'containerd.toml')])
        for _ in range(30):
            if sock.exists() and cri(['info'], ok=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Independent recovery CRI did not start')
        run(['ctr', '--address', str(sock), '-n', 'k8s.io', 'images', 'import', '--platform', 'linux/amd64', str(export)])
        pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': POD, 'namespace': 'kube-system'},
               'spec': {'nodeName': NODE, 'hostNetwork': True, 'dnsPolicy': 'Default', 'automountServiceAccountToken': False,
                        'restartPolicy': 'Never', 'securityContext': {'seccompProfile': {'type': 'RuntimeDefault'}}, 'containers': [{'name': 'pause', 'image': IMAGE, 'imagePullPolicy': 'Never',
                        'resources': {'requests': {'cpu': '10m', 'memory': '8Mi'}, 'limits': {'cpu': '100m', 'memory': '32Mi'}},
                        'securityContext': {'runAsUser': 65534, 'runAsNonRoot': True, 'allowPrivilegeEscalation': False,
                                            'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}}}]}}
        request('/api/v1/namespaces/kube-system/pods', method='POST', data=pod)
        assigned = owned_pods(request)
        if len(assigned) != 1 or assigned[0]['metadata']['name'] != POD:
            raise RuntimeError('Recovery kubelet may receive only the inert fixture')
        service(UNITS[1], '256M', ['kubelet', '--config=' + str(root / 'kubelet.json'),
                                 '--root-dir=' + str(root / 'kubelet'), '--cert-dir=' + str(root / 'certs'),
                                 '--kubeconfig=' + str(root / 'kubeconfig'), '--hostname-override=' + NODE,
                                 '--node-ip=192.168.10.50'])
        for _ in range(90):
            assigned = owned_pods(request)
            if len(assigned) != 1 or assigned[0]['metadata']['name'] != POD:
                raise RuntimeError('Unexpected Pod assigned to the recovery kubelet')
            observed = assigned[0]
            node = json.loads(request('/api/v1/nodes/' + NODE).stdout)
            ready = any(c['type'] == 'Ready' and c['status'] == 'True' and c['reason'] == 'KubeletReady'
                        for c in node.get('status', {}).get('conditions', []))
            if ready and observed['status'].get('phase') == 'Running' and any(c.get('ready') for c in observed['status'].get('containerStatuses', [])):
                break
            if run(['systemctl', 'is-active', UNITS[1]], ok=False).returncode != 0:
                raise RuntimeError('Recovery kubelet exited; inspect its private log')
            time.sleep(2)
        else:
            raise RuntimeError('Real recovery kubelet and inert Pod did not become Ready')
        lease = json.loads(request('/apis/coordination.k8s.io/v1/namespaces/kube-node-lease/leases/' + NODE).stdout)
        first = lease['spec']['renewTime']
        for _ in range(20):
            time.sleep(1)
            lease = json.loads(request('/apis/coordination.k8s.io/v1/namespaces/kube-node-lease/leases/' + NODE).stdout)
            if lease['spec']['renewTime'] != first:
                break
        else:
            raise RuntimeError('Real kubelet did not renew its Node lease')
        containers = json.loads(cri(['ps', '-o', 'json']).stdout)['containers']
        if len(containers) != 1 or containers[0]['metadata']['name'] != 'pause':
            raise RuntimeError('Independent CRI has unexpected running workload containers')
        inspection = json.loads(cri(['inspect', containers[0]['id']]).stdout)['info']
        pid = inspection['pid']
        if not inspection['runtimeSpec']['linux']['cgroupsPath'].startswith('/etcd-recovery-pods/'):
            raise RuntimeError('Fixture escaped its dedicated pod cgroup')
        if Path('/proc/' + str(pid) + '/ns/net').stat().st_ino != Path('/run/netns/' + NETNS).stat().st_ino:
            raise RuntimeError('Fixture must share only the disconnected network namespace')
        return {'real_kubelet_ready': True, 'node_lease_renewed': True, 'inert_container_running_ready': True,
                'separate_cri_and_kubelet_roots': True, 'dedicated_pod_cgroup': True,
                'fixture_network_namespace_verified': True, 'production_cni_tested': False}
    finally:
        # Stop the producer first, then clean its separate CRI. Failures in API/CRI
        # cleanup must never prevent stopping services and killing our pod cgroup.
        cleanup_errors = []
        if UNITS[1] in started:
            run(['systemctl', 'stop', UNITS[1]], ok=False)
        try:
            request('/api/v1/namespaces/kube-system/pods/' + POD, method='DELETE',
                    data={'apiVersion': 'v1', 'kind': 'DeleteOptions', 'gracePeriodSeconds': 0}, ok=False)
        except Exception:
            cleanup_errors.append('API fixture deletion')
        try:
            if sock.exists():
                result = cri(['pods', '-o', 'json'], ok=False)
                if result.returncode == 0:
                    for sandbox in json.loads(result.stdout).get('items', []):
                        cri(['stopp', sandbox['id']], ok=False)
                        cri(['rmp', sandbox['id']], ok=False)
        except Exception:
            cleanup_errors.append('CRI sandbox cleanup')
        if group_created:
            (CGROUP / 'cgroup.kill').write_text('1')
        for unit in reversed(started):
            run(['systemctl', 'stop', unit], ok=False)
            if run(['systemctl', 'is-active', unit], ok=False).returncode == 0:
                cleanup_errors.append('active recovery service: ' + unit)
        if group_created:
            for _ in range(20):
                try:
                    for path in sorted(CGROUP.rglob('*'), key=lambda p: len(p.parts), reverse=True):
                        if path.is_dir():
                            path.rmdir()
                    CGROUP.rmdir()
                    break
                except OSError:
                    time.sleep(1)
            else:
                cleanup_errors.append('nonempty recovery pod cgroup')
        if not Path('/run/containerd/containerd.sock').exists() or Path('/run/containerd/containerd.sock').stat().st_ino != original_socket:
            cleanup_errors.append('original lab CRI socket changed')
        if cleanup_errors:
            raise RuntimeError('Inspect private runtime work before removing it: ' + ', '.join(cleanup_errors))
