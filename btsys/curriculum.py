"""課綱資料：載入、適用性判斷、推薦、檢核、匯入。

原則：
- 只使用逐字擷取並經核對的官方資料（data/curriculum/*.json）或教師匯入且標示來源的資料。
- 系統不產生、不拼湊任何課綱代碼；無資料時回傳「待確認」。
- 教師調整的敘述（teacherText）與官方原文（officialText）分開保存，以 itemId 追溯。
"""
import json, math, re, os, functools, csv, io, hashlib
from collections import Counter
from . import options as opt

ROMAN_STAGE_SUBJECTS = {'社會技巧', '學習策略', '職業教育'}       # Ⅰ～Ⅴ 階段
SP_SA_SUBJECTS = {'生活管理', '溝通訓練', '點字', '定向行動'}      # 初階 sP／進階 sA
NO_STAGE_SUBJECTS = {'功能性動作訓練', '輔助科技應用'}

_CJK = re.compile(r'[㐀-鿿]')

_STOP = set('的與及和並或之於以為等其')

def bigrams(s):
    s = ''.join(ch for ch in s if _CJK.match(ch) or ch.isalnum())
    return [s[i:i+2] for i in range(len(s) - 1) if not (set(s[i:i+2]) & _STOP)]

# 單元常用詞 → 課綱常見用語（僅用於推薦排序，屬系統推估；不改動任何課綱文字）
EXPAND = {
    '上課': ['學校', '規範', '課堂', '指令', '作息'], '坐': ['姿勢', '坐姿', '座位'], '排隊': ['等待', '輪流', '規範'],
    '洗手': ['清潔', '衛生', '洗手'], '購物': ['消費', '金錢', '購買', '商店'], '打掃': ['清潔', '環境', '整理'],
    '用餐': ['飲食', '餐具', '禮儀', '進食'], '吃飯': ['飲食', '餐具', '進食'], '情緒': ['情緒', '壓力', '調整'],
    '溝通': ['表達', '溝通', '回應'], '安全': ['安全', '危險', '防護'], '交通': ['交通', '行動', '搭乘'],
    '禮貌': ['禮儀', '禮節', '互動'], '禮儀': ['禮儀', '禮節'], '合作': ['合作', '團隊', '分工'], '工作': ['工作', '職場'],
    '整理': ['整理', '收納', '歸位'], '服務': ['服務', '顧客'], '清潔': ['清潔', '清潔劑', '工具'], '清洗': ['清潔', '清洗', '洗滌'], '餐具': ['器具', '餐具'], '洗碗': ['清潔', '器具', '餐具'], '衣服': ['衣物', '穿脫', '衣著'],
    '如廁': ['如廁', '衛生'], '時間': ['時間', '作息', '時程'], '錢': ['金錢', '消費'], '友': ['朋友', '人際', '互動'],
    '輪流': ['輪流', '等待'], '規則': ['規範', '規則', '遵守'], '遊戲': ['遊戲', '休閒', '參與'], '手機': ['科技', '資訊', '通訊'],
}

class Store:
    def __init__(self, cur_dir):
        self.items = {}
        sn = json.load(open(os.path.join(cur_dir, 'special_needs.json'), encoding='utf-8'))
        sv = json.load(open(os.path.join(cur_dir, 'service_group.json'), encoding='utf-8'))
        for it in sn + sv['items']:
            self.items[it['id']] = it
        self.sources = json.load(open(os.path.join(cur_dir, 'sources.json'), encoding='utf-8'))
        self._build_idf()

    def _build_idf(self):
        df = Counter()
        for it in self.items.values():
            df.update(set(bigrams(it['text'])))
        n = len(self.items) or 1
        self.idf = {k: math.log(n / (1 + v)) + 1 for k, v in df.items()}

    def add_imported(self, rows):
        for it in rows:
            self.items[it['id']] = it

    def get(self, item_id):
        return self.items.get(item_id)

    # ---------- 適用性 ----------
    def context_items(self, ctx):
        """依部別＋年級＋領域／科目，回傳該科目的全部官方項目（含階段標記）。"""
        dept, grade, dom = ctx.get('dept'), ctx.get('grade'), ctx.get('domain')
        domain = opt.find_domain(dept, dom) if dept and dom else None
        if not domain:
            return dict(status='待確認', reason='尚未選擇部別或領域／科目', items=[])
        if domain['framework'] == 'school-practice':
            out = [self._annot(it, ctx, domain) for it in self.items.values() if it['framework'] == 'service-group']
            return dict(status='已載入', items=out, reason=f'「{domain["label"]}」為本校校訂實習科目，課綱無專屬學習重點；系統依單元與本校教學大綱，自服務群科課綱推薦可對應的學習表現與學習內容（系統推估），請教師確認。')
        if domain['dataStatus'] != 'loaded':
            imp = [it for it in self.items.values() if it.get('imported') and it.get('subject') == domain['subject']
                   and dept in it.get('departments', [dept])]
            if imp:
                return dict(status='教師匯入', reason='此領域使用教師匯入之課綱資料，請確認來源', items=[self._annot(i, ctx, domain) for i in imp])
            label = '幼兒園教保活動課程大綱' if domain['framework'] == 'kindergarten' else '此領域／科目之官方課綱'
            extra = ''
            ol = domain.get('outline')
            if ol:
                extra = f'本校教學大綱（{ol.get("table", "")}）列對應領域：{ol.get("domain") or "未載明"}；課綱核心素養項目：{"、".join(ol.get("coreRefs") or []) or "未載明"}（僅為項目名稱，非領域核心素養代碼）。'
            return dict(status='待確認', reason=f'系統尚未載入{label}之可信資料。請由「匯入課綱資料」匯入官方原文，或於教案中以「待確認」呈現，不以假資料替代。' + extra, items=[])
        out = []
        for it in self.items.values():
            if it['framework'] != domain['framework']: continue
            if it['framework'] == 'special-needs' and it['subject'] != domain['subject']: continue
            if it['framework'] == 'service-group' and not (it['subject'] == domain['subject'] or it['type'] == '核心素養'): continue
            out.append(self._annot(it, ctx, domain))
        return dict(status='已載入', reason='', items=out)

    def _annot(self, it, ctx, domain):
        g = opt.grade_info(ctx.get('dept'), ctx.get('grade')) or {}
        stage_note, default = '', True
        if it['framework'] == 'special-needs':
            subj = it['subject']
            if it['type'] == '核心素養':
                if subj in SP_SA_SUBJECTS:
                    default = True; stage_note = '初階／進階依學生能力選用'
                elif subj in NO_STAGE_SUBJECTS:
                    default = True
                else:
                    default = (it['stage'] == g.get('level'))
                    if not default: stage_note = f'非本學習階段（本年級對應 {g.get("level", "?")}）'
            elif subj in ROMAN_STAGE_SUBJECTS:
                default = (it['stage'] == g.get('stage'))
                if not default: stage_note = f'非本年級對應階段（{g.get("stage", "?")}）；領綱允許依學生能力往前或往後選取'
            elif subj in SP_SA_SUBJECTS:
                stage_note = '初階／進階依學生能力選用'
        return dict(it, defaultStage=default, stageNote=stage_note)

    # ---------- 推薦 ----------
    def score(self, text, query_weights):
        tb = set(bigrams(text))
        hits = [(b, query_weights[b] * self.idf.get(b, 1.0)) for b in tb if b in query_weights]
        return sum(w for _, w in hits), [b for b, _ in sorted(hits, key=lambda x: -x[1])]

    def recommend(self, ctx, unit, ability_texts, limit=12):
        base = self.context_items(ctx)
        if not base['items']:
            return dict(status=base['status'], reason=base['reason'], core=[], performance=[], content=[])
        qw = Counter()
        for b in bigrams(unit or ''): qw[b] += 3.0
        for k, vs in EXPAND.items():
            if k in (unit or ''):
                for v in vs:
                    for b in bigrams(v): qw[b] += 1.5
        for t in ability_texts or []:
            for b in set(bigrams(t)): qw[b] += 0.4
        res = {'核心素養': [], '學習表現': [], '學習內容': []}
        domain = opt.find_domain(ctx.get('dept'), ctx.get('domain')) or {}
        own = set(opt.SV_DEPTS.get(ctx.get('shDept') or '', []))
        for it in base['items']:
            sc, terms = self.score(it['text'] + ' ' + (it.get('dimension') or ''), qw)
            if domain.get('framework') == 'school-practice' and it['type'] != '核心素養' and (not it.get('skillDomain') or it['skillDomain'] in own):
                sc += 3.0
            if it['defaultStage']: sc += 8.0
            elif it['type'] == '核心素養': sc -= 50.0
            reason = []
            if terms: reason.append('與單元／學生能力共同詞：' + '、'.join(_merge_terms(terms)[:5]))
            if it['defaultStage'] and it['type'] != '核心素養': reason.append('符合本年級學習階段')
            if it.get('stageNote'): reason.append(it['stageNote'])
            res[it['type']].append(dict(it, score=round(sc, 2), reason='；'.join(reason) or '同科目項目（系統推估相關性低）'))
        for k in res:
            res[k].sort(key=lambda x: (-x['score'], x['code']))
        # 核心素養只推薦本教育階段（其餘仍可在「展開全部」中選用）
        if any(x['defaultStage'] for x in res['核心素養']):
            res['核心素養'] = [x for x in res['核心素養'] if x['defaultStage']]
        return dict(status=base['status'], reason=base['reason'],
                    core=res['核心素養'][:max(limit, 6)], performance=res['學習表現'][:limit], content=res['學習內容'][:limit],
                    totals={k: len(v) for k, v in res.items()})

    def search(self, q='', framework=None, type_=None, subject=None, limit=60):
        q = (q or '').strip()
        out = []
        for it in self.items.values():
            if framework and it['framework'] != framework: continue
            if type_ and it['type'] != type_: continue
            if subject and it['subject'] != subject: continue
            if q and q not in it['text'] and q not in it['code'] and q not in (it.get('dimension') or ''): continue
            out.append(it)
            if len(out) >= limit: break
        return out

    # ---------- 檢核 ----------
    def validate(self, ctx, selection):
        """切換部別／年級／領域後重新檢核。回傳每個已選項目的狀態：ok / warn（需教師確認）/ error（不適用，需移除）。"""
        domain = opt.find_domain(ctx.get('dept'), ctx.get('domain'))
        g = opt.grade_info(ctx.get('dept'), ctx.get('grade')) or {}
        results = []
        for sel in selection:
            it = self.get(sel.get('itemId'))
            r = dict(itemId=sel.get('itemId'), code=sel.get('code'), level='ok', messages=[])
            if not it:
                r['level'] = 'error'; r['messages'].append('此代碼不在已載入的官方課綱資料中，無法追溯來源')
            elif not domain:
                r['level'] = 'warn'; r['messages'].append('尚未選擇領域／科目')
            else:
                fw = it['framework']; dept = ctx.get('dept')
                if fw == 'special-needs' and dept == 'kg':
                    r['level'] = 'error'; r['messages'].append('特殊需求領域課綱適用國小至高中階段，不適用幼兒園')
                elif fw == 'service-group' and dept != 'sh':
                    r['level'] = 'error'; r['messages'].append('服務群科課綱僅適用技高部')
                elif fw == 'service-group' and it.get('skillDomain') and ctx.get('shDept') and domain['framework'] != 'school-practice' and \
                        it['skillDomain'] not in opt.SV_DEPTS.get(ctx['shDept'], []):
                    r['level'] = 'error'; r['messages'].append(f'「{it["skillDomain"]}」非{ctx["shDept"]}適用技能領域')
                else:
                    same = (it['subject'] == domain['subject']) or (fw == 'service-group' and it['type'] == '核心素養' and domain['framework'] == 'service-group') \
                        or (fw == 'service-group' and domain['framework'] == 'school-practice')
                    if not same:
                        r['level'] = 'warn'; r['messages'].append(f'屬「{it["subject"]}」，與目前領域／科目「{domain["label"]}」不同（跨領域選用需教師確認）')
                    if fw == 'special-needs' and it['type'] != '核心素養' and it['subject'] in ROMAN_STAGE_SUBJECTS and g.get('stage') and it['stage'] != g['stage']:
                        r['level'] = 'warn' if r['level'] == 'ok' else r['level']
                        r['messages'].append(f'階段 {it["stage"]} 與本年級對應階段 {g["stage"]} 不同（領綱允許依能力調整，需教師確認）')
                    if fw == 'special-needs' and it['type'] == '核心素養' and it['stage'] in ('E', 'J', 'U') and g.get('level') and it['stage'] != g['level']:
                        r['level'] = 'warn' if r['level'] == 'ok' else r['level']
                        r['messages'].append(f'核心素養教育階段 {it["stage"]} 與本年級 {g["level"]} 不同')
                    if it and sel.get('officialText') and sel['officialText'] != it['text']:
                        r['level'] = 'error'; r['messages'].append('官方原文欄位被修改；官方原文不可改寫，請改在「教師調整敘述」欄')
            if r['level'] == 'warn' and sel.get('teacherConfirmed'):
                r['level'] = 'ok'; r['messages'].append('（教師已確認）')
            results.append(r)
        return results

def _merge_terms(terms):
    """把重疊的雙字詞合併為較長的詞，便於顯示推薦理由。"""
    out = []
    for t in terms:
        if any(t in o for o in out): continue
        out.append(t)
    return out

REQUIRED_IMPORT = ['code', 'type', 'subject', 'text', 'version', 'sourceTitle']

def parse_import(filename, data: bytes, dept_keys):
    """教師／管理者匯入正式課綱資料（CSV 或 JSON）。必須含代碼、類型、科目、原文、版本、來源名稱；
    匯入資料標示為「教師匯入」，不與系統核對資料混淆。"""
    text = data.decode('utf-8-sig')
    if filename.lower().endswith('.json'):
        rows = json.loads(text)
        if isinstance(rows, dict): rows = rows.get('items', [])
    else:
        rows = list(csv.DictReader(io.StringIO(text)))
    items, errors = [], []
    for i, r in enumerate(rows, 1):
        miss = [k for k in REQUIRED_IMPORT if not str(r.get(k, '')).strip()]
        if miss:
            errors.append(f'第{i}筆缺少欄位：{"、".join(miss)}'); continue
        if r['type'] not in ('核心素養', '學習表現', '學習內容'):
            errors.append(f'第{i}筆類型須為 核心素養／學習表現／學習內容'); continue
        items.append(dict(id='IMP-' + r['code'].strip() + '-' + hashlib.sha1(r['text'].encode()).hexdigest()[:8], code=r['code'].strip(), printedCode=r['code'].strip(),
            framework='imported', type=r['type'], subject=r['subject'].strip(), dimension=r.get('dimension', ''),
            stage=r.get('stage', ''), stageLabel=r.get('stage', ''), text=r['text'].strip(), imported=True,
            departments=[d for d in str(r.get('departments', '')).split('|') if d] or dept_keys,
            source=dict(title=r['sourceTitle'], version=r['version'], url=r.get('sourceUrl') or None,
                        publisher=r.get('publisher', ''), note='教師匯入，未經系統逐字核對')))
    return items, errors

@functools.lru_cache(maxsize=1)
def _store_cached(cur_dir):
    return Store(cur_dir)

def store(app):
    return _store_cached(app.config['CURRICULUM_DIR'])
