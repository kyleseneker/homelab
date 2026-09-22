#!/usr/bin/env python3
"""Read an offsite Velero snapshot using independently recovered credentials."""
import argparse
import configparser
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def restore(credentials, password_file, namespace, snapshot, output, binary):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', namespace):
        raise ValueError('Invalid repository namespace')
    parts = snapshot.split('/')
    if not re.fullmatch(r'[a-f0-9]{32}', parts[0]) or any(x in ('', '.', '..') for x in parts[1:]):
        raise ValueError('Expected a snapshot ID and optional relative subdirectory')
    for path in (credentials, password_file):
        if path.stat().st_mode & 0o077:
            raise ValueError('Credential directory and password file must be private')
    metadata = json.loads((credentials / 'metadata.json').read_text())
    if metadata['credential_source'] != 'HCP Terraform homelab-aws':
        raise ValueError('Require the independent HCP credential export')
    ini = configparser.ConfigParser()
    ini.read(credentials / 'velero-offsite.credentials')
    password = password_file.read_text()
    if not password or '\0' in password:
        raise ValueError('Invalid repository password')
    output.mkdir(mode=0o700)  # Never merge recovery output into an existing directory.
    environment = {k: v for k, v in os.environ.items() if not k.startswith(('AWS_', 'KOPIA_'))}
    environment.update(AWS_ACCESS_KEY_ID=ini['default']['aws_access_key_id'],
                       AWS_SECRET_ACCESS_KEY=ini['default']['aws_secret_access_key'],
                       AWS_EC2_METADATA_DISABLED='true', KOPIA_PASSWORD=password,
                       KOPIA_CHECK_FOR_UPDATES='false')
    prefix = 'velero/kopia/' + namespace + '/'
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix='reader-', dir=output) as temporary:
        environment.update(KOPIA_CACHE_DIRECTORY=temporary + '/cache', KOPIA_LOG_DIR=temporary + '/logs')
        base = [str(binary.resolve()), '--config-file=' + temporary + '/repository.config',
                '--disable-file-logging', '--no-progress', '--no-use-keychain', '--no-persist-credentials']
        def run(arguments):
            result = subprocess.run(base + arguments, env=environment, capture_output=True, timeout=1800)
            if result.returncode:
                # Tool diagnostics may contain credentials, object paths or application data.
                raise RuntimeError('Read-only Kopia operation failed; output withheld')
            return result.stdout
        run(['repository', 'connect', 's3', '--readonly', '--bucket=' + metadata['bucket'],
             '--prefix=' + prefix, '--region=' + metadata['region'],
             '--override-username=default', '--override-hostname=default'])
        run(['snapshot', 'restore', snapshot, str(output / 'source'),
             '--skip-owners', '--skip-permissions', '--no-overwrite-files'])
    evidence = {'bucket': metadata['bucket'], 'prefix': prefix, 'snapshot': snapshot,
                'credential_source': metadata['credential_source'], 'readonly': True,
                'started_at': started, 'completed_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    (output / 'retrieval.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print('Offsite snapshot retrieved read-only into new private storage; temporary connection state removed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials-dir', required=True, type=Path)
    parser.add_argument('--password-file', required=True, type=Path)
    parser.add_argument('--namespace', required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--kopia', type=Path, default=Path('.lab/bin/kopia'))
    args = parser.parse_args()
    os.umask(0o077)
    restore(args.credentials_dir, args.password_file, args.namespace, args.snapshot, args.output, args.kopia)
