"""先備能力分析（本機規則式，不送出任何資料）。

輸出的每一筆能力描述都是原始資料中的「原文句子」（狀態：原文事實），並附檔名與頁碼／段落；
「與本單元的關聯」由系統依共同詞推估（狀態：系統推估）；
在資料中找不到的能力面向一律列為「資料不足」，請教師補充，系統不自行補寫。
性別、障礙類別只有在資料中出現明確欄位標記（例如「性別：女」）時才填入，否則留白。
"""
import re, uuid
from .extract import loc_label
from .curriculum import bigrams

DOMAINS = {
    '認知理解': ['理解', '認知', '識字', '閱讀', '數學', '數字', '數數', '記憶', '注意力', '專注', '概念', '分類', '配對', '辨識', '辨認', '判斷', '書寫', '仿寫', '計算', '指令', '意涵', '學習'],
    '溝通': ['口語', '語言', '表達', '溝通', '仿說', '句子', '詞彙', '手勢', '手語', '圖卡', 'AAC', '溝通板', '溝通輔具', '回應', '說出', '敘述', '氣音', '聽懂', '對話'],
    '動作操作': ['大動作', '精細', '手部', '抓握', '操作', '跑', '蹲', '步態', '平衡', '肢體', '動作', '握筆', '剪', '移位', '輪椅', '行走', '姿勢', '坐'],
    '社會互動': ['同學', '同儕', '人際', '互動', '合作', '輪流', '分享', '遊戲', '團體', '稱讚', '社交', '打招呼', '他人', '朋友'],
    '情緒行為': ['情緒', '挫折', '容忍', '生氣', '哭', '尖叫', '固著', '過動', '自我刺激', '攻擊', '敏感', '焦慮', '調適', '行為', '榮譽感', '喜愛', '厭惡', '壓力'],
    '生活自理': ['自理', '如廁', '進食', '用餐', '穿脫', '衣物', '盥洗', '刷牙', '洗手', '整理', '清潔', '收拾', '飲食', '儀容'],
}
SUPPORT_PATTERNS = [
    ('完全肢體協助', r'完全肢體(協助|引導)'),
    ('部分肢體協助', r'部分?肢體(協助|引導)|一對一.{0,6}肢體'),
    ('示範', r'示範|仿做'),
    ('口語提示', r'口語(提示|引導|提醒)|老師(引導|提醒)|須提醒|需提醒'),
    ('視覺提示', r'視覺(提示|支持)|圖卡|圖片提示|工作分析圖'),
    ('一對一', r'一對一'),
    ('溝通輔具', r'溝通(輔具|板)|AAC|語音輸出'),
    ('獨立完成', r'獨立(完成)?|可自行|能自行|主動'),
]
LABEL_GENDER = re.compile(r'性\s*別\s*[:：]\s*(男|女)')
LABEL_DISAB = re.compile(r'(?:障礙類別|障礙別|鑑定類別|障別|特教類別)\s*[:：]\s*([一-鿿、（）()]{2,20})')
LABEL_NAME = re.compile(r'(?:姓\s*名|學生姓名)\s*[:：]\s*([一-鿿]{2,4})')

def split_sentences(text):
    parts = re.split(r'(?<=[。；;！？!?])|\n', text)
    return [p.strip() for p in parts if p and len(p.strip()) >= 4]

def detect_support(sentence):
    return [name for name, pat in SUPPORT_PATTERNS if re.search(pat, sentence)]

def relevance(sentence, unit_terms):
    common = sorted(set(bigrams(sentence)) & unit_terms)
    if common:
        return dict(text='與本單元／所選課綱有共同詞：' + '、'.join(common[:6]) + '，可能相關，請教師判斷。', status='系統推估')
    return dict(text='未找到與本單元的明顯共同詞，關聯性請教師判斷。', status='系統推估')

def analyze_student(student_key, files, unit_text=''):
    """files: [dict(fileId, filename, extraction)]；回傳此學生的分析結果（全部待教師確認）。"""
    unit_terms = set(bigrams(unit_text))
    basic = dict(gender=dict(value='', status='資料不足', evidence=[]),
                 disability=dict(value='', status='資料不足', evidence=[]), nameCandidates=[])
    abilities, seen = [], set()
    for f in files:
        for seg in f['extraction']['segments']:
            label = loc_label(f['filename'], seg['loc'])
            text = seg['text']
            for rx, field in ((LABEL_GENDER, 'gender'), (LABEL_DISAB, 'disability')):
                m = rx.search(text)
                if m:
                    v = m.group(1).strip()
                    b = basic[field]
                    b['evidence'].append(dict(fileId=f['fileId'], label=label, quote=m.group(0)))
                    if b['value'] and b['value'] != v:
                        b['status'] = '資料矛盾'; b['value'] = ''
                    elif b['status'] != '資料矛盾':
                        b['value'] = v; b['status'] = '原文事實'
            m = LABEL_NAME.search(text)
            if m and m.group(1) not in basic['nameCandidates']:
                basic['nameCandidates'].append(m.group(1))
            for k, sent in enumerate(split_sentences(text), 1):
                doms = [d for d, kws in DOMAINS.items() if any(kw in sent for kw in kws)]
                sup = detect_support(sent)
                if not doms and sup: doms = ['所需協助']
                if not doms: continue
                key = re.sub(r'\s', '', sent)
                if key in seen: continue
                seen.add(key)
                abilities.append(dict(
                    id=uuid.uuid4().hex[:10], domains=doms, quote=sent, status='原文事實',
                    evidence=dict(fileId=f['fileId'], filename=f['filename'], loc=dict(seg['loc'], sentence=k), label=f'{label} 第{k}句'),
                    lowConfidence=(seg.get('conf') is not None and seg['conf'] < 60),
                    support=dict(levels=sup, status='原文事實' if sup else '資料不足'),
                    relevance=relevance(sent, unit_terms),
                    teacherText='', teacherNote='', confirmed=False, excluded=False))
    covered = {d for a in abilities for d in a['domains']}
    insufficient = [dict(domain=d, status='資料不足', note=f'上傳資料中未找到「{d}」相關描述，請教師補充或標記不適用。', teacherText='', confirmed=False)
                    for d in list(DOMAINS) + ['所需協助'] if d not in covered and not (d == '所需協助' and any(a['support']['levels'] for a in abilities))]
    for b in (basic['gender'], basic['disability']):
        if b['status'] == '資料矛盾':
            b['note'] = '不同資料記載不一致，請教師確認。'
    return dict(studentKey=student_key, mode='rule', basic=basic, abilities=abilities, insufficient=insufficient)

def support_profile(analysis):
    """由已確認（或未排除）的佐證，估計所需支持程度（0＝最少，越高越多），供分組建議。屬系統推估。"""
    w = {'獨立完成': -1.0, '口語提示': 1.0, '視覺提示': 1.0, '示範': 1.5, '一對一': 2.0, '溝通輔具': 1.5, '部分肢體協助': 2.5, '完全肢體協助': 3.5}
    neg = [r'無口語', r'無法', r'不具備', r'尚無', r'難以', r'較緩慢', r'須', r'需']
    score, n, reasons = 0.0, 0, []
    for a in analysis.get('abilities', []):
        if a.get('excluded'): continue
        text = a.get('teacherText') or a['quote']
        levels = detect_support(text)
        s = sum(w.get(l, 0) for l in levels) + 0.5 * sum(1 for p in neg if re.search(p, text))
        if levels or s:
            n += 1; score += s
            if levels: reasons.append(f'{"、".join(levels)}（{a["evidence"]["label"]}）')
    return dict(score=round(score / max(n, 1), 2), evidenceCount=n, reasons=reasons[:6])
