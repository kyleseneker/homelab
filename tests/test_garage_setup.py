import http.server
import importlib.util
import json
from pathlib import Path
import threading
import unittest
from urllib.parse import parse_qs, urlparse

PATH = Path(__file__).parents[1] / 'k8s/clusters/homelabk8s01/infrastructure/garage/scripts/setup.py'
spec = importlib.util.spec_from_file_location('garage_setup', PATH)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)

TOKEN = 'admin-token'
KEY_ID = 'GK' + 'a1' * 12
SECRET = 'b2' * 32


class FakeGarage:
    def __init__(self, nodes=1):
        self.version = 0
        self.role = None
        self.staged = None
        self.buckets = {}
        self.keys = {}
        self.grants = []
        self.calls = []
        self.nodes = nodes

    def handle(self, method, path, query, body):
        self.calls.append((method, path))
        if method == 'GET' and path == '/v2/GetClusterStatus':
            nodes = [{'id': f'node{i}', 'isUp': True, 'draining': False, 'role': self.role}
                     for i in range(self.nodes)]
            return 200, {'layoutVersion': self.version, 'nodes': nodes}
        if method == 'POST' and path == '/v2/UpdateClusterLayout':
            self.staged = body['roles']
            return 200, {}
        if method == 'GET' and path == '/v2/GetClusterLayout':
            return 200, {'version': self.version}
        if method == 'POST' and path == '/v2/ApplyClusterLayout':
            if body['version'] != self.version + 1 or not self.staged:
                return 400, {'message': 'bad layout version'}
            self.version, self.role, self.staged = body['version'], self.staged[0], None
            return 200, {}
        if method == 'GET' and path == '/v2/GetBucketInfo':
            alias = query['globalAlias'][0]
            return (200, {'id': self.buckets[alias]}) if alias in self.buckets else (404, {})
        if method == 'POST' and path == '/v2/CreateBucket':
            self.buckets[body['globalAlias']] = 'bucket-' + body['globalAlias']
            return 200, {'id': self.buckets[body['globalAlias']]}
        if method == 'GET' and path == '/v2/GetKeyInfo':
            return (200, {'accessKeyId': query['id'][0]}) if query['id'][0] in self.keys else (404, {})
        if method == 'POST' and path == '/v2/ImportKey':
            self.keys[body['accessKeyId']] = body['secretAccessKey']
            return 200, {}
        if method == 'POST' and path == '/v2/AllowBucketKey':
            self.grants.append(body)
            return 200, {}
        return 404, {}


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.garage = FakeGarage()
        garage = self.garage

        class Handler(http.server.BaseHTTPRequestHandler):
            def respond(self, method):
                if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
                    code, payload = 401, {'message': 'unauthorized'}
                else:
                    url = urlparse(self.path)
                    length = int(self.headers.get('Content-Length') or 0)
                    body = json.loads(self.rfile.read(length)) if length else None
                    code, payload = garage.handle(method, url.path, parse_qs(url.query), body)
                data = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self.respond('GET')

            def do_POST(self):
                self.respond('POST')

            def log_message(self, *args):
                pass

        self.server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        setup.ADMIN = f'http://127.0.0.1:{self.server.server_port}'

    def configure(self, token=TOKEN):
        status = setup.wait_for_admin(token, attempts=1, delay=0)
        layout = setup.ensure_layout(token, status)
        bucket_id, created = setup.ensure_bucket(token)
        imported = setup.ensure_key(token, KEY_ID, SECRET)
        setup.allow(token, bucket_id, KEY_ID)
        return layout, created, imported

    def test_first_run_configures_node_bucket_and_key(self):
        self.assertEqual(self.configure(), (True, True, True))
        self.assertEqual(self.garage.version, 1)
        self.assertEqual(self.garage.role['zone'], setup.ZONE)
        self.assertEqual(self.garage.keys, {KEY_ID: SECRET})
        self.assertEqual(self.garage.grants[-1]['permissions'],
                         {'read': True, 'write': True, 'owner': False})

    def test_second_run_changes_nothing(self):
        self.configure()
        self.garage.calls.clear()
        self.assertEqual(self.configure(), (False, False, False))
        mutations = [c for c in self.garage.calls if c[0] == 'POST' and c[1] != '/v2/AllowBucketKey']
        self.assertEqual(mutations, [])
        self.assertEqual(self.garage.version, 1)

    def test_more_than_one_node_is_rejected(self):
        self.garage.nodes = 2
        status = setup.wait_for_admin(TOKEN, attempts=1, delay=0)
        with self.assertRaises(RuntimeError):
            setup.ensure_layout(TOKEN, status)

    def test_wrong_token_fails_immediately(self):
        with self.assertRaises(PermissionError):
            setup.wait_for_admin('wrong', attempts=1, delay=0)


if __name__ == '__main__':
    unittest.main()
