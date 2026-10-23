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

def suggest_goals(ctx, groups, analyses, perf_sel, content_sel, curriculum_pending=False):
    if not curriculum_pending and (not perf_sel or not content_sel):
        return dict(error='請先在「確認課綱」步驟勾選至少一項學習表現與一項學習內容，系統才會依所選項目產生目標。')
    unit = ctx.get('unit') or '本單元'
    # 課綱未載入（待確認）時，以單元名稱產生目標，課綱代碼留空，不自行拼湊代碼
    contents = [(_clean(c.get('teacherText') or c['officialText']), c['code']) for c in content_sel][:2] or [(unit, '')]
    pcodes = [p['code'] for p in perf_sel][:3]
    out = {}
    for rank, g in enumerate([g for g in groups if g['studentKeys']]):
        modes = _response_modes(g['studentKeys'], analyses)
        modes_t = '或'.join(modes)
        sup, from_data = _support_for(g['studentKeys'], analyses, rank)
        crit = RANK_CRITERION[min(rank, 3)]
        c_text, c_code = contents[0]
        c2_text, c2_code = contents[-1]
        verb = ('說出' if rank == 0 else '說出或指認') if modes == ['口語'] else '指認或選出'
        goals = [
            dict(domain='認知', situation=f'在教師以圖片、實物或情境提問呈現「{unit}」相關內容時',
                 behavior=f'能以{modes_t}{verb}「{c_text}」的正確做法或內容', support=sup,
                 assessment='口頭評量' if modes == ['口語'] else '指認／配對評量', contentCodes=[x for x in [c_code] if x]),
            dict(domain='情意', situation=f'在「{unit}」的小組活動中',
                 behavior='能參與活動並' + ('以口語表達自己的感受或想法，且能等待輪流、接受同學提醒' if modes == ['口語'] else f'以{modes_t}表達喜歡或不喜歡，並能在活動中等待輪流'),
                 support=sup, assessment='觀察評量', contentCodes=[x for x in [c2_code] if x]),
            dict(domain='技能', situation=f'在實際操作或模擬「{unit}」的情境中',
                 behavior=f'能表現出符合「{c2_text}」的實際行為或操作', support=sup,
                 assessment='實作評量' + ('（協助下）' if rank >= 2 else ''), contentCodes=[x for x in [c2_code] if x]),
        ]
        for go in goals:
            go.update(id=uuid.uuid4().hex[:8], responseModes=modes, criterion=crit, criterionSuggested=True,
                      supportFromData=from_data, performanceCodes=pcodes, groupKey=g['key'])
            go['text'] = f'{go["situation"]}，{go["support"]}，{go["behavior"]}，達成標準：{go["criterion"]}（建議值，請教師確認）。'
        out[g['key']] = goals
    return dict(goals=out, note='目標由所選學習表現／學習內容與各組佐證產生；達成標準為建議值，回應方式依學生資料（口語、指認、手勢、溝通輔具），請逐條修改確認。')

def _round5(x):
    return max(5, int(round(x / 5.0)) * 5)

def suggest_activities(ctx, groups, goals, content_sel):
    minutes = int(ctx.get('minutes') or 45)
    intro = _round5(minutes * 0.2) if minutes >= 25 else max(1, minutes // 5)
    wrap = _round5(minutes * 0.2) if minutes >= 25 else max(1, minutes // 5)
    dev = minutes - intro - wrap
    unit = ctx.get('unit') or '本單元'
    contents = [_clean(c.get('teacherText') or c['officialText']) for c in content_sel] or [unit]
    active = [g for g in groups if g['studentKeys']]
    def per_group(fn):
        return {g['key']: fn(g, i) for i, g in enumerate(active)}
    def gsup(g, i):
        gg = goals.get(g['key']) or []
        return (gg[0]['support'] if gg else RANK_SUPPORT[min(i, 3)]) + ('；回應方式：' + '、'.join(gg[0]['responseModes']) if gg else '')
    def gassess(g, i):
        gg = goals.get(g['key']) or []
        return '、'.join(dict.fromkeys(x['assessment'] for x in gg)) or '觀察評量'
    acts = [
        dict(phase='一、複習及引起動機', minutes=intro,
             content=f'（一）複習與「{unit}」相關的先備經驗，以提問、圖片或實物引起學習動機。\n（二）說明本節課的學習重點與活動規則。',
             resources='圖片或實物、簡報', groupSupport=per_group(gsup), assessment=per_group(lambda g, i: '口頭問答／觀察')),
        dict(phase='二、發展活動', minutes=dev,
             content='（一）教師說明並示範：' + '；'.join(f'「{c}」' for c in contents[:2]) + '。\n（二）分組練習：各組依目標進行練習，教師依各組支持需求提供提示、示範或協助。\n（三）學生輪流實作並互相觀摩，教師即時回饋。',
             resources='教學簡報、實作材料、提示圖卡、增強物', groupSupport=per_group(gsup), assessment=per_group(gassess)),
        dict(phase='三、綜合活動', minutes=wrap,
             content=f'（一）以遊戲或實作檢核「{unit}」學習成果。\n（二）師生共同回顧今日學習內容，給予回饋與鼓勵。',
             resources='計時器、記分板', groupSupport=per_group(gsup), assessment=per_group(gassess)),
    ]
    for a in acts: a['id'] = uuid.uuid4().hex[:8]
    return dict(activities=acts, total=sum(a['minutes'] for a in acts), minutes=minutes)

def check_time(activities, minutes):
    total = sum(int(a.get('minutes') or 0) for a in activities)
    return dict(ok=(total == int(minutes or 0)), total=total, minutes=int(minutes or 0))

def course_structure(basic, domain, activities, focus_subject=None):
    """自動產生「課程架構」：課程 → 本單元 → 本節教學活動；有本校教學大綱者列出單元位置。皆可由教師修改。"""
    course = basic.get('subjectLabel') or (domain or {}).get('label') or '本課程'
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
    acts = [a for a in activities if a.get('phase')]
    for i, a in enumerate(acts):
        first = re.sub(r'^（[一二三四五六七八九十]+）', '', (a.get('content') or '').split('\n')[0]).strip()
        first = re.split(r'[，。；：]', first)[0][:24]
        lines.append(('　　└ ' if i == len(acts) - 1 else '　　├ ') + f'{a["phase"]}（{a.get("minutes", "")}分）' + (f'：{first}' if first else ''))
    return '\n'.join(lines)
