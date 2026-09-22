#!/usr/bin/env python3
"""Export AWS recovery credentials from HCP Terraform without Kubernetes or Vault."""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def export(outputs, destination):
    def value(name):
        result = outputs[name]['value']
        if not isinstance(result, str) or not result or '\n' in result or '\r' in result:
            raise ValueError('Invalid recovery output: ' + name)
        return result

    arn = value('kms_key_arn').split(':')
    if len(arn) != 6 or arn[2] != 'kms' or not arn[3]:
        raise ValueError('Expected a KMS key ARN')
    region = arn[3]
    kms = {'AWS_ACCESS_KEY_ID': value('aws_access_key_id'),
           'AWS_SECRET_ACCESS_KEY': value('aws_secret_access_key'),
           'AWS_REGION': region, 'VAULT_AWSKMS_SEAL_KEY_ID': value('kms_key_id')}
    access = value('velero_offsite_access_key_id')
    secret = value('velero_offsite_secret_access_key')
    metadata = {'region': region, 'bucket': value('velero_offsite_bucket_name'),
                'credential_source': 'HCP Terraform homelab-aws'}
    contents = {
        'vault-kms.env': ''.join(k + '=' + v + '\n' for k, v in kms.items()),
        'velero-offsite.credentials': '[default]\naws_access_key_id = ' + access + '\naws_secret_access_key = ' + secret + '\n',
        'metadata.json': json.dumps(metadata, indent=2) + '\n',
    }
    # Validate everything before creating files; never overwrite an existing export.
    destination.mkdir(mode=0o700)
    for name, content in contents.items():
        descriptor = os.open(destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True, help='New private directory outside Git tracking')
    args = parser.parse_args()
    result = subprocess.run(['terraform', '-chdir=' + str(ROOT / 'terraform/aws'), 'output', '-json'],
                            capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError('Cannot read HCP outputs; run make aws-init and check Terraform authentication. Output withheld.')
    export(json.loads(result.stdout), args.output_dir)
    print('Recovery credentials exported privately from HCP Terraform; no Kubernetes or Vault access used.')


if __name__ == '__main__':
    main()
