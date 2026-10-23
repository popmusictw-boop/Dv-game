"""北特教案生成系統 — Flask 應用程式。

啟動（開發）：python app.py         正式部署請見 DEPLOY.md（gunicorn／Docker、HTTPS、環境變數金鑰）。
"""
import io, json, logging, os, secrets, shutil, subprocess, tempfile, time, uuid, functools, datetime
from flask import Flask, jsonify, request, session, send_from_directory, abort, Response, g
from werkzeug.security import check_password_hash, generate_password_hash

from btsys.config import Config
from btsys import db as dbm, crypto, options, curriculum, extract, analyze, planner, export_docx, ai

log = logging.getLogger('btlesson')

def create_app(test_config=None):
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    app.config.from_object(Config)
    if test_config: app.config.update(test_config)
    if app.config['ENV'] == 'production' and not (os.environ.get('BT_SECRET_KEY') and os.environ.get('BT_DATA_KEY')):
        raise RuntimeError('正式環境必須以環境變數設定 BT_SECRET_KEY 與 BT_DATA_KEY（金鑰不可與資料存放在同一處）')
    app.config.update(
        MAX_CONTENT_LENGTH=app.config['MAX_UPLOAD_MB'] * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=app.config['SESSION_SECURE'],
        PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=app.config['SESSION_HOURS']))
    dbm.init_db(app.config['DATABASE'])
    app.teardown_appcontext(dbm.close_db)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)  # 不輸出含參數的預設存取紀錄

    store = curriculum.store(app)
    loaded_imports = set()

    def sync_imports():
        """多個伺服器執行個體時，確保教師匯入的課綱在每個執行個體都已載入。"""
        for r in dbm.get_db().execute('SELECT id, items_json FROM curriculum_imports').fetchall():
            if r['id'] not in loaded_imports:
                store.add_imported(json.loads(r['items_json'])); loaded_imports.add(r['id'])
    with app.app_context():
        sync_imports()

    # ---------- 上傳檔案隔日自動刪除 ----------
    TZ = datetime.timezone(datetime.timedelta(hours=8))  # 臺灣時間
    _last_purge = {'at': 0.0}

    def purge_uploaded_files():
        """隔日清除：刪除「今天（臺灣時間）以前」建立的教案（含學生資料、分析與生成內容）及所有上傳檔案。
        系統不長期保存教案；教師需於當天下載 Word 檔，在自己的電腦上調整。"""
        today0 = datetime.datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        db = dbm.get_db()
        files = db.execute('SELECT id FROM files WHERE created_at < ? OR draft_id IN (SELECT id FROM drafts WHERE created_at < ?)', (today0, today0)).fetchall()
        drafts = db.execute('SELECT id FROM drafts WHERE created_at < ?', (today0,)).fetchall()
        if files:
            db.execute('DELETE FROM files WHERE created_at < ? OR draft_id IN (SELECT id FROM drafts WHERE created_at < ?)', (today0, today0))
        if drafts:
            db.execute('DELETE FROM drafts WHERE created_at < ?', (today0,))
        db.commit()
        if files or drafts:
            dbm.audit(None, 'auto_purge', f'drafts={len(drafts)} files={len(files)}')
        _last_purge['at'] = time.time()
        return len(files) + len(drafts)

    @app.before_request
    def lazy_purge():
        # 除每日排程外，系統有人使用時每 10 分鐘也檢查一次，確保逾期檔案不會留存
        if request.path.startswith('/api/') and time.time() - _last_purge['at'] > 600:
            try: purge_uploaded_files()
            except Exception: log.exception('自動刪除檔案失敗')

    @app.get('/api/cron/purge')
    def cron_purge():
        secret = os.environ.get('CRON_SECRET')
        if not secret or request.headers.get('Authorization') != f'Bearer {secret}':
            return jsonify(error='forbidden'), 403
        return jsonify(deleted=purge_uploaded_files())

    # ---------- 共用 ----------
    @app.after_request
    def headers(resp):
        resp.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Referrer-Policy'] = 'no-referrer'
        resp.headers['Cache-Control'] = 'no-store'
        # 存取紀錄：只記錄方法、路徑、狀態碼與使用者編號，不含查詢參數或內容
        log.info('%s %s %s uid=%s', request.method, request.path, resp.status_code, session.get('uid'))
        return resp

    @app.before_request
    def csrf_guard():
        if request.path.startswith('/api/curriculum') and session.get('uid'):
            try: sync_imports()
            except Exception: pass
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH') and request.path.startswith('/api/'):
            if request.headers.get('X-BT-Requested') != '1':
                return jsonify(error='請求來源驗證失敗'), 403

    def login_required(fn):
        @functools.wraps(fn)
        def w(*a, **k):
            uid = session.get('uid')
            if not uid: return jsonify(error='請先登入'), 401
            u = dbm.get_db().execute('SELECT * FROM users WHERE id=? AND active=1', (uid,)).fetchone()
            if not u: session.clear(); return jsonify(error='請先登入'), 401
            g.user = u
            return fn(*a, **k)
        return w

    def admin_required(fn):
        @functools.wraps(fn)
        @login_required
        def w(*a, **k):
            if not g.user['is_admin']: return jsonify(error='需要管理者權限'), 403
            return fn(*a, **k)
        return w

    def load_draft(did):
        row = dbm.get_db().execute('SELECT * FROM drafts WHERE id=? AND owner_id=?', (did, g.user['id'])).fetchone()
        if not row: abort(404)
        return row, crypto.dec_json(row['content_enc'])

    def save_plan(did, plan):
        plan.setdefault('meta', {})['updatedAt'] = time.time()
        title = (plan.get('basic', {}).get('unit') or '未命名教案')[:60]
        dbm.get_db().execute('UPDATE drafts SET content_enc=?, title=?, updated_at=? WHERE id=? AND owner_id=?',
                             (crypto.enc_json(plan), title, time.time(), did, g.user['id']))
        dbm.get_db().commit()

    def ctx_of(plan):
        b = plan.get('basic', {})
        return dict(dept=b.get('dept'), grade=b.get('grade'), domain=b.get('domain'), shDept=b.get('shDept'),
                    unit=b.get('unit'), minutes=b.get('minutes'))

    @app.errorhandler(413)
    def too_big(_):
        return jsonify(error=f'檔案超過 {app.config["MAX_UPLOAD_MB"]} MB 上限'), 413

    @app.errorhandler(404)
    def nf(_):
        return jsonify(error='找不到資料或無權限存取'), 404

    # ---------- 頁面 ----------
    @app.get('/')
    def index():
        return send_from_directory(app.static_folder, 'index.html')

    # ---------- 登入 ----------
    @app.post('/api/login')
    def login():
        d = request.get_json(force=True)
        uname = (d.get('username') or '').strip().lower()
        if uname.endswith('@tpmr.tp.edu.tw'): uname = uname.split('@')[0]  # 校內信箱可直接當帳號登入
        u = dbm.get_db().execute('SELECT * FROM users WHERE username=? AND active=1', (uname,)).fetchone()
        if not u or not check_password_hash(u['password_hash'], d.get('password', '')):
            time.sleep(0.5)
            return jsonify(error='帳號或密碼錯誤'), 401
        session.clear(); session.permanent = True; session['uid'] = u['id']
        # 登入失敗不洩漏帳號是否存在；成功後才回傳是否需變更密碼
        dbm.audit(u['id'], 'login')
        return jsonify(user=dict(name=u['display_name'], admin=bool(u['is_admin']), mustChange=bool(u['must_change'])))

    @app.post('/api/logout')
    def logout():
        session.clear(); return jsonify(ok=True)

    @app.get('/api/me')
    @login_required
    def me():
        return jsonify(user=dict(name=g.user['display_name'], admin=bool(g.user['is_admin']), mustChange=bool(g.user['must_change'])))

    @app.post('/api/me/password')
    @login_required
    def change_password():
        d = request.get_json(force=True)
        if not check_password_hash(g.user['password_hash'], d.get('old', '')):
            return jsonify(error='目前密碼不正確'), 400
        if len(d.get('new', '')) < 10:
            return jsonify(error='新密碼至少 10 碼'), 400
        dbm.get_db().execute('UPDATE users SET password_hash=?, must_change=0 WHERE id=?', (generate_password_hash(d['new']), g.user['id']))
        dbm.get_db().commit(); dbm.audit(g.user['id'], 'password_change')
        return jsonify(ok=True)

    @app.get('/api/privacy')
    @login_required
    def privacy():
        ocr = extract.ocr_status(app.config['OCR_LANG'])
        return jsonify(
            aiEnabled=app.config['AI_ENABLED'], aiModel=app.config['AI_MODEL'] if app.config['AI_ENABLED'] else None,
            ocr=ocr, retentionDays=app.config['RETENTION_DAYS'], filePolicy='next-day', draftPolicy='next-day', maxUploadMb=app.config['MAX_UPLOAD_MB'],
            supported=extract.SUPPORTED, unsupported=extract.UNSUPPORTED_HINT)

    # ---------- 選單與課綱 ----------
    @app.get('/api/options')
    @login_required
    def get_options():
        return jsonify(options.OPTIONS)

    @app.get('/api/curriculum/sources')
    @login_required
    def cur_sources():
        imps = [dict(id=r['id'], title=r['title'], version=r['version'], url=r['source_url'], count=len(json.loads(r['items_json'])))
                for r in dbm.get_db().execute('SELECT * FROM curriculum_imports ORDER BY id DESC')]
        return jsonify(dict(store.sources, imports=imps))

    @app.post('/api/curriculum/recommend')
    @login_required
    def cur_recommend():
        d = request.get_json(force=True)
        return jsonify(store.recommend(d.get('context', {}), d.get('unit', ''), d.get('abilities', []), int(d.get('limit', 12))))

    @app.post('/api/curriculum/items')
    @login_required
    def cur_items():
        d = request.get_json(force=True)
        return jsonify(store.context_items(d.get('context', {})))

    @app.get('/api/curriculum/search')
    @login_required
    def cur_search():
        a = request.args
        return jsonify(items=store.search(a.get('q', ''), a.get('framework') or None, a.get('type') or None, a.get('subject') or None))

    @app.post('/api/curriculum/validate')
    @login_required
    def cur_validate():
        d = request.get_json(force=True)
        return jsonify(results=store.validate(d.get('context', {}), d.get('selection', [])))

    @app.post('/api/curriculum/import')
    @login_required
    def cur_import():
        f = request.files.get('file')
        if not f: return jsonify(error='請選擇 CSV 或 JSON 檔'), 400
        title = request.form.get('title', '').strip(); version = request.form.get('version', '').strip()
        if not title or not version:
            return jsonify(error='請填寫課綱名稱與版本'), 400
        try:
            items, errors = curriculum.parse_import(f.filename, f.read(), [request.form.get('dept')] if request.form.get('dept') else ['kg', 'elem', 'jh', 'sh'])
        except Exception as e:
            return jsonify(error=f'檔案格式無法解析：{e}'), 400
        if errors and not items:
            return jsonify(error='；'.join(errors[:10])), 400
        db = dbm.get_db()
        db.execute('INSERT INTO curriculum_imports(owner_id,title,version,source_url,items_json,created_at) VALUES(?,?,?,?,?,?)',
                   (g.user['id'], title, version, request.form.get('url'), json.dumps(items, ensure_ascii=False), time.time()))
        db.commit(); store.add_imported(items); dbm.audit(g.user['id'], 'curriculum_import', title)
        return jsonify(imported=len(items), errors=errors)

    # ---------- 草稿 ----------
    @app.get('/api/drafts')
    @login_required
    def drafts():
        rows = dbm.get_db().execute('SELECT id,title,created_at,updated_at FROM drafts WHERE owner_id=? ORDER BY updated_at DESC', (g.user['id'],))
        return jsonify(drafts=[dict(r) for r in rows])

    @app.post('/api/drafts')
    @login_required
    def new_draft():
        plan = request.get_json(silent=True) or {}
        plan.setdefault('basic', {}); plan.setdefault('students', []); plan.setdefault('analyses', {})
        plan.setdefault('curriculum', dict(core=[], performance=[], content=[])); plan.setdefault('groups', [])
        plan.setdefault('goals', {}); plan.setdefault('activities', []); plan.setdefault('meta', dict(createdAt=time.time()))
        db = dbm.get_db(); now = time.time()
        cur = db.execute('INSERT INTO drafts(owner_id,title,content_enc,created_at,updated_at) VALUES(?,?,?,?,?)',
                         (g.user['id'], '未命名教案', crypto.enc_json(plan), now, now))
        db.commit(); dbm.audit(g.user['id'], 'draft_create', cur.lastrowid)
        return jsonify(id=cur.lastrowid, plan=plan)

    @app.get('/api/drafts/<int:did>')
    @login_required
    def get_draft(did):
        _, plan = load_draft(did)
        files = [file_meta(r) for r in dbm.get_db().execute('SELECT id,student_key,filename_enc,mime,size,status,extract_enc FROM files WHERE draft_id=? AND owner_id=?', (did, g.user['id']))]
        return jsonify(id=did, plan=plan, files=files)

    @app.put('/api/drafts/<int:did>')
    @login_required
    def put_draft(did):
        _, old = load_draft(did)
        plan = request.get_json(force=True)
        plan['analyses'] = plan.get('analyses') or old.get('analyses', {})
        save_plan(did, plan)
        return jsonify(ok=True, savedAt=time.time())

    @app.delete('/api/drafts/<int:did>')
    @login_required
    def del_draft(did):
        load_draft(did)
        db = dbm.get_db()
        db.execute('DELETE FROM files WHERE draft_id=?', (did,)); db.execute('DELETE FROM drafts WHERE id=?', (did,))
        db.commit(); dbm.audit(g.user['id'], 'draft_delete', did)
        return jsonify(ok=True)

    # ---------- 檔案 ----------
    def file_meta(r):
        ex = crypto.dec_json(r['extract_enc']) if r['extract_enc'] else None
        return dict(id=r['id'], studentKey=r['student_key'], filename=crypto.dec_text(r['filename_enc']), mime=r['mime'],
                    size=r['size'], status=r['status'], method=(ex or {}).get('method'), warnings=(ex or {}).get('warnings', []),
                    pages=(ex or {}).get('pages'), segments=len((ex or {}).get('segments', [])), error=(ex or {}).get('error'))

    def _store_file(did, student_key, filename, data, mime, extraction, status):
        db = dbm.get_db()
        cur = db.execute('INSERT INTO files(draft_id,owner_id,student_key,filename_enc,mime,size,blob_enc,extract_enc,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                         (did, g.user['id'], student_key, crypto.enc_text(filename), mime, len(data), crypto.enc_bytes(data), crypto.enc_json(extraction), status, time.time()))
        db.commit(); dbm.audit(g.user['id'], 'file_upload', cur.lastrowid)
        return db.execute('SELECT id,student_key,filename_enc,mime,size,status,extract_enc FROM files WHERE id=?', (cur.lastrowid,)).fetchone()

    @app.post('/api/drafts/<int:did>/files')
    @login_required
    def upload(did):
        load_draft(did)
        sk = request.form.get('studentKey', '')
        if not sk: return jsonify(error='請先選擇此檔案所屬的學生'), 400
        out = []
        for f in request.files.getlist('file'):
            data = f.read(); name = f.filename or '未命名'
            try:
                ex = extract.extract(data, name, app.config['OCR_LANG']); status = '已擷取' if ex['segments'] else '無文字'
            except extract.Unsupported as e:
                out.append(dict(filename=name, status='不支援', error=str(e))); continue
            except Exception as e:
                ex = dict(segments=[], method='', warnings=[], error='檔案讀取失敗，可能已損毀或加密。'); status = '失敗'
            out.append(file_meta(_store_file(did, sk, name, data, f.mimetype or '', ex, status)))
        return jsonify(files=out)

    @app.post('/api/drafts/<int:did>/paste')
    @login_required
    def paste(did):
        load_draft(did)
        d = request.get_json(force=True)
        text, sk = (d.get('text') or '').strip(), d.get('studentKey', '')
        if not text or not sk: return jsonify(error='請選擇學生並貼上文字'), 400
        label = (d.get('label') or '貼上文字').strip()[:40]
        row = _store_file(did, sk, label, text.encode(), 'text/plain', extract.from_pasted(text), '已擷取')
        return jsonify(file=file_meta(row))

    @app.get('/api/drafts/<int:did>/files/<int:fid>/segments')
    @login_required
    def segments(did, fid):
        r = dbm.get_db().execute('SELECT * FROM files WHERE id=? AND draft_id=? AND owner_id=?', (fid, did, g.user['id'])).fetchone()
        if not r: abort(404)
        return jsonify(crypto.dec_json(r['extract_enc']))

    @app.delete('/api/drafts/<int:did>/files/<int:fid>')
    @login_required
    def del_file(did, fid):
        row, plan = load_draft(did)
        db = dbm.get_db()
        r = db.execute('SELECT * FROM files WHERE id=? AND draft_id=? AND owner_id=?', (fid, did, g.user['id'])).fetchone()
        if not r: abort(404)
        db.execute('DELETE FROM files WHERE id=?', (fid,)); db.commit()
        # 同步移除以此檔為佐證的分析項目
        a = plan.get('analyses', {}).get(r['student_key'])
        if a:
            a['abilities'] = [x for x in a['abilities'] if x['evidence'].get('fileId') != fid]
            for k in ('gender', 'disability'):
                b = a['basic'][k]
                b['evidence'] = [e for e in b['evidence'] if e.get('fileId') != fid]
                if not b['evidence']: b.update(value='', status='資料不足')
            save_plan(did, plan)
        dbm.audit(g.user['id'], 'file_delete', fid)
        return jsonify(ok=True, analysis=a)

    # ---------- 分析 ----------
    @app.post('/api/drafts/<int:did>/analyze')
    @login_required
    def do_analyze(did):
        _, plan = load_draft(did)
        d = request.get_json(force=True)
        sk = d.get('studentKey')
        st = next((s for s in plan.get('students', []) if s['key'] == sk), None)
        if not st: return jsonify(error='找不到學生'), 400
        rows = dbm.get_db().execute('SELECT * FROM files WHERE draft_id=? AND owner_id=? AND student_key=?', (did, g.user['id'], sk)).fetchall()
        files = [dict(fileId=r['id'], filename=crypto.dec_text(r['filename_enc']), extraction=crypto.dec_json(r['extract_enc'])) for r in rows]
        files = [f for f in files if f['extraction'].get('segments')]
        if not files:
            return jsonify(error='此學生尚無可分析的文字資料（未上傳、格式不支援或辨識失敗）。系統不會在無資料時產生能力描述。'), 400
        b = plan.get('basic', {})
        unit_text = ' '.join([b.get('unit', ''), b.get('subjectLabel', '')] + [x.get('officialText', '') for x in plan.get('curriculum', {}).get('content', [])])
        result = analyze.analyze_student(sk, files, unit_text)
        result['rejected'] = []
        if d.get('useAI'):
            if not app.config['AI_ENABLED']:
                return jsonify(error='系統未啟用外部 AI 分析（管理者未設定）。已提供本機規則式分析。'), 400
            if not d.get('consent'):
                return jsonify(error='使用外部 AI 前需勾選同意資料送出說明'), 400
            try:
                items, rejected = ai.analyze_with_ai(app.config, st.get('code') or '學生', st.get('name') or '', files, b.get('unit', ''), b.get('subjectLabel', ''))
                result['abilities'] = items; result['rejected'] = rejected; result['mode'] = 'ai'
                covered = {x for a in items for x in a['domains']}
                result['insufficient'] = [x for x in result['insufficient'] if x['domain'] not in covered]
                dbm.audit(g.user['id'], 'ai_analyze', did)
            except Exception:
                return jsonify(error='外部 AI 服務呼叫失敗，未送出結果；可改用本機分析。'), 502
        result['generatedAt'] = time.time()
        plan.setdefault('analyses', {})[sk] = result
        save_plan(did, plan)
        return jsonify(analysis=result)

    @app.delete('/api/drafts/<int:did>/analysis/<sk>')
    @login_required
    def del_analysis(did, sk):
        _, plan = load_draft(did)
        plan.get('analyses', {}).pop(sk, None)
        for s in plan.get('students', []):
            if s['key'] == sk: s.update(abilitySummary='', abilityConfirmed=False)
        save_plan(did, plan); dbm.audit(g.user['id'], 'analysis_delete', did)
        return jsonify(ok=True)

    # ---------- 分組、目標、活動 ----------
    @app.post('/api/drafts/<int:did>/groups/suggest')
    @login_required
    def groups_suggest(did):
        _, plan = load_draft(did)
        d = request.get_json(silent=True) or {}
        students = [s for s in plan.get('students', []) if not s.get('excludeFromPlan')]
        return jsonify(planner.suggest_groups(students, plan.get('analyses', {}), d.get('names')))

    @app.post('/api/drafts/<int:did>/goals/suggest')
    @login_required
    def goals_suggest(did):
        _, plan = load_draft(did)
        cur = plan.get('curriculum', {})
        r = planner.suggest_goals(ctx_of(plan), plan.get('groups', []), plan.get('analyses', {}), cur.get('performance', []), cur.get('content', []))
        return (jsonify(r), 400) if r.get('error') else jsonify(r)

    @app.post('/api/drafts/<int:did>/activities/suggest')
    @login_required
    def acts_suggest(did):
        _, plan = load_draft(did)
        return jsonify(planner.suggest_activities(ctx_of(plan), plan.get('groups', []), plan.get('goals', {}), plan.get('curriculum', {}).get('content', [])))

    # ---------- 匯出 ----------
    def _check_ready(plan):
        issues = []
        acts = plan.get('activities', [])
        tc = planner.check_time(acts, plan.get('basic', {}).get('minutes'))
        if not tc['ok']: issues.append(f'教學時間合計 {tc["total"]} 分，與每節 {tc["minutes"]} 分不符')
        for s in plan.get('students', []):
            if not s.get('excludeFromPlan') and not s.get('abilityConfirmed'):
                issues.append(f'學生「{s.get("code") or s.get("name")}」的先備能力尚未經教師確認')
        return issues

    @app.get('/api/drafts/<int:did>/check')
    @login_required
    def check(did):
        _, plan = load_draft(did)
        return jsonify(issues=_check_ready(plan))

    def _fname(plan, ext):
        unit = (plan.get('basic', {}).get('unit') or '教案').replace('/', '_')[:30]
        return f'北特教學設計表_{unit}.{ext}'

    def _download(data, name, mime):
        from urllib.parse import quote
        return Response(data, mimetype=mime, headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(name)}"})

    @app.get('/api/drafts/<int:did>/export.docx')
    @login_required
    def export_word(did):
        _, plan = load_draft(did)
        dbm.audit(g.user['id'], 'export_docx', did)
        return _download(export_docx.build_docx(plan), _fname(plan, 'docx'),
                         'application/vnd.openxmlformats-officedocument.wordprocessingml.document')

    @app.get('/api/drafts/<int:did>/export.pdf')
    @login_required
    def export_pdf(did):
        _, plan = load_draft(did)
        soffice = shutil.which(app.config['SOFFICE']) or shutil.which('libreoffice')
        if not soffice:
            return jsonify(error='伺服器未安裝 LibreOffice，無法轉 PDF。可使用預覽頁的「列印／另存 PDF」。'), 503
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, 'plan.docx')
            open(src, 'wb').write(export_docx.build_docx(plan))
            try:
                subprocess.run([soffice, '--headless', f'-env:UserInstallation=file://{td}/lo', '--convert-to', 'pdf', '--outdir', td, src],
                               capture_output=True, timeout=120, check=True)
                pdf = open(os.path.join(td, 'plan.pdf'), 'rb').read()
            except Exception:
                return jsonify(error='PDF 轉檔失敗，請改下載 Word 或使用列印功能。'), 500
        dbm.audit(g.user['id'], 'export_pdf', did)
        return _download(pdf, _fname(plan, 'pdf'), 'application/pdf')

    # ---------- 管理 ----------
    @app.get('/api/admin/users')
    @admin_required
    def users():
        return jsonify(users=[dict(id=r['id'], username=r['username'], name=r['display_name'], admin=bool(r['is_admin']), active=bool(r['active']))
                              for r in dbm.get_db().execute('SELECT * FROM users')])

    @app.post('/api/admin/users')
    @admin_required
    def add_user():
        d = request.get_json(force=True)
        if len(d.get('password', '')) < 10: return jsonify(error='密碼至少 10 碼'), 400
        try:
            dbm.get_db().execute('INSERT INTO users(username,display_name,password_hash,is_admin,must_change,created_at) VALUES(?,?,?,?,1,?)',
                                 (d['username'].strip().lower(), d.get('name') or d['username'], generate_password_hash(d['password']), int(bool(d.get('admin'))), time.time()))
            dbm.get_db().commit()
        except Exception:
            return jsonify(error='帳號已存在'), 400
        return jsonify(ok=True)

    @app.post('/api/admin/users/<int:uid_>')
    @admin_required
    def edit_user(uid_):
        d = request.get_json(force=True); db = dbm.get_db()
        if uid_ == g.user['id'] and d.get('active') is False:
            return jsonify(error='不能停用自己的帳號'), 400
        if 'active' in d: db.execute('UPDATE users SET active=? WHERE id=?', (int(bool(d['active'])), uid_))
        if d.get('password'):
            if len(d['password']) < 10: return jsonify(error='密碼至少 10 碼'), 400
            db.execute('UPDATE users SET password_hash=?, must_change=1 WHERE id=?', (generate_password_hash(d['password']), uid_))
        db.commit(); dbm.audit(g.user['id'], 'user_edit', uid_)
        return jsonify(ok=True)

    @app.delete('/api/admin/users/<int:uid_>')
    @admin_required
    def delete_user(uid_):
        db = dbm.get_db()
        if uid_ == g.user['id']: return jsonify(error='不能刪除自己的帳號'), 400
        if db.execute('SELECT id FROM drafts WHERE owner_id=?', (uid_,)).fetchone():
            return jsonify(error='此帳號仍有教案，請先停用帳號或由該教師刪除教案'), 400
        db.execute('DELETE FROM users WHERE id=?', (uid_,)); db.commit(); dbm.audit(g.user['id'], 'user_delete', uid_)
        return jsonify(ok=True)

    @app.cli.command('purge-files')
    def purge_files_cmd():
        print(f'已刪除 {purge_uploaded_files()} 個逾期上傳檔案')

    @app.cli.command('purge-old')
    def purge_old():
        """刪除超過保存期限（BT_RETENTION_DAYS）未更新的草稿與檔案。"""
        cutoff = time.time() - app.config['RETENTION_DAYS'] * 86400
        db = dbm.get_db()
        old = db.execute('SELECT id FROM drafts WHERE updated_at<?', (cutoff,)).fetchall()
        for r in old:
            db.execute('DELETE FROM files WHERE draft_id=?', (r['id'],)); db.execute('DELETE FROM drafts WHERE id=?', (r['id'],))
        db.commit(); print(f'已刪除 {len(old)} 份逾期草稿')

    return app

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    create_app().run(host=os.environ.get('BT_HOST', '127.0.0.1'), port=int(os.environ.get('BT_PORT', '5000')), debug=False)

# Vercel（Serverless Flask）進入點：部署環境會設定 VERCEL=1
if os.environ.get('VERCEL'):
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    app = create_app()
