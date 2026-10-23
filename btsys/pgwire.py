"""極簡 PostgreSQL 連線（純 Python、無外部套件）：TLS、SCRAM-SHA-256、Extended Query（參數以 $1..$n 綁定）。
僅實作本系統需要的功能；參數一律由伺服器端綁定，不做字串拼接，避免 SQL 注入。"""
import base64, hashlib, hmac, os, socket, ssl, struct
from urllib.parse import urlparse, unquote

class PgError(Exception):
    pass

_INT = {20, 21, 23, 26}
_FLOAT = {700, 701, 1700}

def _decode(oid, raw):
    if raw is None: return None
    s = raw.decode()
    if oid in _INT: return int(s)
    if oid in _FLOAT: return float(s)
    if oid == 16: return s == 't'
    if oid == 17: return bytes.fromhex(s[2:]) if s.startswith('\\x') else s.encode()
    return s

def _encode(v):
    if v is None: return None
    if isinstance(v, (bytes, bytearray, memoryview)): return ('\\x' + bytes(v).hex()).encode()
    if isinstance(v, bool): return b't' if v else b'f'
    return str(v).encode()

class Row(dict):
    def __getitem__(self, k):
        if isinstance(k, int): return list(self.values())[k]
        return dict.__getitem__(self, k)

class Connection:
    def __init__(self, url, timeout=15):
        u = urlparse(url)
        self.user, self.password = unquote(u.username or ''), unquote(u.password or '')
        self.db = (u.path or '/postgres').lstrip('/') or 'postgres'
        raw = socket.create_connection((u.hostname, u.port or 5432), timeout=timeout)
        sslmode = 'require' if 'sslmode=disable' not in (u.query or '') else 'disable'
        if sslmode == 'require':
            raw.sendall(struct.pack('!ii', 8, 80877103))
            if raw.recv(1) != b'S': raise PgError('伺服器不支援 TLS')
            ctx = ssl.create_default_context()
            ca = os.path.join(os.path.dirname(__file__), 'certs', 'supabase-ca.pem')
            if (u.hostname or '').endswith('.supabase.com') or (u.hostname or '').endswith('.supabase.co'):
                # Supabase 使用自有根憑證；放入 btsys/certs/supabase-ca.pem 即可完整驗證，未放置時仍加密傳輸但不驗證伺服器憑證
                if os.path.exists(ca): ctx = ssl.create_default_context(cafile=ca)
                else: ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            if 'sslverify=0' in (u.query or ''):
                ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            raw = ctx.wrap_socket(raw, server_hostname=u.hostname)
            if os.environ.get('BT_TLS_DIAG') and not getattr(Connection, '_diag', False):
                Connection._diag = True
                try:
                    from cryptography import x509
                    c = x509.load_der_x509_certificate(raw.getpeercert(True))
                    try: aki = c.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value.key_identifier.hex()
                    except Exception: aki = '-'
                    print('TLSDIAG subject=', c.subject.rfc4514_string(), '| issuer=', c.issuer.rfc4514_string(), '| aki=', aki,
                          '| issuer_der=', c.issuer.public_bytes().hex(), flush=True)
                except Exception as e:
                    print('TLSDIAG error', e, flush=True)
        self.sock = raw; self.buf = b''
        self._startup()

    # ---- 低階 ----
    def _send(self, t, payload=b''):
        self.sock.sendall((t or b'') + struct.pack('!i', len(payload) + 4) + payload)

    def _recv_exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk: raise PgError('連線中斷')
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _msg(self):
        t = self._recv_exact(1); ln = struct.unpack('!i', self._recv_exact(4))[0]
        return t, self._recv_exact(ln - 4)

    @staticmethod
    def _err(body):
        f = {}
        for part in body.split(b'\0'):
            if part: f[chr(part[0])] = part[1:].decode(errors='replace')
        return PgError(f"{f.get('C', '')} {f.get('M', '')}")

    def _startup(self):
        params = b'user\0' + self.user.encode() + b'\0database\0' + self.db.encode() + b'\0client_encoding\0UTF8\0\0'
        self._send(None, struct.pack('!i', 196608) + params)
        while True:
            t, body = self._msg()
            if t == b'R':
                code = struct.unpack('!i', body[:4])[0]
                if code == 0: continue
                if code == 3: self._send(b'p', self.password.encode() + b'\0'); continue
                if code == 10: self._scram(); continue
                raise PgError(f'不支援的驗證方式 {code}')
            if t == b'E': raise self._err(body)
            if t == b'Z': return

    def _scram(self):
        nonce = base64.b64encode(os.urandom(18)).decode()
        first_bare = f'n=,r={nonce}'
        msg = b'SCRAM-SHA-256\0' + struct.pack('!i', len('n,,' + first_bare)) + ('n,,' + first_bare).encode()
        self._send(b'p', msg)
        t, body = self._msg()
        if t == b'E': raise self._err(body)
        server_first = body[4:].decode()
        d = dict(kv.split('=', 1) for kv in server_first.split(','))
        salted = hashlib.pbkdf2_hmac('sha256', self.password.encode(), base64.b64decode(d['s']), int(d['i']))
        ckey = hmac.new(salted, b'Client Key', hashlib.sha256).digest()
        skey = hashlib.sha256(ckey).digest()
        final_wo = f'c=biws,r={d["r"]}'
        auth = f'{first_bare},{server_first},{final_wo}'.encode()
        sig = hmac.new(skey, auth, hashlib.sha256).digest()
        proof = base64.b64encode(bytes(a ^ b for a, b in zip(ckey, sig))).decode()
        self._send(b'p', f'{final_wo},p={proof}'.encode())
        t, body = self._msg()
        if t == b'E': raise self._err(body)
        server_key = hmac.new(salted, b'Server Key', hashlib.sha256).digest()
        expect = base64.b64encode(hmac.new(server_key, auth, hashlib.sha256).digest()).decode()
        if f'v={expect}' not in body[4:].decode(): raise PgError('伺服器簽章驗證失敗')

    # ---- 查詢 ----
    def query(self, sql, params=()):
        p = b''.join((struct.pack('!i', -1) if (e := _encode(v)) is None else struct.pack('!i', len(e)) + e) for v in params)
        self._send(b'P', b'\0' + sql.encode() + b'\0' + struct.pack('!h', 0))
        self._send(b'B', b'\0\0' + struct.pack('!h', 0) + struct.pack('!h', len(params)) + p + struct.pack('!h', 0))
        self._send(b'D', b'P\0'); self._send(b'E', b'\0' + struct.pack('!i', 0)); self._send(b'S')
        cols, rows, err = [], [], None
        while True:
            t, body = self._msg()
            if t == b'T':
                n = struct.unpack('!h', body[:2])[0]; pos = 2; cols = []
                for _ in range(n):
                    end = body.index(b'\0', pos); name = body[pos:end].decode(); pos = end + 1
                    oid = struct.unpack('!i', body[pos + 6:pos + 10])[0]; pos += 18
                    cols.append((name, oid))
            elif t == b'D':
                n = struct.unpack('!h', body[:2])[0]; pos = 2; vals = []
                for i in range(n):
                    ln = struct.unpack('!i', body[pos:pos + 4])[0]; pos += 4
                    raw = None if ln == -1 else body[pos:pos + ln]; pos += max(ln, 0)
                    vals.append(_decode(cols[i][1], raw))
                rows.append(Row(zip([c[0] for c in cols], vals)))
            elif t == b'E':
                err = self._err(body)
            elif t == b'Z':
                if err: raise err
                return rows

    def close(self):
        try: self._send(b'X'); self.sock.close()
        except Exception: pass
