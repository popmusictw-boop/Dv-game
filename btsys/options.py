"""部別、年級、領域／科目之聯動選單。

只列出各部別適用的項目；課綱資料是否已載入以 dataStatus 標示：
  loaded  ：已有逐字擷取的官方課綱資料
  pending ：系統尚未取得可信官方資料，課綱欄位一律標示「待確認」，可由教師匯入
"""
import json, pathlib

SN_SUBJECTS = ['生活管理', '社會技巧', '學習策略', '職業教育', '溝通訓練', '點字', '定向行動', '功能性動作訓練', '輔助科技應用']

KG_DOMAINS = ['身體動作與健康', '認知', '語文', '社會', '情緒', '美感']  # 幼兒園教保活動課程大綱六大領域

ELEM_GENERAL = {
    # 領域：適用年級
    '國語文': range(1, 7), '本土語文／臺灣手語': range(1, 7), '新住民語文': range(1, 7), '英語文': range(3, 7),
    '數學': range(1, 7), '生活課程': range(1, 3), '社會': range(3, 7), '自然科學': range(3, 7),
    '藝術': range(3, 7), '綜合活動': range(3, 7), '健康與體育': range(1, 7),
}
JH_GENERAL = ['國語文', '本土語文／臺灣手語', '新住民語文', '英語文', '數學', '社會', '自然科學', '藝術', '綜合活動', '科技', '健康與體育']
# 服務群課綱「課程架構表」所列一般科目
SH_GENERAL = ['國語文', '本土語文／臺灣手語', '英語文', '數學', '社會', '自然科學', '藝術', '綜合活動暨科技', '健康與體育', '全民國防教育']

SV_PRO = ['服務導論', '衛生與安全概論', '事務機器與電腦應用概論']
SV_PRACTICE = ['基礎清潔實務', '基礎清潔實作', '職場清潔實作', '顧客服務實務', '顧客服務實作']
SV_SKILL = {
    '車輛整理技能領域': ['車輛外部清理實作', '車輛內裝清理實作', '車輛美容實作'],
    '門市技能領域': ['基礎設備實作', '收銀台實作', '門市作業實作'],
    '物品整理技能領域': ['物品整理實作', '倉儲實作', '配送實作'],
    '農園藝技能領域': ['農園藝種植維護實作', '園藝景觀維護管理實作', '農園管理維護實作'],
    '產品加工技能領域': ['基礎蔬果加工實作', '基礎雜糧作物加工實作', '基礎香草加工實作'],
    '裝配技能領域': ['組裝技能實作', '代工品組裝實作', '商品包裝實作'],
    '生活照護技能領域': ['生活保健實作', '居家照顧實作', '飲食調理實作'],
    '家務處理技能領域': ['生活用品整理實作', '家電使用與維護實作', '家事處理實作'],
    '餐飲製作技能領域': ['食材處理實作', '基礎速食實作', '飲料調製實作'],
    '旅館房務技能領域': ['客房整理實作', '客房清潔與維護實作', '客房服務實作'],
    '按摩技能領域': ['按摩基礎手法實作', '局部按摩實作'],
    '紓壓保健技能領域': ['基礎精油物品實作', '基礎精油按摩手法實作', '足部精油按摩實作'],
}
# 服務群課綱「本群各科技能領域適用對照表」
SV_DEPTS = {
    '汽車美容服務科': ['車輛整理技能領域', '門市技能領域'],
    '門市服務科': ['門市技能領域', '物品整理技能領域'],
    '農園藝整理服務科': ['農園藝技能領域', '產品加工技能領域'],
    '包裝服務科': ['裝配技能領域', '物品整理技能領域'],
    '居家生活服務科': ['生活照護技能領域', '家務處理技能領域'],
    '餐飲服務科': ['餐飲製作技能領域', '家務處理技能領域'],
    '旅館服務科': ['旅館房務技能領域', '家務處理技能領域'],
    '保健按摩服務科': ['按摩技能領域', '紓壓保健技能領域'],
    '綜合職能科': list(SV_SKILL.keys()),  # 學校自行選取2個技能領域
}

def _d(key, label, group, framework, subject=None, status='pending', **kw):
    return dict(key=key, label=label, group=group, framework=framework, subject=subject or label, dataStatus=status, **kw)

_SCHOOL_DIR = pathlib.Path(__file__).resolve().parent.parent / 'data' / 'school'
SCHOOL_SH = json.load(open(_SCHOOL_DIR / 'tpmr_115_service.json', encoding='utf-8'))
SCHOOL_EJ = json.load(open(_SCHOOL_DIR / 'tpmr_113_elem_jh.json', encoding='utf-8'))
SCHOOL_SOURCES = [dict(SCHOOL_SH['source'], scope='技高部科別與科目'), dict(SCHOOL_EJ['source'], scope='國小部、國中部領域與特殊需求科目')]

def _ej_domains(level, prefix):
    data = SCHOOL_EJ[level]
    # 國小部混齡：所有領域兩班皆可選（不依年級篩選）；國中部依年級篩選
    gk = lambda gs: None  # 不再依年級篩選（教學者自填班級）
    out = [_d('gen:' + x['name'], x['name'] + (f'（{x["note"]}）' if x.get('note') and x['name'] == '語文' else ''), '部定課程－領域學習', 'general', x['name'], grades=gk(x['grades'])) for x in data['domains']]
    offered = {x['name'] for x in data['specialNeeds']}
    out += [_d('sn:' + x['name'], x['name'], '校訂課程－特殊需求領域（本校課程架構）', 'special-needs', x['name'], 'loaded', grades=gk(x['grades'])) for x in data['specialNeeds']]
    out += [_d('sn:' + s, s, '其他特殊需求科目（本校架構表未列，依學生需求選用）', 'special-needs', s, 'loaded') for s in SN_SUBJECTS if s not in offered]
    for x in data.get('other', []):
        out.append(_d('other:' + x['name'], x['name'], '校訂課程－其他', 'custom', x['name'], grades=gk(x['grades'])))
    return out + [_d('custom', '其他／自訂', '其他', 'custom')]

def _sh_domains():
    seen = {}
    for dept, info in SCHOOL_SH['departments'].items():
        for c in info['courses']:
            fw = c['framework']
            prefix = {'general': 'gen:', 'service-group': 'sv:', 'special-needs': 'sn:'}.get(fw, 'sch:')
            key = prefix + c['name']
            if key in seen:
                seen[key]['depts'].append(dept); continue
            status = 'loaded' if fw in ('service-group', 'special-needs', 'school-practice') else 'pending'
            dom = _d(key, c['name'], c['group'], fw, c['subject'], status, depts=[dept])
            if c.get('skillDomain'): dom['skillDomain'] = c['skillDomain']
            if c.get('outline'): dom['outline'] = c['outline']
            seen[key] = dom
    order = ['部定必修－一般科目', '部定必修－專業科目', '部定必修－實習科目', '部定必修－生活照護技能領域', '部定必修－家務處理技能領域',
             '部定必修－餐飲製作技能領域', '校訂必修－一般科目', '校訂必修－實習科目', '校訂選修－一般科目', '校訂選修－實習科目（同群跨科）']
    doms = sorted(seen.values(), key=lambda x: order.index(x['group']) if x['group'] in order else 99)
    offered = {d['subject'] for d in doms if d['framework'] == 'special-needs'}
    doms += [_d('sn:' + x, x, '其他特殊需求科目（依學生需求選用）', 'special-needs', x, 'loaded') for x in SN_SUBJECTS if x not in offered]
    return doms + [_d('custom', '其他／自訂', '其他', 'custom')]

def build_options():
    deps = []
    deps.append(dict(key='kg', label='幼兒園', grades=[
        dict(key='kg-2', label='幼幼班（2-3歲）', stage='kg'), dict(key='kg-3', label='小班（3-4歲）', stage='kg'),
        dict(key='kg-4', label='中班（4-5歲）', stage='kg'), dict(key='kg-5', label='大班（5-6歲）', stage='kg')],
        domains=[_d('kg:' + x, x, '幼兒園教保活動課程大綱領域', 'kindergarten') for x in KG_DOMAINS]
                + [_d('custom', '其他／自訂', '其他', 'custom')]))
    # 本校國小部為混齡編班，分小1、小2兩班；不對應單一年級，學習階段依學生能力選用（Ⅰ～Ⅲ）
    eg = [dict(key=f'e-c{n}', label=f'小{n}', stage=None, level='E', mixed=True) for n in (1, 2)]
    deps.append(dict(key='elem', label='國小部', grades=eg, domains=_ej_domains('elem', 'e')))
    jg = [dict(key=f'j{g}', label=f'{"七八九"[g-7]}年級', stage='Ⅳ', level='J', grade=g) for g in (7, 8, 9)]
    deps.append(dict(key='jh', label='國中部', grades=jg, domains=_ej_domains('jh', 'j')))
    sg = [dict(key=f's{g}', label=f'高{"一二三"[g-10]}', stage='Ⅴ', level='U', grade=g) for g in (10, 11, 12)]
    deps.append(dict(key='sh', label='技高部', grades=sg,
        clusters=[dict(key='服務群', label='服務群', departments=[dict(key=k, label=k, skillDomains=v['skillDomains']) for k, v in SCHOOL_SH['departments'].items()])],
        domains=_sh_domains()))
    return dict(departments=deps, schoolSources=SCHOOL_SOURCES)

OPTIONS = build_options()

def find_dept(key):
    return next((d for d in OPTIONS['departments'] if d['key'] == key), None)

def domains_for(dept_key, grade_key=None, sh_dept=None):
    """回傳某部別（＋年級、技高科別）適用的領域／科目；依本校課程架構與科別篩選。"""
    d = find_dept(dept_key)
    if not d: return []
    out = []
    for dom in d['domains']:
        if dom.get('grades') and grade_key and grade_key not in dom['grades']:
            continue
        if dept_key == 'sh' and sh_dept and dom.get('depts') and sh_dept not in dom['depts']:
            continue
        out.append(dom)
    return out

def find_domain(dept_key, domain_key):
    d = find_dept(dept_key)
    return next((x for x in (d or {}).get('domains', []) if x['key'] == domain_key), None)

# 介面已改為由教學者自填「班級」，不再選年級；課綱學習階段依部別預設（國小部混齡依能力選用）
DEPT_STAGE = {'kg': {}, 'elem': dict(stage=None, level='E', mixed=True), 'jh': dict(stage='Ⅳ', level='J'), 'sh': dict(stage='Ⅴ', level='U')}

def grade_info(dept_key, grade_key):
    d = find_dept(dept_key)
    g = next((x for x in (d or {}).get('grades', []) if x['key'] == grade_key), None)
    return g or (DEPT_STAGE.get(dept_key) if d else None)
