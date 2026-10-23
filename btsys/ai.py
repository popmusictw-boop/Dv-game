"""選用：外部 AI（Anthropic Claude API）輔助擷取。

- 金鑰只存在伺服器環境變數 ANTHROPIC_API_KEY，前端不會取得。
- 必須由管理者開啟（BT_AI_ENABLED=1），且教師每次分析前勾選同意，才會送出。
- 送出前以學生代號取代姓名。
- AI 回傳的每一句「原文引用」都會回到原始資料逐字比對；比對不到者一律剔除並記錄，不採用。
"""
import json, re, urllib.request, uuid
from .analyze import DOMAINS, detect_support, relevance
from .curriculum import bigrams
from .extract import loc_label

API = 'https://api.anthropic.com/v1/messages'

PROMPT = """你是特殊教育教師的助理。以下是一位學生（代號：{code}）的評量／觀察／IEP 資料片段，每段前有編號。
請找出與本單元「{unit}」（領域／科目：{subject}）教學相關的能力描述，面向限於：認知理解、溝通、動作操作、社會互動、情緒行為、生活自理、所需協助。
規則：
1. quote 必須逐字複製資料中的原句（不可改寫、不可合併不同段落）。
2. 不得推測診斷、障礙類別或 IEP 目標；資料沒寫的不要補。
3. relevance 以一句話說明與本單元的關聯（這是推估）。
只輸出 JSON 陣列，每個元素：{{"seg": 段落編號, "quote": "原句", "domains": ["面向"], "relevance": "說明"}}

資料：
{segments}"""

def _norm(s):
    return re.sub(r'[\s　]', '', s)

def analyze_with_ai(cfg, student_code, real_name, files, unit, subject):
    segs, flat = [], []
    for f in files:
        for s in f['extraction']['segments']:
            t = s['text'].replace(real_name, student_code) if real_name else s['text']
            flat.append((f, s, t)); segs.append(f'[{len(flat)}] {t}')
    body = json.dumps(dict(model=cfg['AI_MODEL'], max_tokens=4000,
        messages=[dict(role='user', content=PROMPT.format(code=student_code, unit=unit, subject=subject, segments='\n'.join(segs)))])).encode()
    req = urllib.request.Request(API, data=body, headers={
        'x-api-key': cfg['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read())
    text = ''.join(c.get('text', '') for c in resp.get('content', []))
    m = re.search(r'\[.*\]', text, re.S)
    items = json.loads(m.group(0)) if m else []
    unit_terms = set(bigrams(unit))
    out, rejected = [], []
    for it in items:
        try:
            f, s, t = flat[int(it['seg']) - 1]
        except Exception:
            rejected.append(dict(reason='段落編號無效', quote=it.get('quote', ''))); continue
        q = (it.get('quote') or '').replace(student_code, real_name) if real_name else it.get('quote') or ''
        if not q or _norm(q) not in _norm(s['text']):
            rejected.append(dict(reason='引用句無法在原始資料中逐字找到，已排除', quote=q)); continue
        doms = [d for d in it.get('domains', []) if d in DOMAINS or d == '所需協助'] or ['所需協助']
        sup = detect_support(q)
        out.append(dict(id=uuid.uuid4().hex[:10], domains=doms, quote=q, status='原文事實',
            evidence=dict(fileId=f['fileId'], filename=f['filename'], loc=s['loc'], label=loc_label(f['filename'], s['loc'])),
            support=dict(levels=sup, status='原文事實' if sup else '資料不足'),
            relevance=dict(text=(it.get('relevance') or '') + '（AI 推估）', status='系統推估') if it.get('relevance') else relevance(q, unit_terms),
            teacherText='', teacherNote='', confirmed=False, excluded=False, source='AI'))
    return out, rejected
