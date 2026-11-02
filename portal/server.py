"""SCAN3D account and delivery portal. Python 3.11+, standard library only."""
import argparse
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parent
MAX_FILE = 64 * 1024 * 1024
MAX_CUSTOMER_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024


class Problem(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


class Store:
    def __init__(self, directory):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'files').mkdir(exist_ok=True)
        self.dbpath = self.root / 'portal.sqlite3'
        self.setup_code = secrets.token_urlsafe(20)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE,
              name TEXT, password TEXT, role TEXT, claim TEXT UNIQUE, claim_expiry REAL);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, uid TEXT, expiry REAL);
            CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY, merchant TEXT, owner TEXT,
              title TEXT, note TEXT, story TEXT DEFAULT '', status TEXT DEFAULT 'draft', created REAL, delivered REAL);
            CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY, item TEXT, name TEXT, ext TEXT, size INTEGER, sha TEXT);
            CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY, count INTEGER, until REAL);
            CREATE TABLE IF NOT EXISTS rate_limits(key TEXT PRIMARY KEY, count INTEGER, until REAL);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.dbpath, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def merchant_exists(self):
        with self.db() as db:
            return bool(db.execute("SELECT 1 FROM users WHERE role='merchant'").fetchone())

    def add_user(self, data, role='customer'):
        username = str(data.get('username', '')).strip().lower()
        password = str(data.get('password', ''))
        name = str(data.get('name', '')).strip()
        if not re.fullmatch(r'[a-z0-9_]{3,32}', username):
            raise Problem('账号请使用 3–32 位字母、数字或下划线')
        if not 10 <= len(password) <= 128:
            raise Problem('密码长度应为 10–128 位')
        if not 1 <= len(name) <= 40:
            raise Problem('请输入不超过 40 字的姓名或昵称')
        salt = secrets.token_hex(16)
        hashed = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if role == 'merchant' and db.execute("SELECT 1 FROM users WHERE role='merchant'").fetchone():
                raise Problem('商家账户已建立', 409)
            if db.execute('SELECT count(*) FROM users').fetchone()[0] >= 500:
                raise Problem('试用账号容量已满，请联系商家', 429)
            try:
                db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)',
                           (secrets.token_hex(16), username, name, salt + ':' + hashed, role, None, 0))
            except sqlite3.IntegrityError:
                raise Problem('账号已被使用', 409)


def validate_file(ext, content):
    if ext == 'stl':
        import struct
        binary = len(content) >= 84 and 0 < struct.unpack_from('<I', content, 80)[0] <= 2000000 and 84 + struct.unpack_from('<I', content, 80)[0] * 50 == len(content)
        ascii_stl = content.lstrip().startswith(b'solid') and b'facet normal' in content and b'endsolid' in content
        if not (binary or ascii_stl):
            raise Problem('STL 文件结构不正确')
    elif ext == 'ply':
        head = content[:65536]
        if not head.startswith(b'ply') or b'end_header' not in head or not re.search(rb'element vertex [1-9][0-9]*', head):
            raise Problem('PLY 缺少有效点云头部')
        count = int(re.search(rb'element vertex ([1-9][0-9]*)', head)[1])
        if count > 6000000:
            raise Problem('点云超过 600 万点上限')
        header = head.split(b'end_header')[0]
        if not all(re.search(rb'property\s+\w+\s+' + axis + rb'\s', header + b'\n') for axis in (b'x', b'y', b'z')):
            raise Problem('PLY 必须包含 XYZ 坐标')
    elif ext == 'pcd':
        head = content[:65536]
        if not re.search(rb'FIELDS\s+[^\r\n]*\bx\b[^\r\n]*\by\b[^\r\n]*\bz\b', head) or not re.search(rb'DATA (ascii|binary|binary_compressed)', head):
            raise Problem('PCD 缺少 XYZ 坐标或 DATA 头部')
        points = re.search(rb'POINTS\s+([0-9]+)', head)
        if not points or not 0 < int(points[1]) <= 6000000:
            raise Problem('PCD 点数应在 1–600 万之间')
        compressed = re.search(rb'DATA binary_compressed\r?\n', head)
        if compressed:
            import struct
            offset = compressed.end()
            if len(content) < offset + 8:
                raise Problem('PCD 压缩数据不完整')
            packed, unpacked = struct.unpack_from('<II', content, offset)
            if packed != len(content) - offset - 8 or unpacked > 256 * 1024 * 1024:
                raise Problem('PCD 压缩长度异常或解压超过 256 MB')
    else:
        raise Problem('仅支持 STL、PLY、PCD 文件')


class Handler(BaseHTTPRequestHandler):
    server_version = 'SCAN3D'

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def public_request(self):
        return self.headers.get('Host') != self.server.local_host or bool(self.headers.get('CF-Connecting-IP'))

    def client_address_key(self):
        # This server binds loopback only; public traffic comes from the local tunnel.
        address = self.headers.get('CF-Connecting-IP', self.client_address[0]) if self.public_request() else self.client_address[0]
        return hashlib.sha256(address.encode()).hexdigest()

    def limit(self, kind, maximum, seconds):
        key = kind + ':' + self.client_address_key()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            now = time.time()
            row = db.execute('SELECT count,until FROM rate_limits WHERE key=?', (key,)).fetchone()
            count, until = (row['count'] + 1, row['until']) if row and row['until'] > now else (1, now + seconds)
            if count > maximum:
                raise Problem('操作频繁，请稍后重试', 429)
            db.execute('INSERT OR REPLACE INTO rate_limits VALUES(?,?,?)', (key, count, until))
            db.execute('DELETE FROM rate_limits WHERE until<?', (now - 86400,))

    def log_message(self, fmt, *args):
        # Avoid recording passwords, claim codes or query strings.
        pass

    @property
    def store(self):
        return self.server.store

    def reply(self, data, status=200, cookie=None):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(raw)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        self.send_header('Content-Security-Policy', self.server.csp)
        if self.public_request():
            self.send_header('Strict-Transport-Security', 'max-age=86400')
        super().end_headers()

    def body(self, limit=32768):
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise Problem('请求长度错误')
        if not 0 < size <= limit:
            raise Problem('文件过大（单文件上限 64 MB）或请求为空', 413)
        self.connection.settimeout(60)
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise Problem('上传未完成')
        return raw

    def json_body(self):
        try:
            value = json.loads(self.body())
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeDecodeError):
            raise Problem('请求内容错误')

    def user(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            token = cookie['scan3d_session'].value
        except Exception:
            raise Problem('请先登录', 401)
        with self.store.db() as db:
            row = db.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.uid WHERE s.token=? AND s.expiry>?',
                             (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        if not row:
            raise Problem('登录已过期，请重新登录', 401)
        return dict(row)

    def allowed_item(self, item_id, user, edit=False):
        with self.store.db() as db:
            row = db.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone()
        if not row:
            raise Problem('藏品不存在', 404)
        row = dict(row)
        allowed = row['merchant'] == user['id'] or (
            row['owner'] == user['id'] and row['status'] == 'delivered')
        if not allowed:
            raise Problem('藏品不存在', 404)
        return row

    def do_GET(self):
        self.handle_request('GET')

    def do_POST(self):
        self.handle_request('POST')

    def do_PUT(self):
        self.handle_request('PUT')

    def handle_request(self, method):
        try:
            if self.headers.get('Host') not in self.server.allowed_hosts:
                raise Problem('访问地址未获允许', 403)
            self.limit('requests', 600, 60)
            if method != 'GET':
                origin = self.headers.get('Origin')
                expected_origin = self.server.public_origin if self.public_request() else self.server.origin
                if origin and origin != expected_origin:
                    raise Problem('请求来源不匹配', 403)
                if self.headers.get('X-SCAN3D-Client') != 'portal':
                    raise Problem('缺少请求校验', 403)
            self.route(method, unquote(urlsplit(self.path).path))
        except Problem as exc:
            self.reply({'error': exc.message}, exc.status)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:
            self.reply({'error': '服务处理失败，请重试'}, 500)

    def route(self, method, path):
        if method == 'GET' and path == '/api/status':
            return self.reply({'service': 'scan3d-portal', 'setup': False, 'accounts': 'shared'})
        if method == 'POST' and path in ('/api/register', '/api/setup'):
            self.limit('register', 8, 3600)
            data = self.json_body()
            if path.endswith('setup'):
                if self.public_request():
                    raise Problem('商家初始化仅允许在本机完成', 403)
                if self.client_address[0] not in ('127.0.0.1', '::1') or not hmac.compare_digest(str(data.get('code', '')), self.store.setup_code):
                    raise Problem('初始化口令不正确，请查看启动窗口', 403)
            self.store.add_user(data, 'merchant' if path.endswith('setup') else 'customer')
            return self.reply({'ok': True}, 201)
        if method == 'POST' and path == '/api/login':
            self.limit('login', 30, 900)
            data = self.json_body()
            username = str(data.get('username', '')).strip().lower()
            key = self.client_address_key() + ':' + username
            with self.store.db() as db:
                attempt = db.execute('SELECT * FROM attempts WHERE key=?', (key,)).fetchone()
                if attempt and attempt['until'] > time.time() and attempt['count'] >= 8:
                    raise Problem('尝试过于频繁，请 15 分钟后重试', 429)
                row = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
                salt, expected = row['password'].split(':') if row else ('0' * 32, '0' * 128)
                password = str(data.get('password', ''))[:129]
                actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
                if not row or not hmac.compare_digest(expected, actual):
                    count = attempt['count'] + 1 if attempt and attempt['until'] > time.time() else 1
                    db.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)', (key, count, time.time() + 900))
                    db.commit()
                    raise Problem('账号或密码不正确', 401)
                db.execute('DELETE FROM attempts WHERE key=?', (key,))
                token = secrets.token_urlsafe(32)
                db.execute('DELETE FROM sessions WHERE expiry<?', (time.time(),))
                db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), row['id'], time.time() + 86400))
            secure = '; Secure' if self.public_request() else ''
            return self.reply({'ok': True}, cookie=f'scan3d_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400{secure}')
        if path.startswith('/api/'):
            user = self.user()
            if method == 'GET' and path == '/api/me':
                return self.reply({k: user[k] for k in ('id', 'username', 'name', 'role')})
            if method == 'POST' and path == '/api/logout':
                cookie = SimpleCookie(self.headers.get('Cookie'))
                with self.store.db() as db:
                    db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(cookie['scan3d_session'].value.encode()).hexdigest(),))
                return self.reply({'ok': True}, cookie='scan3d_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')
            if method == 'POST' and path == '/api/claim-code':
                code = secrets.token_hex(5).upper()
                with self.store.db() as db:
                    db.execute('UPDATE users SET claim=?, claim_expiry=? WHERE id=?', (code, time.time() + 86400, user['id']))
                return self.reply({'code': code})
            if path == '/api/items' and method == 'GET':
                with self.store.db() as db:
                    rows = [dict(r) for r in db.execute("SELECT * FROM items WHERE merchant=? OR (owner=? AND status='delivered') ORDER BY created DESC", (user['id'], user['id']))]
                    for row in rows:
                        if row['owner'] != user['id']:
                            row['story'] = ''  # Uploading a file does not grant access to its owner's story.
                        owner = db.execute('SELECT name,username FROM users WHERE id=?', (row['owner'],)).fetchone()
                        row['customer'] = dict(owner)
                        row['files'] = [dict(f) for f in db.execute('SELECT id,name,ext,size,sha FROM files WHERE item=?', (row['id'],))]
                return self.reply({'items': rows})
            if path == '/api/items' and method == 'POST':
                data = self.json_body()
                title = str(data.get('title', '')).strip()
                note = str(data.get('note', '')).strip()
                if not 1 <= len(title) <= 80 or len(note) > 2000:
                    raise Problem('请填写藏品名称（最多 80 字），备注最多 2000 字')
                with self.store.db() as db:
                    db.execute('BEGIN IMMEDIATE')
                    is_self = data.get('recipient') == 'self'
                    if is_self:
                        customer = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
                    else:
                        customer = db.execute('SELECT * FROM users WHERE username=? AND claim=? AND claim_expiry>?', (str(data.get('customer', '')).strip().lower(), str(data.get('code', '')).strip().upper(), time.time())).fetchone()
                    if not customer:
                        raise Problem('接收方账号或交付码不正确，或交付码已过期')
                    if db.execute('SELECT count(*) FROM items WHERE owner=?', (customer['id'],)).fetchone()[0] >= 200:
                        raise Problem('接收方已达到 200 件藏品的试用上限')
                    item_id = secrets.token_hex(16)
                    db.execute('INSERT INTO items(id,merchant,owner,title,note,created) VALUES(?,?,?,?,?,?)', (item_id, user['id'], customer['id'], title, note, time.time()))
                    if not is_self:
                        db.execute('UPDATE users SET claim=NULL,claim_expiry=0 WHERE id=?', (customer['id'],))
                return self.reply({'id': item_id}, 201)
            match = re.fullmatch(r'/api/items/([a-f0-9]{32})/(files|deliver|story)', path)
            if match and method == 'POST':
                item_id, action = match.groups()
                item = self.allowed_item(item_id, user)
                if action == 'story':
                    if item['owner'] != user['id'] or item['status'] != 'delivered':
                        raise Problem('入库后的纪念故事仅由藏品主人编辑', 403)
                    data = self.json_body()
                    story = str(data.get('story', ''))
                    if len(story) > 10000:
                        raise Problem('纪念故事最多 10000 字')
                    with self.store.db() as db:
                        db.execute('UPDATE items SET story=? WHERE id=?', (story, item_id))
                    return self.reply({'ok': True})
                if item['merchant'] != user['id']:
                    raise Problem('仅本次上传者可以录入与交付', 403)
                if item['status'] != 'draft':
                    raise Problem('已交付藏品不可覆盖，请新建交付', 409)
                if action == 'deliver':
                    with self.store.db() as db:
                        db.execute('BEGIN IMMEDIATE')
                        if not db.execute('SELECT 1 FROM files WHERE item=?', (item_id,)).fetchone():
                            raise Problem('请先上传至少一个点云或 STL 文件')
                        db.execute("UPDATE items SET status='delivered',delivered=? WHERE id=? AND status='draft'", (time.time(), item_id))
                    return self.reply({'ok': True})
                name = unquote(self.headers.get('X-File-Name', ''))
                self.limit('upload', 20, 60)
                if not name or len(name) > 160 or any(c in name for c in '/\\\r\n\x00'):
                    raise Problem('文件名不正确')
                ext = name.rsplit('.', 1)[-1].lower()
                content = self.body(MAX_FILE)
                validate_file(ext, content)
                file_id = secrets.token_hex(16)
                target = self.store.root / 'files' / file_id
                with self.store.db() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if db.execute('SELECT status FROM items WHERE id=?', (item_id,)).fetchone()[0] != 'draft':
                        raise Problem('藏品已交付', 409)
                    if db.execute('SELECT count(*) FROM files WHERE item=?', (item_id,)).fetchone()[0] >= 8:
                        raise Problem('每件藏品最多 8 个文件')
                    used = db.execute('SELECT COALESCE(sum(f.size),0) FROM files f JOIN items i ON f.item=i.id WHERE i.owner=?', (item['owner'],)).fetchone()[0]
                    total = db.execute('SELECT COALESCE(sum(size),0) FROM files').fetchone()[0]
                    if used + len(content) > MAX_CUSTOMER_BYTES or total + len(content) > MAX_TOTAL_BYTES:
                        raise Problem('试用存储配额不足，请联系管理员', 413)
                    if shutil.disk_usage(self.store.root).free < len(content) + 512 * 1024 * 1024:
                        raise Problem('服务器可用空间不足，请稍后联系管理员', 507)
                    target.write_bytes(content)
                    try:
                        db.execute('INSERT INTO files VALUES(?,?,?,?,?,?)', (file_id, item_id, name, ext, len(content), hashlib.sha256(content).hexdigest()))
                    except Exception:
                        target.unlink(missing_ok=True)
                        raise
                return self.reply({'id': file_id}, 201)
            match = re.fullmatch(r'/api/files/([a-f0-9]{32})', path)
            if match and method == 'GET':
                with self.store.db() as db:
                    file = db.execute('SELECT * FROM files WHERE id=?', (match[1],)).fetchone()
                if not file:
                    raise Problem('文件不存在', 404)
                self.allowed_item(file['item'], user)
                return self.send_file(self.store.root / 'files' / file['id'], 'application/octet-stream')
            raise Problem('接口不存在或无操作权限', 403)
        if method == 'GET':
            static = {'/': ROOT / 'web/index.html', '/app.js': ROOT / 'web/app.js', '/style.css': ROOT / 'web/style.css'}
            if path in static:
                return self.send_file(static[path])
            # Only public, explicitly packaged dependency files are exposed.
            if re.fullmatch(r'/vendor/[A-Za-z0-9_.-]+', path):
                return self.send_file(ROOT / 'web' / path.lstrip('/'))
            if path == '/brand.png':
                return self.send_file(ROOT / 'web/assets/scan3d-brand-sage.png')
            if path in ('/font.woff2', '/sans.woff2'):
                return self.send_file(ROOT / ('web/assets/scan3d-' + ('marker' if path == '/font.woff2' else 'sans') + '.woff2'))
        raise Problem('页面不存在', 404)

    def send_file(self, file, mime=None):
        if not file.is_file():
            raise Problem('文件不存在', 404)
        mime = mime or {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.woff2': 'font/woff2'}.get(file.suffix, 'text/plain')
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(file.stat().st_size))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        with file.open('rb') as source:
            while chunk := source.read(1024 * 1024):
                self.wfile.write(chunk)


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(*args)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.sendall(b'HTTP/1.0 503 Busy\r\nContent-Length: 0\r\n\r\n')
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def make_server(directory, port=8840, public_origin=None):
    import base64
    if public_origin:
        url = urlsplit(public_origin)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
            raise ValueError('Public origin must be an HTTPS origin')
        public_origin = f'https://{url.netloc}'
    server = BoundedServer(('127.0.0.1', port), Handler)
    server.store = Store(directory)
    port = server.server_address[1]
    server.origin = f'http://127.0.0.1:{port}'
    server.local_host = f'127.0.0.1:{port}'
    server.public_origin = public_origin
    server.allowed_hosts = [server.local_host] + ([urlsplit(public_origin).netloc] if public_origin else [])
    import_map = re.search(r'<script type="importmap">(.*?)</script>', (ROOT / 'web/index.html').read_text(encoding='utf-8')).group(1)
    digest = base64.b64encode(hashlib.sha256(import_map.encode()).digest()).decode()
    server.csp = f"default-src 'self'; script-src 'self' 'sha256-{digest}'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8840)
    parser.add_argument('--data', default=str(ROOT / 'data'))
    parser.add_argument('--public-origin')
    args = parser.parse_args()
    server = make_server(args.data, args.port, args.public_origin)
    print('SCAN3D: ' + server.origin, flush=True)
    print('Unified accounts: register on the website to upload or receive collections.', flush=True)
    server.serve_forever()
