import json
import tempfile
import threading
import unittest
import struct
import urllib.request
import urllib.error
from pathlib import Path
from server import make_server, Store

STL = b'solid test\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid test\n'
PLY = b'ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n1 0 0\n0 1 0\n'


class PortalTest(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).parent / 'data'
        base.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.server = make_server(self.tmp.name, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = self.server.origin

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def req(self, path, data=None, cookie='', headers=None):
        hdr = {'X-SCAN3D-Client': 'portal', 'Cookie': cookie}
        hdr.update(headers or {})
        raw = data if isinstance(data, bytes) else json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(self.base + '/api' + path, data=raw, headers=hdr)
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            response = exc
        raw = response.read()
        try:
            body = json.loads(raw)
        except ValueError:
            body = raw
        return response.code, body, response.headers.get('Set-Cookie', '').split(';')[0]

    def account(self, name, merchant=False):
        data = {'username': name, 'password': 'correct-horse-123', 'name': name}
        if merchant:
            data['code'] = self.server.store.setup_code
        self.assertEqual(self.req('/setup' if merchant else '/register', data)[0], 201)
        status, _, cookie = self.req('/login', data)
        self.assertEqual(status, 200)
        return cookie

    def test_delivery_isolation_and_persistence(self):
        merchant = self.account('merchant', True)
        alice = self.account('alice')
        bob = self.account('bob')
        code = self.req('/claim-code', {}, alice)[1]['code']
        data = {'customer': 'alice', 'code': code, 'title': '纪念小鸭', 'note': '原始模型'}
        status, item, _ = self.req('/items', data, merchant)
        self.assertEqual(status, 201)
        item_id = item['id']
        self.assertEqual(self.req('/items', data, merchant)[0], 400)  # one-time code
        self.assertEqual(self.req('/items', data, bob)[0], 400)  # No valid recipient consent.
        self.assertEqual(self.req('/items', cookie=alice)[1]['items'], [])
        self.assertEqual(self.req(f'/items/{item_id}/deliver', {}, merchant)[0], 400)
        file_ids = []
        for name, raw in [('test.stl', STL), ('test.ply', PLY)]:
            status, file, _ = self.req(f'/items/{item_id}/files', raw, merchant, {'X-File-Name': name})
            self.assertEqual(status, 201)
            file_ids.append(file['id'])
        self.assertEqual(self.req('/files/' + file_ids[0], cookie=alice)[0], 404)
        self.assertEqual(self.req(f'/items/{item_id}/deliver', {}, merchant)[0], 200)
        self.assertEqual(len(self.req('/items', cookie=alice)[1]['items']), 1)
        self.assertEqual(self.req('/items', cookie=bob)[1]['items'], [])
        self.assertEqual(self.req('/files/' + file_ids[0], cookie=bob)[0], 404)
        self.assertEqual(self.req('/files/' + file_ids[0], cookie=alice)[1], STL)
        self.assertEqual(self.req(f'/items/{item_id}/files', STL, merchant, {'X-File-Name': 'new.stl'})[0], 409)
        self.assertEqual(self.req(f'/items/{item_id}/story', {'story': '毕业礼物'}, bob)[0], 404)
        self.assertEqual(self.req(f'/items/{item_id}/story', {'story': '毕业礼物'}, alice)[0], 200)
        self.assertEqual(self.req('/items', cookie=merchant)[1]['items'][0]['story'], '')
        self.assertEqual(self.req('/logout', {}, alice)[0], 200)
        self.assertEqual(self.req('/me', cookie=alice)[0], 401)
        alice = self.req('/login', {'username': 'alice', 'password': 'correct-horse-123'})[2]
        self.assertEqual(self.req('/items', cookie=alice)[1]['items'][0]['story'], '毕业礼物')
        reopened = Store(self.tmp.name)
        with reopened.db() as db:
            self.assertEqual(db.execute('SELECT story FROM items').fetchone()[0], '毕业礼物')

    def test_security_and_invalid_upload(self):
        merchant = self.account('merchant', True)
        alice = self.account('alice')
        self.assertEqual(self.req('/setup', {'code': self.server.store.setup_code, 'username': 'another', 'password': 'correct-horse-123', 'name': 'Another'})[0], 409)
        self.assertEqual(self.req('/claim-code', {}, alice, {'Origin': 'https://evil.invalid'})[0], 403)
        self.assertEqual(self.req('/claim-code', {}, alice, {'X-SCAN3D-Client': ''})[0], 403)
        code = self.req('/claim-code', {}, alice)[1]['code']
        item = self.req('/items', {'customer': 'alice', 'code': code, 'title': 'test'}, merchant)[1]['id']
        for name, raw in [('test.exe', b'junk'), ('test.stl', b'junk'), ('../test.stl', STL)]:
            self.assertEqual(self.req(f'/items/{item}/files', raw, merchant, {'X-File-Name': name})[0], 400)
        for _ in range(8):
            self.assertEqual(self.req('/login', {'username': 'alice', 'password': 'incorrect'})[0], 401)
        self.assertEqual(self.req('/login', {'username': 'alice', 'password': 'incorrect'})[0], 429)

    def test_model_headers(self):
        from server import validate_file, Problem
        pcd = b'VERSION .7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 1\nHEIGHT 1\nPOINTS 1\nDATA ascii\n0 0 0\n'
        validate_file('pcd', pcd)
        validate_file('stl', b' ' * 80 + struct.pack('<I', 1) + struct.pack('<12fH', *([0.] * 12), 0))
        for ext, raw in [('pcd', b'invalid'), ('ply', b'ply\nend_header'), ('stl', b' '*84)]:
            with self.assertRaises(Problem):
                validate_file(ext, raw)

    def test_public_origin_and_secure_sessions(self):
        self.server.public_origin = 'https://portal.example.test'
        self.server.allowed_hosts.append('portal.example.test')
        public = {'Host': 'portal.example.test', 'Origin': self.server.public_origin, 'CF-Connecting-IP': '192.0.2.10'}
        self.assertFalse(self.req('/status', headers=public)[1]['setup'])
        data = {'username': 'merchant', 'password': 'correct-horse-123', 'name': 'Merchant', 'code': self.server.store.setup_code}
        self.assertEqual(self.req('/setup', data, headers=public)[0], 403)
        # Even a rewritten local Host must not make proxy requests local administrators.
        self.assertEqual(self.req('/setup', data, headers={'CF-Connecting-IP': '192.0.2.10'})[0], 403)
        self.assertEqual(self.req('/setup', data)[0], 201)
        self.account('customer')
        login = json.dumps({'username': 'customer', 'password': 'correct-horse-123'}).encode()
        req = urllib.request.Request(self.base + '/api/login', data=login, headers={**public, 'X-SCAN3D-Client': 'portal'})
        with urllib.request.urlopen(req) as response:
            self.assertIn('Secure', response.headers['Set-Cookie'])
            self.assertIn('HttpOnly', response.headers['Set-Cookie'])
            self.assertIn('SameSite=Strict', response.headers['Set-Cookie'])
            self.assertIn("object-src 'none'", response.headers['Content-Security-Policy'])
            self.assertIn('max-age=', response.headers['Strict-Transport-Security'])
        self.assertEqual(self.req('/register', data, headers={**public,'Origin':'https://other.invalid'})[0], 403)
        self.assertEqual(self.req('/status', headers={'Host':'evil.invalid'})[0], 403)

    def test_unified_accounts_self_upload_and_delivery(self):
        alice = self.account('alice')
        bob = self.account('bob')
        other = self.account('other')
        # Self uploads must use the authenticated owner, ignoring an injected name.
        code = self.req('/claim-code', {}, alice)[1]['code']
        status, own, _ = self.req('/items', {'recipient':'self','customer':'bob','title':'My collection'}, alice)
        self.assertEqual(status, 201)
        own_id = own['id']
        self.assertEqual(self.req('/items',cookie=bob)[1]['items'], [])
        self.assertEqual(self.req(f'/items/{own_id}/story',{'story':'too early'},alice)[0],403)
        self.assertEqual(self.req(f'/items/{own_id}/files',STL,alice,{'X-File-Name':'self.stl'})[0],201)
        self.assertEqual(self.req(f'/items/{own_id}/deliver',{},alice)[0],200)
        self.assertEqual(self.req(f'/items/{own_id}/story',{'story':'mine'},alice)[0],200)
        own_record=self.req('/items',cookie=alice)[1]['items'][0]
        self.assertEqual(own_record['owner'],own_record['merchant'])
        self.assertEqual(own_record['story'],'mine')
        # An ordinary account can upload for another, with a still-valid claim.
        data={'customer':'alice','code':code,'title':'From Bob'}
        status,sent,_=self.req('/items',data,bob)
        self.assertEqual(status,201)
        sent_id=sent['id']
        self.assertEqual(self.req('/items',data,other)[0],400)
        self.assertEqual(len(self.req('/items',cookie=alice)[1]['items']),1)
        self.assertEqual(self.req(f'/items/{sent_id}/files',STL,other,{'X-File-Name':'other.stl'})[0],404)
        status,file,_=self.req(f'/items/{sent_id}/files',STL,bob,{'X-File-Name':'gift.stl'})
        self.assertEqual(status,201)
        self.assertEqual(self.req(f'/items/{sent_id}/deliver',{},bob)[0],200)
        self.assertEqual(self.req('/files/'+file['id'],cookie=alice)[1],STL)
        self.assertEqual(self.req(f'/items/{sent_id}/story',{'story':'private memory'},alice)[0],200)
        self.assertEqual(self.req(f'/items/{sent_id}/story',{'story':'overwrite'},bob)[0],403)
        self.assertEqual(self.req('/items',cookie=bob)[1]['items'][0]['story'],'')
        self.assertEqual(self.req(f'/items/{sent_id}/files',STL,alice,{'X-File-Name':'overwrite.stl'})[0],403)
        self.assertEqual(self.req('/files/'+file['id'],cookie=other)[0],404)
        # A legacy merchant account also receives collections under the same rules.
        legacy=self.account('legacy',True)
        legacy_code=self.req('/claim-code',{},legacy)[1]['code']
        self.assertEqual(self.req('/items',{'customer':'legacy','code':legacy_code,'title':'Legacy recipient'},alice)[0],201)

    def test_claim_expiry_rotation_and_draft_permissions(self):
        uploader = self.account('uploader')
        recipient = self.account('recipient')
        other = self.account('other')
        old_code = self.req('/claim-code', {}, recipient)[1]['code']
        new_code = self.req('/claim-code', {}, recipient)[1]['code']
        data = {'customer': 'recipient', 'title': 'Private draft'}
        self.assertEqual(self.req('/items', {**data, 'code': old_code}, uploader)[0], 400)

        # Expiry is changed only in this test's isolated temporary database.
        with self.server.store.db() as db:
            db.execute('UPDATE users SET claim_expiry=0 WHERE username=?', ('recipient',))
        self.assertEqual(self.req('/items', {**data, 'code': new_code}, uploader)[0], 400)
        self.assertEqual(self.req('/items', cookie=uploader)[1]['items'], [])

        valid_code = self.req('/claim-code', {}, recipient)[1]['code']
        status, draft, _ = self.req('/items', {**data, 'code': valid_code}, uploader)
        self.assertEqual(status, 201)
        item_id = draft['id']
        status, original, _ = self.req(f'/items/{item_id}/files', STL, uploader,
                                        {'X-File-Name': 'original.stl'})
        self.assertEqual(status, 201)
        for viewer in (recipient, other):
            self.assertEqual(self.req('/items', cookie=viewer)[1]['items'], [])
            self.assertEqual(self.req('/files/' + original['id'], cookie=viewer)[0], 404)
            self.assertEqual(self.req(f'/items/{item_id}/files', STL, viewer,
                                      {'X-File-Name': 'unauthorized.stl'})[0], 404)
            self.assertEqual(self.req(f'/items/{item_id}/deliver', {}, viewer)[0], 404)

        draft_record = self.req('/items', cookie=uploader)[1]['items'][0]
        self.assertEqual(draft_record['status'], 'draft')
        self.assertEqual(len(draft_record['files']), 1)
        self.assertEqual(self.req(f'/items/{item_id}/files', PLY, uploader,
                                  {'X-File-Name': 'original.ply'})[0], 201)
        self.assertEqual(self.req(f'/items/{item_id}/deliver', {}, uploader)[0], 200)
        self.assertEqual(len(self.req('/items', cookie=recipient)[1]['items']), 1)
        self.assertEqual(self.req('/files/' + original['id'], cookie=recipient)[1], STL)
        self.assertEqual(self.req('/files/' + original['id'], cookie=other)[0], 404)

    def test_public_login_limits_are_per_visitor(self):
        self.account('customer')
        self.server.public_origin = 'https://portal.example.test'
        self.server.allowed_hosts.append('portal.example.test')
        public = {'Host':'portal.example.test', 'Origin':self.server.public_origin, 'CF-Connecting-IP':'192.0.2.10'}
        for _ in range(8):
            self.assertEqual(self.req('/login', {'username':'customer','password':'incorrect'}, headers=public)[0], 401)
        correct = {'username':'customer','password':'correct-horse-123'}
        self.assertEqual(self.req('/login', correct, headers=public)[0], 429)
        other = {**public, 'CF-Connecting-IP':'192.0.2.11'}
        self.assertEqual(self.req('/login', correct, headers=other)[0], 200)

    def test_storage_quota(self):
        import server
        merchant=self.account('merchant', True)
        alice=self.account('alice')
        code=self.req('/claim-code', {}, alice)[1]['code']
        item=self.req('/items', {'customer':'alice','code':code,'title':'Quota'},merchant)[1]['id']
        old=server.MAX_CUSTOMER_BYTES
        try:
            server.MAX_CUSTOMER_BYTES=1
            self.assertEqual(self.req(f'/items/{item}/files',STL,merchant,{'X-File-Name':'sample.stl'})[0],413)
            self.assertEqual(self.req('/items',cookie=merchant)[1]['items'][0]['files'],[])
        finally:
            server.MAX_CUSTOMER_BYTES=old


if __name__ == '__main__':
    unittest.main(verbosity=2)
