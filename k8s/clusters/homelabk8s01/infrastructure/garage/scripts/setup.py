#!/usr/bin/env python3
"""Configure single-node Garage for Velero; every step is idempotent (ADR-025)."""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ADMIN = os.environ.get('GARAGE_ADMIN_URL', 'http://garage.backups.svc.cluster.local:3903')
S3 = os.environ.get('GARAGE_S3_URL', 'http://garage.backups.svc.cluster.local:3900')
BUCKET = os.environ.get('GARAGE_BUCKET', 'velero')
ZONE = os.environ.get('GARAGE_ZONE', 'homelab')
CAPACITY = int(os.environ.get('GARAGE_CAPACITY_BYTES', str(50 * 10**9)))


class NotFound(Exception):
    pass


def call(token, method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(ADMIN + path, data=data, method=method,
                                     headers={'Authorization': 'Bearer ' + token,
                                              'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read().decode()
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise PermissionError(f'{method} {path}: admin token rejected (HTTP {error.code})') from error
        if error.code in (400, 404) and method == 'GET':
            raise NotFound(path) from error
        raise RuntimeError(f'{method} {path}: HTTP {error.code} {error.read().decode()[:300]}') from error
    return json.loads(text) if text else {}


def wait_for_admin(token, attempts=60, delay=5):
    for _ in range(attempts):
        try:
            return call(token, 'GET', '/v2/GetClusterStatus')
        except (urllib.error.URLError, ConnectionError, RuntimeError):
            time.sleep(delay)
    raise RuntimeError('Garage admin API did not become reachable')


def ensure_layout(token, status):
    nodes = status['nodes']
    if len(nodes) != 1:
        raise RuntimeError(f'expected one Garage node, found {len(nodes)}')
    node = nodes[0]
    if node.get('role'):
        return False
    call(token, 'POST', '/v2/UpdateClusterLayout',
         {'roles': [{'id': node['id'], 'zone': ZONE, 'capacity': CAPACITY, 'tags': []}]})
    layout = call(token, 'GET', '/v2/GetClusterLayout')
    call(token, 'POST', '/v2/ApplyClusterLayout', {'version': layout['version'] + 1})
    return True


def ensure_bucket(token):
    try:
        return call(token, 'GET', '/v2/GetBucketInfo?globalAlias=' + BUCKET)['id'], False
    except NotFound:
        return call(token, 'POST', '/v2/CreateBucket', {'globalAlias': BUCKET})['id'], True


def ensure_key(token, key_id, secret):
    try:
        call(token, 'GET', '/v2/GetKeyInfo?id=' + key_id)
        return False
    except NotFound:
        call(token, 'POST', '/v2/ImportKey',
             {'accessKeyId': key_id, 'secretAccessKey': secret, 'name': 'velero'})
        return True


def allow(token, bucket_id, key_id):
    call(token, 'POST', '/v2/AllowBucketKey',
         {'bucketId': bucket_id, 'accessKeyId': key_id,
          'permissions': {'read': True, 'write': True, 'owner': False}})


def verify_s3(key_id, secret):
    # The AWS CLI sends CRC32 request checksums, like Velero's AWS plugin.
    env = dict(os.environ, AWS_ACCESS_KEY_ID=key_id, AWS_SECRET_ACCESS_KEY=secret,
               AWS_DEFAULT_REGION='garage', HOME='/tmp')
    probe = 'garage-setup-probe'
    base = ['aws', '--endpoint-url', S3, 's3api']
    with open('/tmp/probe', 'w') as handle:
        handle.write('ok\n')
    for args in (['put-object', '--bucket', BUCKET, '--key', probe, '--body', '/tmp/probe'],
                 ['get-object', '--bucket', BUCKET, '--key', probe, '/tmp/probe.out'],
                 ['delete-object', '--bucket', BUCKET, '--key', probe]):
        subprocess.run(base + args, env=env, check=True, stdout=subprocess.DEVNULL)


def main():
    token = os.environ['GARAGE_ADMIN_TOKEN']
    key_id = os.environ['GARAGE_ACCESS_KEY_ID']
    secret = os.environ['GARAGE_SECRET_ACCESS_KEY']
    status = wait_for_admin(token)
    print('layout applied' if ensure_layout(token, status) else 'layout already assigned')
    bucket_id, created = ensure_bucket(token)
    print(('created' if created else 'found') + f' bucket {BUCKET}')
    print('imported key' if ensure_key(token, key_id, secret) else 'key already present')
    allow(token, bucket_id, key_id)
    verify_s3(key_id, secret)
    print('S3 put/get/delete verified')
    return 0


if __name__ == '__main__':
    sys.exit(main())
