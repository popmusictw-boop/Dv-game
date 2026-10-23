"""能力分組、學習目標與教學活動的「建議草稿」。

全部輸出皆為可編輯的建議：
- 分組依學生在本單元相關佐證中呈現的支持需求（提示、示範、肢體協助等）推估，不依障礙類別或年級決定。
- 目標只依教師已勾選的學習表現／學習內容產生，不為湊數產生無關目標；資料不足時的達成標準標示為「建議值」。
- 活動時間由每節分鐘數分配，合計必等於設定課時。
"""
import re, uuid
from .analyze import support_profile, detect_support

RANK_SUPPORT = ['獨立或在一次口語提示下', '在口語或視覺提示下', '在示範或部分肢體協助下', '在一對一肢體協助下']
RANK_CRITERION = ['5次中至少4次正確（80%）', '5次中至少3次正確（60%）', '在協助下5次中至少3次完成', '在協助下5次中至少2次完成']
NONVERBAL = re.compile(r'無口語|無法以口語|氣音|仿說|較無法以口語|難以引導其口語|配對選擇')

def suggest_groups(students, analyses, names=None):
    names = names or ['A組', 'B組', 'C組']
    prof = []
    for s in students:
        a = analyses.get(s['key'])
        p = support_profile(a) if a else dict(score=None, evidenceCount=0, reasons=[])
        prof.append((s, p))
    known = sorted([x for x in prof if x[1]['evidenceCount'] > 0], key=lambda x: x[1]['score'])
    unknown = [x for x in prof if x[1]['evidenceCount'] == 0]
    n = min(len(names), max(1, len(known)))
    groups = [dict(key=chr(65 + i), name=names[i], studentKeys=[], rationale=[]) for i in range(len(names))]
    for idx, (s, p) in enumerate(known):
        gi = min(n - 1, idx * n // max(len(known), 1))
        groups[gi]['studentKeys'].append(s['key'])
        groups[gi]['rationale'].append(dict(studentKey=s['key'], score=p['score'], reasons=p['reasons'], status='系統推估'))
    pending = [dict(studentKey=s['key'], note='佐證不足，無法推估支持程度，請教師手動分組') for s, _ in unknown]
    return dict(groups=groups, unassigned=pending,
                note='分組依「本單元相關能力佐證中的支持需求」推估（系統推估），未使用障礙類別或年級；請教師調整組數、組名與學生歸組。')

def _response_modes(group_students, analyses):
    nonverbal = False
    for k in group_students:
        for a in (analyses.get(k) or {}).get('abilities', []):
            if not a.get('excluded') and NONVERBAL.search(a.get('teacherText') or a['quote']): nonverbal = True
    return (['指認', '手勢', '溝通輔具（圖卡／溝通板）'] if nonverbal else ['口語'])

def _support_for(group_students, analyses, rank):
    levels = []
    for k in group_students:
        for a in (analyses.get(k) or {}).get('abilities', []):
            if not a.get('excluded'): levels += detect_support(a.get('teacherText') or a['quote'])
    order = ['完全肢體協助', '部分肢體協助', '示範', '視覺提示', '口語提示', '獨立完成']
    for lv in order:
        if lv in levels:
            return {'完全肢體協助': '在一對一肢體協助下', '部分肢體協助': '在部分肢體協助下', '示範': '在教師示範後',
                    '視覺提示': '在視覺提示下', '口語提示': '在口語提示下', '獨立完成': '獨立'}[lv], True
    return RANK_SUPPORT[min(rank, 3)], False

def _clean(t):
    return re.sub(r'[。．]$', '', t.strip())

def _sup_phrase(sup):
    """協助程度轉為目標前置語；獨立者不加。"""
    if not sup or sup.startswith('獨立'): return ''
    return sup if sup.startswith('在') else f'在{sup}下'

def suggest_goals(ctx, groups, analyses, perf_sel, content_sel, curriculum_pending=False):
    """依本校教案寫法：條件＋可觀察行為的短句；達成標準另存於欄位（建議值），不寫入目標句。"""
    if not curriculum_pending and (not perf_sel or not content_sel):
        return dict(error='請先在「確認課綱」步驟勾選至少一項學習表現與一項學習內容，系統才會依所選項目產生目標。')
    unit = ctx.get('unit') or '本單元'
    contents = [(_clean(c.get('teacherText') or c['officialText']), c['code']) for c in content_sel][:2] or [(unit, '')]
    pcodes = [p['code'] for p in perf_sel][:3]
    c_codes = [c for _, c in contents if c]
    out = {}
    for rank, g in enumerate([g for g in groups if g['studentKeys']]):
        modes = _response_modes(g['studentKeys'], analyses)
        verbal = modes == ['口語']
        sup, from_data = _support_for(g['studentKeys'], analyses, rank)
        pre = _sup_phrase(sup)
        pre_c = (pre + '，') if pre else ''
        if rank == 0 and verbal:
            cog = dict(situation=f'提供「{unit}」相關圖片或提問時', support='', behavior=f'能說出「{unit}」的步驟或重點', assessment='口說')
        elif verbal:
            cog = dict(situation=f'提供「{unit}」相關圖片或提問時', support=pre, behavior=f'能說出或指認「{unit}」的步驟或重點', assessment='口說／指認圖片')
        else:
            cog = dict(situation=f'提供「{unit}」步驟圖卡時', support=pre, behavior=f'能指認「{unit}」的步驟或重點', assessment='指認圖片')
        aff = dict(situation='', support='', behavior=f'能以積極、負責任的態度參與「{unit}」課程活動', assessment='觀察')
        if rank == 0 and not pre:
            skl = dict(situation='', support='', behavior=f'能依指令完成「{unit}」的實作', assessment='獨立操作')
        else:
            skl = dict(situation='', support=pre, behavior=f'能完成「{unit}」的實作', assessment='肢體協助／工具輔助操作' if '肢體' in pre else '提示下操作')
        goals = []
        for dom, gdef in (('認知', cog), ('情意', aff), ('技能', skl)):
            go = dict(domain=dom, **gdef)
            go.update(id=uuid.uuid4().hex[:8], responseModes=modes, criterion=RANK_CRITERION[min(rank, 3)], criterionSuggested=True,
                      supportFromData=from_data, performanceCodes=pcodes, contentCodes=c_codes, groupKey=g['key'])
            go['text'] = '，'.join(x for x in (go['situation'], go['support'], go['behavior']) if x) + '。'
            goals.append(go)
        out[g['key']] = goals
    return dict(goals=out, note='目標依本校教案寫法產生（條件＋可觀察行為）；達成標準為建議值，存於各目標欄位，可再修改。')

def _round5(x):
    return max(5, int(round(x / 5.0)) * 5)

def _assess_code(goals, domain, fallback):
    for x in goals or []:
        if x['domain'] == domain: return x.get('assessment') or fallback
    return fallback

def suggest_activities(ctx, groups, goals, content_sel):
    """依本校教案寫法：一、複習及引起動機／二、發展活動（說明與示範、分組練習）／三、綜合活動，各組分列 A組、B組…。"""
    minutes = int(ctx.get('minutes') or 45)
    intro = _round5(minutes * 0.15) if minutes >= 25 else max(1, minutes // 5)
    wrap = _round5(minutes * 0.2) if minutes >= 25 else max(1, minutes // 5)
    dev = minutes - intro - wrap
    demo = max(1, _round5(dev * 0.4)) if dev >= 15 else max(1, dev // 2)
    prac = dev - demo
    unit = ctx.get('unit') or '本單元'
    contents = [_clean(c.get('teacherText') or c['officialText']) for c in content_sel][:2]
    active = [g for g in groups if g['studentKeys']] or [dict(key='A', name='A組', studentKeys=[])]
    def gl(g):
        return goals.get(g['key']) or []
    def line(i, g, fn):
        return f'{i}{g["key"]}組：{fn(g)}'
    def beh(g, dom):
        x = next((x for x in gl(g) if x['domain'] == dom), None)
        return (('，'.join(y for y in (x['support'], x['behavior']) if y)) if x else '').replace('「' + unit + '」', unit)
    sub = lambda fn, ind='       ', mark=('(A)', '(B)', '(C)', '(D)'): '\n'.join(f'{ind}{mark[i]} {g["key"]}組：{fn(g)}' for i, g in enumerate(active))
    num = lambda fn, ind='    ', mark=('(1)', '(2)', '(3)', '(4)'): '\n'.join(f'{ind}{mark[i]}{g["key"]}組：{fn(g)}' for i, g in enumerate(active))
    ass = lambda dom, fb: {g['key']: _assess_code(gl(g), dom, fb if i == 0 else '指認圖片' if dom == '認知' else '協助操作') for i, g in enumerate(active)}
    focus = '、'.join(f'「{c}」' for c in contents) if contents else f'「{unit}」'
    acts = [
        dict(phase='一、複習及引起動機', minutes=intro,
             content=f'  (一) 複習：回顧與「{unit}」相關的先備經驗\n  (二) 引起動機：\n     1.圖片分享：請學生分享與「{unit}」相關的圖片或生活經驗\n     2.說明活動：說明本節課將學習「{unit}」',
             resources='電腦及投影片、圖片', assessment={g['key']: ('口說' if i == 0 else '指認圖片') for i, g in enumerate(active)}),
        dict(phase='二、發展活動', minutes=demo,
             content=f'  (一) 說明與示範\n     1.說明：教師說明「{unit}」的步驟與重點\n     2.示範：教師逐步示範，並以步驟圖卡提示\n     3.評量\n' + sub(lambda g: beh(g, '認知') or '能說出或指認步驟'),
             resources='教學步驟圖卡、實作材料', assessment=ass('認知', '口說')),
        dict(phase='', minutes=prac,
             content='  (二) 分組練習\n     1.說明：各組依目標進行練習，完成者可獲得增強（如集點印章）\n     2.練習開始\n' + num(lambda g: beh(g, '技能') or '完成實作', '       ') + '\n     3.複習步驟與重點',
             resources='實作材料、增強物', assessment=ass('技能', '獨立操作')),
        dict(phase='三、綜合活動', minutes=wrap,
             content=f'  1.成果檢核：\n' + num(lambda g: beh(g, '技能') or '完成實作') + f'\n  2.總結及預告下節活動：複習「{unit}」重點，並說明下節課內容',
             resources='實作材料、增強物', assessment=ass('技能', '獨立操作')),
    ]
    for a in acts: a['id'] = uuid.uuid4().hex[:8]; a['groupSupport'] = {}
    return dict(activities=acts, total=sum(a['minutes'] for a in acts), minutes=minutes)

def check_time(activities, minutes):
    total = sum(int(a.get('minutes') or 0) for a in activities)
    return dict(ok=(total == int(minutes or 0)), total=total, minutes=int(minutes or 0))

def course_structure(basic, domain, activities, focus_subject=None):
    """自動產生「課程架構」：課程 → 本單元 → 本節教學活動；有本校教學大綱者列出單元位置。皆可由教師修改。"""
    course = (basic.get('customDomain') if (domain or {}).get('key') == 'custom' else (domain or {}).get('label')) or basic.get('subjectLabel') or '本課程'
    group = re.split(r'[（(]', (domain or {}).get('group') or '')[0].strip()
    unit = basic.get('unit') or '本單元'
    lines = [course + (f'（{group}）' if group and group != '其他' else '')]
    ol = (domain or {}).get('outline') or {}
    units = ol.get('units') or []
    idx = next((i for i, u in enumerate(units) if u.get('title') and (u['title'] in unit or unit in u['title'])), None)
    if units:
        pos = f'第{units[idx]["no"]}單元／共{len(units)}單元' if idx is not None else f'本校教學大綱共{len(units)}單元'
        lines.append(f'├ 本校教學大綱：{pos}')
    if focus_subject and focus_subject != course:
        lines.append(f'├ 對應課綱科目：{focus_subject}')
    tp, pn = basic.get('totalPeriods'), basic.get('periodNo')
    lines.append(f'└ 單元：{unit}' + (f'（共{tp}節，本節第{pn}節）' if tp and pn else ''))
    if idx is not None and units[idx].get('items'):
        lines.append('　　├ 單元內容：' + '、'.join(units[idx]['items'])[:60])
    phases = []
    for a in activities:
        subs = re.findall(r'^\s*[\(（][一二三四五六七八九十]+[\)）]\s*([^：:\n]+)', a.get('content') or '', re.M)
        if a.get('phase') or not phases:
            phases.append([a.get('phase') or '', int(a.get('minutes') or 0), subs])
        else:
            phases[-1][1] += int(a.get('minutes') or 0); phases[-1][2] += subs
    for i, (ph, mins, subs) in enumerate(phases):
        subs = [x.strip() for x in subs if x.strip()][:4]
        lines.append(('　　└ ' if i == len(phases) - 1 else '　　├ ') + f'{ph}（{mins}分）' + (('：' + '、'.join(subs)) if subs else ''))
    return '\n'.join(lines)
