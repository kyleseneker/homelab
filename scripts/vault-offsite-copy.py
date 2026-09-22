#!/usr/bin/env python3
"""Upload a verified Vault archive without overwriting, then verify an S3 download."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile


def copy(archive, credentials, expected_sha256, download):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError('Archive SHA-256 does not match the verified recovery copy')
    if download.exists() or not download.parent.is_dir():
        raise ValueError('Download must be a new file in an existing private directory')
    metadata = json.loads((credentials / 'metadata.json').read_text())
    key = 'vault-file-backups/' + archive.name
    env = {k: v for k, v in os.environ.items() if not k.startswith('AWS_')}
    env.update(AWS_SHARED_CREDENTIALS_FILE=str((credentials / 'velero-offsite.credentials').resolve()),
               AWS_CONFIG_FILE='/dev/null', AWS_DEFAULT_REGION=metadata['region'],
               AWS_EC2_METADATA_DISABLED='true', AWS_PAGER='')

    def aws(arguments):
        result = subprocess.run(['aws', 's3api'] + arguments, env=env,
                                capture_output=True, timeout=120)
        if result.returncode:
            code = re.search(r'An error occurred \(([A-Za-z0-9]+)\)', result.stderr.decode())
            label = code.group(1) if code else 'details withheld'
            raise RuntimeError('S3 operation failed (' + label + '); existing objects are never overwritten.')
        return json.loads(result.stdout or b'{}')

    uploaded = aws(['put-object', '--bucket', metadata['bucket'], '--key', key,
                    '--body', str(archive), '--if-none-match', '*',
                    '--server-side-encryption', 'AES256', '--metadata', 'sha256=' + expected_sha256])
    # GetObject uses existing IAM permissions; verify the returned version before publishing.
    version = uploaded.get('VersionId')
    with tempfile.NamedTemporaryFile(dir=download.parent, prefix='.vault-offsite-') as staged:
        received = aws(['get-object', '--bucket', metadata['bucket'], '--key', key]
                       + [staged.name])
        if version and received.get('VersionId') != version:
            raise RuntimeError('S3 current version changed after upload; download not published')
        actual = hashlib.sha256(Path(staged.name).read_bytes()).hexdigest()
        if actual != expected_sha256 or received.get('Metadata', {}).get('sha256') != expected_sha256:
            raise RuntimeError('Downloaded archive failed SHA-256 verification')
        os.link(staged.name, download)
    return {'bucket': metadata['bucket'], 'key': key, 'sha256': expected_sha256,
            'bytes': download.stat().st_size, 'version_id': version}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--credentials-dir', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--download-output', type=Path, required=True)
    args = parser.parse_args()
    result = copy(args.archive, args.credentials_dir, args.expected_sha256, args.download_output)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
