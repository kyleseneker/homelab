#!/usr/bin/env python3
"""Configure Kubernetes auth only in the existing isolated Vault restore lab."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
KUBE = ['kubectl', '--kubeconfig', str(ROOT / '.lab/kubeconfig')]


def run(arguments, data=None):
    result = subprocess.run(arguments, input=data, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError('Lab authentication operation failed; output withheld to protect credentials')
    return result.stdout


def main():
    context = run(KUBE + ['config', 'current-context']).decode().strip()
    if context != 'homelabrestore01':
        raise RuntimeError('Expected the homelabrestore01 context; refusing to configure Vault')
    token = os.environ.get('VAULT_TOKEN')
    if not token:
        token = (Path.home() / '.vault-token').read_text().strip()
    if not token or '\n' in token:
        raise RuntimeError('Provide a valid administrative Vault token privately')

    def vault(command, payload=''):
        script = 'read -r VAULT_TOKEN; export VAULT_TOKEN; ' + command
        return run(KUBE + ['-n', 'restore-vault', 'exec', '-i', 'deployment/restore-vault',
                           '--', 'sh', '-ec', script], (token + '\n' + payload).encode())

    status = json.loads(vault('vault status -format=json'))
    if not status['initialized'] or status['sealed']:
        raise RuntimeError('Restore and auto-unseal Vault before configuring authentication')
    # Empty reviewer/CA fields select the pod's rotating token and lab CA files.
    vault('vault write auth/kubernetes/config -', json.dumps({
        'kubernetes_host': 'https://kubernetes.default.svc:443',
        'kubernetes_ca_cert': '', 'token_reviewer_jwt': '',
        'disable_local_ca_jwt': False, 'disable_iss_validation': True,
    }))
    vault('vault policy write restore-grafana-read -',
          'path "homelab/data/infrastructure/grafana" { capabilities = ["read"] }\n')
    vault('vault write auth/kubernetes/role/restore-external-secrets -', json.dumps({
        'bound_service_account_names': ['restore-external-secrets'],
        'bound_service_account_namespaces': ['restore-vault'],
        'audience': 'vault', 'token_policies': ['restore-grafana-read'],
        'token_ttl': '10m', 'token_max_ttl': '10m',
    }))
    print('Lab Kubernetes auth configured; ESO role can read only the restored Grafana credential path.')


if __name__ == '__main__':
    main()
