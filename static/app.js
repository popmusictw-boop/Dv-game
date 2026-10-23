/* 北特教案生成系統 前端（無外部套件；所有使用者內容以 textContent 輸出，避免注入） */
'use strict';

// ---------- 小工具 ----------
const $ = (s, r = document) => r.querySelector(s);
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'value') el.value = v;
    else if (k === 'checked') el.checked = !!v;
    else if (k === 'text') el.textContent = v;
    else if (k === 'style') el.style.cssText = v;  // 以 CSSOM 設定，符合 CSP
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
const badge = (text, kind) => h('span', { class: 'badge ' + ({ '原文事實': 'b-fact', '系統推估': 'b-guess', '資料不足': 'b-missing', '資料矛盾': 'b-missing', '教師確認': 'b-teacher', '待確認': 'b-pending', '建議值': 'b-pending', '已載入': 'b-fact', '教師匯入': 'b-teacher' }[text] || kind || 'b-neutral') }, text);
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('show'), 3200); }
async function api(method, url, body, form) {
  const opt = { method, headers: { 'X-BT-Requested': '1' }, credentials: 'same-origin' };
  if (form) opt.body = body; else if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch(url, opt);
  if (r.status === 401 && url !== '/api/login') { showLogin(); throw new Error('請先登入'); }
  const ct = r.headers.get('content-type') || '';
  const data = ct.includes('json') ? await r.json() : null;
  if (!r.ok) throw new Error((data && data.error) || `發生錯誤（${r.status}）`);
  return data;
}
function modal(content, wide) {
  const d = $('#modal'); const b = $('#modalBody'); b.replaceChildren(content);
  d.style.maxWidth = wide ? 'min(960px,96vw)' : ''; if (!d.open) d.showModal(); return d;
}
const closeModal = () => $('#modal').close();
const rocDate = (iso) => { if (!iso) return ''; const [y, m, d] = iso.split('-').map(Number); return `${y - 1911}年${m}月${d}日`; };
const uid = () => Math.random().toString(36).slice(2, 10);

// ---------- 狀態 ----------
const S = { user: null, options: null, privacy: null, draftId: null, plan: null, files: [], step: 0, rec: null, ctxItems: null, validation: [] };
const STEPS = ['基本資料', '上傳資料', '確認先備能力', '確認課綱', '分組與目標', '生成教案', '編輯預覽', '匯出'];

let saveTimer = null;
function markDirty() {
  $('#saveState').textContent = '尚未儲存…';
  clearTimeout(saveTimer); saveTimer = setTimeout(saveNow, 1200);
}
async function saveNow() {
  clearTimeout(saveTimer);
  if (!S.draftId) return;
  try { await api('PUT', `/api/drafts/${S.draftId}`, S.plan); $('#saveState').textContent = '已自動儲存 ' + new Date().toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' }); }
  catch (e) { $('#saveState').textContent = '儲存失敗'; toast(e.message); }
}

// ---------- 登入與首頁 ----------
function showView(id) { for (const v of ['loginView', 'homeView', 'editorView']) $('#' + v).hidden = v !== id; $('#topActions').hidden = id === 'loginView'; }
function showLogin() { showView('loginView'); }
$('#loginForm').addEventListener('submit', async (e) => {
  e.preventDefault(); const f = new FormData(e.target);
  try { const r = await api('POST', '/api/login', { username: f.get('username'), password: f.get('password') }); S.user = r.user; e.target.reset(); await boot(); }
  catch (err) { $('#loginErr').textContent = err.message; }
});
$('#btnLogout').onclick = async () => { await saveNow(); await api('POST', '/api/logout'); location.reload(); };
$('#btnDrafts').onclick = async () => { await saveNow(); S.draftId = null; await showHome(); };
$('#btnNew').onclick = async () => {
  const r = await api('POST', '/api/drafts', { basic: { minutes: 45, totalPeriods: 1, periodNo: 1, teacher: S.user.name, date: new Date().toISOString().slice(0, 10) } });
  await openDraft(r.id);
};

async function boot() {
  try { const me = await api('GET', '/api/me'); S.user = me.user; } catch { return showLogin(); }
  [S.options, S.privacy] = await Promise.all([api('GET', '/api/options'), api('GET', '/api/privacy')]);
  await showHome();
  if (S.user.mustChange) passwordDialog(true);
}

async function showHome() {
  showView('homeView'); $('#saveState').textContent = '';
  const r = await api('GET', '/api/drafts');
  const list = $('#draftList');
  list.replaceChildren(
    h('div', { class: 'notice warn' }, h('strong', {}, '當日使用、隔日清除：'), '今天建立的教案與上傳的學生資料，會在今晚 24:00 後自動刪除。完成後請在「匯出」步驟下載 Word（可在自己的電腦修改）或 PDF；明天需重新建立並上傳學生資料。'),
    r.drafts.length ? '' : h('p', { class: 'muted' }, '尚無教案。按「新增教案」開始。'),
    ...r.drafts.map(d => h('div', { class: 'draft' },
      h('div', {}, h('strong', {}, d.title), h('div', { class: 'muted' }, '最後修改：' + new Date(d.updated_at * 1000).toLocaleString('zh-TW'))),
      h('div', { class: 'row' },
        h('button', { class: 'btn small', onclick: () => openDraft(d.id) }, '開啟'),
        h('button', { class: 'btn small danger', onclick: async () => {
          if (!confirm(`刪除「${d.title}」？教案、上傳檔案與分析資料將一併永久刪除。`)) return;
          await api('DELETE', `/api/drafts/${d.id}`); toast('已刪除'); showHome();
        } }, '刪除')))));
  const src = await api('GET', '/api/curriculum/sources');
  $('#sourcesCard').replaceChildren(
    h('h2', {}, '已載入的課綱資料'),
    ...src.datasets.map(d => h('div', { class: 'notice' }, h('strong', {}, `${d.title}（${d.version}）`), h('div', { class: 'muted' }, `${d.items} 筆；${d.scope}`),
      d.url ? h('a', { href: d.url, target: '_blank', rel: 'noopener' }, '官方來源') : h('span', { class: 'muted' }, d.urlNote || ''))),
    h('div', { class: 'notice warn' }, h('strong', {}, '尚未載入（呈現為「待確認」）：'), src.notLoaded.join('、')),
    ...(src.imports || []).map(i => h('div', { class: 'notice' }, `教師匯入：${i.title}（${i.version}）${i.count} 筆`)),
    h('button', { class: 'btn', onclick: importDialog }, '匯入正式課綱資料（CSV／JSON）'));
  const acc = $('#accountCard') || h('div', { id: 'accountCard' });
  $('#homeView').append(acc); acc.replaceChildren(await accountCard());
}

function passwordDialog(forced) {
  const f = h('form', {},
    h('h2', {}, forced ? '請先變更密碼' : '變更密碼'),
    forced ? h('p', { class: 'muted' }, '此帳號使用管理者設定的初始密碼，請設定只有您知道的新密碼（至少 10 碼）。') : null,
    h('label', {}, '目前密碼', h('input', { name: 'old', type: 'password', required: true, autocomplete: 'current-password' })),
    h('label', {}, '新密碼（至少 10 碼）', h('input', { name: 'new', type: 'password', required: true, minlength: 10, autocomplete: 'new-password' })),
    h('label', {}, '再輸入一次', h('input', { name: 'new2', type: 'password', required: true, autocomplete: 'new-password' })),
    h('div', { class: 'row' }, h('button', { class: 'btn primary', type: 'submit' }, '變更'), forced ? null : h('button', { class: 'btn', type: 'button', onclick: closeModal }, '取消')));
  f.onsubmit = async (e) => {
    e.preventDefault(); const d = new FormData(f);
    if (d.get('new') !== d.get('new2')) return toast('兩次輸入的新密碼不同');
    try { await api('POST', '/api/me/password', { old: d.get('old'), new: d.get('new') }); S.user.mustChange = false; closeModal(); toast('密碼已變更'); }
    catch (err) { toast(err.message); }
  };
  const dlg = modal(f);
  dlg.oncancel = (e) => { if (S.user.mustChange) e.preventDefault(); };
}

async function accountCard() {
  const box = h('div', { class: 'card' }, h('h2', {}, '帳號'), h('div', { class: 'row' }, h('span', {}, `目前登入：${S.user.name}${S.user.admin ? '（管理者）' : ''}`),
    h('button', { class: 'btn small', onclick: () => passwordDialog(false) }, '變更密碼')));
  if (!S.user.admin) return box;
  const r = await api('GET', '/api/admin/users');
  const list = h('div', {}, ...r.users.map(u => h('div', { class: 'draft' },
    h('div', {}, h('strong', {}, u.name), ` ${u.username}`, u.admin ? badge('管理者', 'b-teacher') : null, u.active ? null : badge('已停用', 'b-missing')),
    h('div', { class: 'row' },
      h('button', { class: 'btn small', onclick: async () => {
        const pw = prompt(`為「${u.name}」設定新的臨時密碼（至少 10 碼；對方登入後須自行變更）`); if (!pw) return;
        try { await api('POST', `/api/admin/users/${u.id}`, { password: pw }); toast('已重設'); } catch (e) { toast(e.message); } } }, '重設密碼'),
      h('button', { class: 'btn small ' + (u.active ? 'danger' : ''), onclick: async () => {
        try { await api('POST', `/api/admin/users/${u.id}`, { active: !u.active }); showHome(); } catch (e) { toast(e.message); } } }, u.active ? '停用' : '啟用')))));
  const f = h('form', { class: 'grid' },
    h('label', {}, '帳號', h('input', { name: 'username', required: true, autocomplete: 'off' })),
    h('label', {}, '姓名', h('input', { name: 'name', required: true })),
    h('label', {}, '臨時密碼（至少 10 碼）', h('input', { name: 'password', required: true, minlength: 10, autocomplete: 'new-password' })),
    h('label', { class: 'inline' }, h('input', { name: 'admin', type: 'checkbox' }), '管理者'),
    h('button', { class: 'btn primary', type: 'submit' }, '新增教師帳號'));
  f.onsubmit = async (e) => {
    e.preventDefault(); const d = new FormData(f);
    try { await api('POST', '/api/admin/users', { username: d.get('username'), name: d.get('name'), password: d.get('password'), admin: !!d.get('admin') }); toast('已新增，請將帳號與臨時密碼交給教師'); showHome(); }
    catch (err) { toast(err.message); }
  };
  box.append(h('h3', {}, '教師帳號管理'), list, h('h3', {}, '新增帳號'), f);
  return box;
}

function importDialog() {
  const f = h('form', {},
    h('h2', {}, '匯入正式課綱資料'),
    h('p', { class: 'muted' }, '請只匯入教育部、國教署或國家教育研究院公告之原文。必要欄位：code、type（核心素養／學習表現／學習內容）、subject（須與系統領域名稱相同，如「國語文」「身體動作與健康」）、text、version、sourceTitle；選填：stage、dimension、sourceUrl、departments（kg|elem|jh|sh）。匯入資料會標示「教師匯入」。'),
    h('label', {}, '課綱名稱', h('input', { name: 'title', required: true })),
    h('label', {}, '版本（例：中華民國108年7月）', h('input', { name: 'version', required: true })),
    h('label', {}, '官方來源網址', h('input', { name: 'url', type: 'url' })),
    h('label', {}, '適用部別', h('select', { name: 'dept' }, h('option', { value: '' }, '全部'), ...S.options.departments.map(d => h('option', { value: d.key }, d.label)))),
    h('label', {}, '檔案', h('input', { name: 'file', type: 'file', accept: '.csv,.json', required: true })),
    h('div', { class: 'row' }, h('button', { class: 'btn primary', type: 'submit' }, '匯入'), h('button', { class: 'btn', type: 'button', onclick: closeModal }, '取消')));
  f.onsubmit = async (e) => {
    e.preventDefault();
    try { const r = await api('POST', '/api/curriculum/import', new FormData(f), true); toast(`已匯入 ${r.imported} 筆` + (r.errors.length ? `，${r.errors.length} 筆格式錯誤略過` : '')); closeModal(); if (!S.draftId) showHome(); }
    catch (err) { toast(err.message); }
  };
  modal(f);
}

async function openDraft(id) {
  const r = await api('GET', `/api/drafts/${id}`);
  S.draftId = id; S.plan = r.plan; S.files = r.files; S.step = 0; S.rec = null;
  const p = S.plan; p.basic ||= {}; p.students ||= []; p.analyses ||= {}; p.curriculum ||= { core: [], performance: [], content: [] };
  p.groups ||= []; p.goals ||= {}; p.activities ||= [];
  showView('editorView'); $('#saveState').textContent = '已開啟';
  render();
}

// ---------- 步驟框架 ----------
function stepDone(i) {
  const p = S.plan, b = p.basic;
  switch (i) {
    case 0: return !!(b.dept && b.stageText && b.domain && b.unit && b.minutes);
    case 1: return p.students.length > 0 && p.students.every(s => s.excludeFromPlan || S.files.some(f => f.studentKey === s.key && f.segments > 0));
    case 2: return p.students.length > 0 && p.students.every(s => s.excludeFromPlan || s.abilityConfirmed);
    case 3: return p.curriculum.performance.length > 0 && p.curriculum.content.length > 0 && !S.validation.some(v => v.level !== 'ok');
    case 4: return p.groups.some(g => g.studentKeys.length) && Object.values(p.goals).some(x => x.length);
    case 5: return p.activities.length > 0 && timeTotal() === Number(b.minutes);
    case 6: return !!p.previewed;
    default: return false;
  }
}
function render() {
  $('#stepper').replaceChildren(...STEPS.map((t, i) => h('button', { type: 'button', class: (i === S.step ? 'active ' : '') + (stepDone(i) ? 'done' : ''), 'aria-current': i === S.step ? 'step' : null, onclick: () => go(i) }, `${i + 1}. ${t}`)));
  const body = $('#stepBody'); body.replaceChildren(h('div', { class: 'card' }, h('p', { class: 'muted' }, '載入中…')));
  const fn = [stepBasic, stepUpload, stepAbilities, stepCurriculum, stepGroups, stepGenerate, stepPreview, stepExport][S.step];
  Promise.resolve(fn()).then(el => { body.replaceChildren(el); }).catch(e => body.replaceChildren(h('div', { class: 'notice err' }, e.message)));
  $('#btnPrev').disabled = S.step === 0; $('#btnNext').hidden = S.step === STEPS.length - 1;
  $('#stepper .active')?.scrollIntoView({ inline: 'center', block: 'nearest' });
}
async function go(i) { await saveNow(); S.step = i; window.scrollTo(0, 0); render(); }
$('#btnPrev').onclick = () => go(Math.max(0, S.step - 1));
$('#btnNext').onclick = () => {
  if (!stepDone(S.step) && !confirm('此步驟尚未完成或尚有待確認項目，仍要前往下一步嗎？')) return;
  go(Math.min(STEPS.length - 1, S.step + 1));
};

const ctx = () => ({ dept: S.plan.basic.dept, grade: S.plan.basic.grade, domain: S.plan.basic.domain, shDept: S.plan.basic.shDept });
function bind(obj, key, el, after) {
  const ev = (el.tagName === 'SELECT' || el.type === 'checkbox' || el.type === 'date') ? 'change' : 'input';
  el.addEventListener(ev, () => { obj[key] = el.type === 'checkbox' ? el.checked : (el.type === 'number' ? Number(el.value) : el.value); markDirty(); after && after(); });
  return el;
}

// ---------- 1. 基本資料 ----------
function deptObj() { return S.options.departments.find(d => d.key === S.plan.basic.dept); }
function domainsFor() {
  const d = deptObj(); if (!d) return [];
  const b = S.plan.basic;
  if (d.key === 'sh' && !b.shDept) return [];
  return d.domains.filter(x => (!x.grades || !b.grade || x.grades.includes(b.grade)) &&
    !(d.key === 'sh' && x.depts && !x.depts.includes(b.shDept)));
}
function autoSubjectLabel() {
  const b = S.plan.basic; const dom = domainsFor().find(x => x.key === b.domain);
  if (!dom) return;
  const base = dom.key === 'custom' ? (b.customDomain || '') : (dom.framework === 'special-needs' ? dom.label : dom.label);
  b.subjectLabel = base + (b.courseName ? '/' + b.courseName : '');
}
function stepBasic() {
  const b = S.plan.basic; const wrap = h('div', { class: 'card' }, h('h1', {}, '1. 基本資料'));
  const dSel = h('select', { 'aria-label': '部別' }, h('option', { value: '' }, '請選擇部別'), ...S.options.departments.map(d => h('option', { value: d.key, selected: b.dept === d.key }, d.label)));
  const cSel = h('select', { 'aria-label': '科別' });
  const domSel = h('select', { 'aria-label': '領域／科目' });
  const domNote = h('div', { class: 'hint' });
  const shBox = h('div', { class: 'grid' });
  const custom = h('label', { hidden: b.domain !== 'custom' }, '自訂領域／科目名稱', bind(b, 'customDomain', h('input', { value: b.customDomain || '' }), () => { autoSubjectLabel(); subj.value = b.subjectLabel || ''; }));
  const subj = h('input', { value: b.subjectLabel || '' });
  subj.addEventListener('input', () => { b.subjectLabel = subj.value; b.subjectLabelEdited = true; markDirty(); });
  const fillGrades = () => {
    const d = deptObj();
    shBox.hidden = !(d && d.key === 'sh');
    if (d && d.key === 'sh') {
      b.cluster ||= '服務群';
      cSel.replaceChildren(h('option', { value: '' }, '請選擇科別（用於篩選技能領域）'), ...d.clusters[0].departments.map(x => h('option', { value: x.key, selected: b.shDept === x.key }, x.label)));
    }
  };
  const fillDomains = () => {
    const list = domainsFor(); const groups = {};
    for (const x of list) (groups[x.group] ||= []).push(x);
    domSel.replaceChildren(h('option', { value: '' }, '請選擇領域／科目'), ...Object.entries(groups).map(([g, xs]) => h('optgroup', { label: g }, ...xs.map(x => h('option', { value: x.key, selected: b.domain === x.key }, x.label + (x.dataStatus === 'loaded' ? '' : '（課綱待確認）'))))));
    if (b.domain && !list.some(x => x.key === b.domain)) { domNote.textContent = '原選的領域／科目不適用目前部別／科別，請重新選擇。'; b.domain = ''; }
    const cur = list.find(x => x.key === b.domain);
    if (deptObj()?.key === 'sh' && !b.shDept) domNote.textContent = '請先選擇科別，系統依本校課程計畫列出該科科目。';
    else domNote.textContent = cur ? (cur.framework === 'school-practice' ? '本校校訂實習科目：課綱推薦將自服務群科課綱對應（系統推估）。' : cur.dataStatus === 'loaded' ? '此科目已載入官方課綱（逐字擷取）。' : '此領域尚未載入可信課綱資料：課綱欄位將標示「待確認」，可匯入官方資料。') : domNote.textContent;
    custom.hidden = b.domain !== 'custom';
    fillUnits(cur);
  };
  const ctxChanged = async () => { S.rec = null; S.ctxItems = null; autoSubjectLabel(); subj.value = b.subjectLabel || ''; markDirty(); await revalidate(true); };
  dSel.onchange = () => { b.dept = dSel.value; b.grade = ''; if (b.dept !== 'sh') { b.shDept = ''; } fillGrades(); fillDomains(); ctxChanged(); };
  cSel.onchange = () => { b.shDept = cSel.value; fillDomains(); ctxChanged(); };
  domSel.onchange = () => { b.domain = domSel.value; b.subjectLabelEdited = false; fillDomains(); ctxChanged(); };
  const unitBox = h('div', { class: 'notice', hidden: true });
  function fillUnits(cur) {
    const ol = cur && cur.outline;
    unitBox.hidden = !ol; if (!ol) return;
    const sel = h('select', { 'aria-label': '教學大綱單元' }, h('option', { value: '' }, ol.units?.length ? '從本校教學大綱選擇單元（可再修改）' : '此科目教學大綱單元未能自動擷取，請自行輸入'),
      ...(ol.units || []).map((u, i) => h('option', { value: i, selected: b.unit === u.title }, `（${u.no}）${u.title}`)));
    const detail = h('div', { class: 'hint' });
    const show = () => { const u = ol.units?.[sel.value]; detail.textContent = u ? '內容細項：' + u.items.join('、') : ''; };
    sel.onchange = () => { const u = ol.units?.[sel.value]; if (!u) return; b.unit = u.title; b.keywords = u.items.join('、'); unitIn.value = u.title; S.rec = null; show(); markDirty(); };
    show();
    unitBox.replaceChildren(h('strong', {}, `本校課程計畫：${cur.label}（${ol.table}）`), ol.goals ? h('div', { class: 'hint' }, '教學目標：' + ol.goals) : null,
      h('label', {}, '教學大綱單元', sel), detail, h('div', { class: 'hint' }, ol.extractNote));
  }
  fillGrades(); fillDomains();
  shBox.append(h('label', {}, '群別', h('select', { disabled: true }, h('option', {}, '服務群'))), h('label', {}, '科別', cSel));
  const unitIn = bind(b, 'unit', h('input', { value: b.unit || '', placeholder: '例：上課好好坐' }), () => { S.rec = null; });
  const stage = h('input', { value: b.stageText || '', 'aria-label': '班級', placeholder: '請自行填寫，例：小1、國八甲、高二餐飲A組' }); stage.addEventListener('input', () => { b.stageText = stage.value; b.stageEdited = true; markDirty(); });
  const dateIn = h('input', { type: 'date', value: b.date || '' }); dateIn.onchange = () => { b.date = dateIn.value; b.dateText = rocDate(b.date); markDirty(); };
  if (b.date && !b.dateText) b.dateText = rocDate(b.date);
  wrap.append(
    h('div', { class: 'grid' }, h('label', {}, '部別', dSel), h('label', {}, '班級', stage)), shBox,
    h('div', { class: 'grid' }, h('label', {}, '領域／科目', domSel, domNote), custom,
      h('label', {}, '課程名稱（選填，例：餐飲服務禮儀實作）', bind(b, 'courseName', h('input', { value: b.courseName || '' }), () => { autoSubjectLabel(); subj.value = b.subjectLabel || ''; }))),
    unitBox,
    h('div', { class: 'grid' },
      h('label', {}, '單元名稱', unitIn),
      h('label', {}, '教學日期', dateIn),
      h('label', {}, '教學者', bind(b, 'teacher', h('input', { value: b.teacher || '' })))),
    h('div', { class: 'grid' },
      h('label', {}, '教學總節數', bind(b, 'totalPeriods', h('input', { type: 'number', min: 1, value: b.totalPeriods || 1 }))),
      h('label', {}, '本節為第＿節', bind(b, 'periodNo', h('input', { type: 'number', min: 1, value: b.periodNo || 1 }))),
      h('label', {}, '每節分鐘數', bind(b, 'minutes', h('input', { type: 'number', min: 10, max: 180, value: b.minutes || 45 })))),
    h('p', { class: 'hint' }, '切換部別、科別或領域後，系統會重新檢核已勾選的課綱項目，提示不適用者。'));
  return wrap;
}

async function revalidate(announce) {
  const sel = [...S.plan.curriculum.core, ...S.plan.curriculum.performance, ...S.plan.curriculum.content];
  if (!sel.length) { S.validation = []; return; }
  const r = await api('POST', '/api/curriculum/validate', { context: ctx(), selection: sel });
  S.validation = r.results;
  const bad = r.results.filter(x => x.level !== 'ok');
  if (announce && bad.length) {
    const box = h('div', {}, h('h2', {}, '已選課綱項目需要重新檢核'),
      h('p', {}, '部別／科別／領域變更後，下列項目不適用或需確認：'),
      ...bad.map(x => h('div', { class: 'sel-item ' + (x.level === 'error' ? 'err' : 'warn') }, h('strong', {}, x.code + ' '), x.messages.join('；'))),
      h('div', { class: 'row' },
        h('button', { class: 'btn primary', onclick: () => { removeInvalid(bad.filter(x => x.level === 'error')); closeModal(); } }, '移除不適用項目（警告項目保留待確認）'),
        h('button', { class: 'btn', onclick: closeModal }, '稍後在課綱步驟處理')));
    modal(box);
  }
}
function removeInvalid(list) {
  const ids = new Set(list.map(x => x.itemId));
  for (const k of ['core', 'performance', 'content']) S.plan.curriculum[k] = S.plan.curriculum[k].filter(x => !ids.has(x.itemId));
  S.validation = S.validation.filter(x => !ids.has(x.itemId)); markDirty(); toast(`已移除 ${ids.size} 項不適用項目`);
}

// ---------- 2. 上傳資料 ----------
function privacyNotice() {
  const p = S.privacy;
  return h('div', { class: 'notice' },
    h('strong', {}, '資料處理說明（上傳前請閱讀）'),
    h('ul', {},
      h('li', {}, '處理位置：檔案上傳至學校自建之本系統伺服器，在伺服器上擷取文字與分析；檔案、擷取文字與教案內容皆以加密方式保存，僅上傳教師本人可存取。'),
      h('li', {}, p.aiEnabled ? `外部 AI：管理者已啟用（${p.aiModel}）。只有在您於分析時勾選同意後，才會將該生擷取文字（姓名以代號取代）送至 Anthropic API；預設不送出。` : '外部 AI：未啟用。所有分析皆在本系統伺服器以規則式比對完成，不送出任何資料。'),
      h('li', {}, 'OCR（掃描檔、照片）：' + p.ocr.message),
      h('li', {}, h('strong', {}, '系統不保存資料：教案、學生資料與上傳檔案皆於隔日（臺灣時間 00:05）自動刪除。請當天完成並下載 Word 檔，在自己的電腦上調整；下次使用需重新上傳學生資料。'), '您也可隨時自行刪除單一檔案、分析資料或整份教案。'),
      h('li', {}, '系統紀錄只記錄操作類型與編號，不記錄學生姓名或內容。建議以代號取代學生全名。')),
    h('div', { class: 'hint' }, '支援格式：' + [...new Set(Object.values(p.supported))].join('、') + `；單檔上限 ${p.maxUploadMb} MB。不支援：.doc、HEIC 等（會提示轉檔方式）。`));
}
function stepUpload() {
  const p = S.plan; const wrap = h('div', { class: 'card' }, h('h1', {}, '2. 上傳學生資料'), privacyNotice());
  const nameIn = h('input', { placeholder: '學生姓名或代號（建議代號，如：A1、甲）' });
  const add = () => { const v = nameIn.value.trim(); if (!v) return toast('請輸入姓名或代號'); p.students.push({ key: 's' + uid(), name: v, code: v, gender: '', disability: '' }); markDirty(); render(); };
  wrap.append(h('div', { class: 'row' }, h('div', { style: 'flex:1;min-width:200px' }, nameIn), h('button', { class: 'btn primary', onclick: add }, '＋ 新增學生')));
  if (!p.students.length) wrap.append(h('p', { class: 'muted' }, '請先新增學生，再為每位學生上傳 IEP、學習表現紀錄、評量結果或觀察紀錄。'));
  for (const s of p.students) wrap.append(studentUploadCard(s));
  return wrap;
}
function studentUploadCard(s) {
  const files = S.files.filter(f => f.studentKey === s.key);
  const fileIn = h('input', { type: 'file', multiple: true, accept: '.pdf,.docx,.txt,.png,.jpg,.jpeg,.bmp,.tif,.tiff,.webp,image/*' });
  const status = h('div', { class: 'hint', 'aria-live': 'polite' });
  fileIn.onchange = async () => {
    if (!fileIn.files.length) return;
    const max = S.privacy.maxUploadMb * 1024 * 1024; const errs = [];
    for (const file of fileIn.files) {
      if (file.size > max) { errs.push(`${file.name}：超過 ${S.privacy.maxUploadMb} MB，請壓縮或分頁後再上傳`); continue; }
      status.textContent = `上傳與擷取中：${file.name}…`;
      const fd = new FormData(); fd.append('studentKey', s.key); fd.append('file', file);
      try {
        const r = await api('POST', `/api/drafts/${S.draftId}/files`, fd, true);
        for (const f of r.files) { if (f.id) S.files.push(f); else errs.push(`${f.filename}：${f.error}`); }
      } catch (e) { errs.push(`${file.name}：${e.message}`); }
    }
    if (errs.length) modal(h('div', {}, h('h2', {}, '部分檔案未能處理'), ...errs.map(x => h('p', { class: 'notice err' }, x)), h('button', { class: 'btn', onclick: () => { closeModal(); render(); } }, '知道了')));
    else render();
  };
  const paste = h('textarea', { placeholder: '或直接貼上文字（例如：觀察紀錄、IEP 現況描述）' });
  const doPaste = async () => {
    if (!paste.value.trim()) return;
    const r = await api('POST', `/api/drafts/${S.draftId}/paste`, { studentKey: s.key, text: paste.value, label: '貼上文字' + (files.length + 1) });
    S.files.push(r.file); render();
  };
  const nameIn = bind(s, 'name', h('input', { value: s.name || '' }));
  return h('div', { class: 'student' },
    h('div', { class: 'row space' }, h('h2', {}, s.code || s.name),
      h('div', { class: 'row' },
        h('label', { class: 'inline' }, bind(s, 'excludeFromPlan', h('input', { type: 'checkbox', checked: s.excludeFromPlan })), '本節不列入'),
        h('button', { class: 'btn small danger', onclick: async () => {
          if (!confirm('移除此學生？其上傳檔案與分析資料將一併刪除。')) return;
          for (const f of files) await api('DELETE', `/api/drafts/${S.draftId}/files/${f.id}`);
          await api('DELETE', `/api/drafts/${S.draftId}/analysis/${s.key}`).catch(() => {});
          S.files = S.files.filter(f => f.studentKey !== s.key); S.plan.students = S.plan.students.filter(x => x !== s);
          delete S.plan.analyses[s.key]; for (const g of S.plan.groups) g.studentKeys = g.studentKeys.filter(k => k !== s.key);
          markDirty(); render();
        } }, '移除學生'))),
    h('div', { class: 'grid' }, h('label', {}, '教案顯示姓名（可用代號）', nameIn), h('label', {}, '上傳檔案（可多選；手機可拍照）', fileIn)),
    status,
    h('div', {}, paste, h('button', { class: 'btn small', onclick: doPaste }, '加入貼上文字')),
    files.length ? h('div', {}, ...files.map(f => h('div', { class: 'file-item' },
      h('div', {}, h('strong', {}, f.filename), ' ', badge(f.status === '已擷取' ? '已擷取' : f.status, f.status === '已擷取' ? 'b-fact' : 'b-missing'),
        h('div', { class: 'hint' }, `${f.method || ''}${f.pages ? `，${f.pages} 頁` : ''}，擷取 ${f.segments} 段`),
        ...(f.warnings || []).map(w => h('div', { class: 'notice warn' }, w)), f.error ? h('div', { class: 'notice err' }, f.error) : null),
      h('div', { class: 'row' },
        h('button', { class: 'btn small', onclick: () => showSegments(f) }, '檢視擷取文字'),
        h('button', { class: 'btn small danger', onclick: async () => {
          if (!confirm(`刪除「${f.filename}」？以此檔為佐證的分析項目也會移除。`)) return;
          const r = await api('DELETE', `/api/drafts/${S.draftId}/files/${f.id}`);
          S.files = S.files.filter(x => x.id !== f.id); if (r.analysis) S.plan.analyses[s.key] = r.analysis; render();
        } }, '刪除'))))) : h('p', { class: 'muted' }, '尚未上傳資料。'));
}
async function showSegments(f) {
  const r = await api('GET', `/api/drafts/${S.draftId}/files/${f.id}/segments`);
  modal(h('div', {}, h('h2', {}, f.filename), h('p', { class: 'hint' }, '以下為系統擷取的原始文字（含位置），分析只會引用這些內容。'),
    ...r.segments.map(s => h('p', {}, h('span', { class: 'badge b-neutral' }, [s.loc.page ? `第${s.loc.page}頁` : '', s.loc.table ? `表${s.loc.table}列${s.loc.row}` : '', s.loc.para ? `第${s.loc.para}段` : ''].join(' ')),
      s.conf !== undefined && s.conf < 60 ? badge('辨識信心低', 'b-missing') : null, s.text)),
    h('button', { class: 'btn', onclick: closeModal }, '關閉')), true);
}

// ---------- 3. 先備能力 ----------
function stepAbilities() {
  const p = S.plan; const wrap = h('div', { class: 'card' }, h('h1', {}, '3. 確認先備能力'),
    h('p', { class: 'muted' }, '每一項能力描述都是上傳資料的原句，並標示檔名與頁碼／段落。請逐項確認、修改或排除；資料中沒有的面向列為「資料不足」，系統不會自行補寫。'),
    h('div', { class: 'row' }, badge('原文事實'), badge('系統推估'), badge('資料不足'), badge('教師確認')));
  for (const s of p.students.filter(s => !s.excludeFromPlan)) wrap.append(abilityCard(s));
  return wrap;
}
function composeSummary(s, a) {
  const parts = (a?.abilities || []).filter(x => x.confirmed && !x.excluded).map(x => (x.teacherText || x.quote).replace(/[。；]$/, ''));
  const extra = (a?.insufficient || []).filter(x => x.teacherText).map(x => x.teacherText.replace(/[。；]$/, ''));
  return [...parts, ...extra].join('。') + (parts.length + extra.length ? '。' : '');
}
function abilityCard(s) {
  const a = S.plan.analyses[s.key];
  const box = h('div', { class: 'student' }, h('div', { class: 'row space' }, h('h2', {}, s.code || s.name), s.abilityConfirmed ? badge('教師確認') : badge('待確認')));
  const aiOn = S.privacy.aiEnabled;
  const consent = h('input', { type: 'checkbox' });
  const useAI = h('input', { type: 'checkbox' });
  const run = async () => {
    if (useAI.checked && !consent.checked) return toast('使用外部 AI 前請勾選同意');
    try {
      const r = await api('POST', `/api/drafts/${S.draftId}/analyze`, { studentKey: s.key, useAI: useAI.checked, consent: consent.checked });
      S.plan.analyses[s.key] = r.analysis; s.abilityConfirmed = false;
      if (r.analysis.basic.gender.status === '原文事實' && !s.gender) s.gender = r.analysis.basic.gender.value;
      if (r.analysis.basic.disability.status === '原文事實' && !s.disability) s.disability = r.analysis.basic.disability.value;
      markDirty(); render();
    } catch (e) { toast(e.message); }
  };
  box.append(h('div', { class: 'row' },
    h('button', { class: 'btn primary', onclick: run }, a ? '重新擷取分析' : '擷取分析'),
    aiOn ? h('label', { class: 'inline' }, useAI, '使用外部 AI 輔助') : h('span', { class: 'hint' }, '本機規則式分析（不送出資料）'),
    aiOn ? h('label', { class: 'inline' }, consent, '我同意將此生擷取文字（姓名以代號取代）送至外部 AI') : null,
    a ? h('button', { class: 'btn small danger', onclick: async () => { if (!confirm('刪除此學生的分析資料？（上傳檔案保留）')) return; await api('DELETE', `/api/drafts/${S.draftId}/analysis/${s.key}`); delete S.plan.analyses[s.key]; s.abilityConfirmed = false; s.abilitySummary = ''; render(); } }, '刪除分析資料') : null));
  if (!a) { box.append(h('p', { class: 'muted' }, S.files.some(f => f.studentKey === s.key) ? '尚未分析。' : '尚未分析，且此生目前沒有上傳檔案（檔案於上傳隔日自動刪除），請重新上傳。')); return box; }
  if (!S.files.some(f => f.studentKey === s.key)) box.append(h('div', { class: 'notice' }, '此生上傳檔案已依規定於隔日自動刪除；以下佐證為當時擷取的紀錄，如需重新分析請重新上傳。'));
  box.append(h('div', { class: 'hint' }, `分析方式：${a.mode === 'ai' ? '外部 AI（引文已逐字核對）' : '本機規則式'}；產生時間 ${new Date(a.generatedAt * 1000).toLocaleString('zh-TW')}`));
  if (a.rejected?.length) box.append(h('div', { class: 'notice warn' }, `AI 回傳 ${a.rejected.length} 句無法在原始資料逐字找到，已排除，未採用。`));
  // 基本欄位
  const fieldRow = (label, key, info) => h('label', {}, label,
    h('div', { class: 'row' }, badge(s[key] && s[key] !== info.value ? '教師確認' : info.status),
      ...(info.evidence || []).map(e => h('span', { class: 'hint' }, `佐證：「${e.quote}」${e.label}`)), info.note ? h('span', { class: 'hint' }, info.note) : null),
    bind(s, key, h('input', { value: s[key] || '', placeholder: '資料未載明者請留白' })));
  box.append(h('div', { class: 'grid' }, fieldRow('性別（僅依資料填寫，缺漏可留白）', 'gender', a.basic.gender), fieldRow('障礙類別（僅依資料填寫，缺漏可留白）', 'disability', a.basic.disability)));
  if (a.basic.nameCandidates?.length) box.append(h('div', { class: 'hint' }, '資料中出現的姓名：' + a.basic.nameCandidates.join('、') + '（請確認檔案屬於此生）'));
  // 能力項目
  const doms = ['認知理解', '溝通', '動作操作', '社會互動', '情緒行為', '生活自理', '所需協助'];
  for (const d of doms) {
    const items = a.abilities.filter(x => x.domains[0] === d);
    const miss = a.insufficient.find(x => x.domain === d);
    if (!items.length && !miss) continue;
    box.append(h('h3', {}, d));
    for (const it of items) box.append(abilityItem(s, it));
    if (miss) box.append(h('div', { class: 'ability' }, badge('資料不足'), miss.note,
      h('label', {}, '教師補充（選填，將以教師確認身分列入）', bind(miss, 'teacherText', h('textarea', { value: miss.teacherText || '' }), () => onAbilityChange(s)))));
  }
  const allDone = a.abilities.every(x => x.confirmed || x.excluded);
  const sum = h('textarea', { value: s.abilitySummary || '' }); sum.style.minHeight = '7rem';
  sum.addEventListener('input', () => { s.abilitySummary = sum.value; s.summaryEdited = true; markDirty(); });
  const conf = h('input', { type: 'checkbox', checked: s.abilityConfirmed, disabled: !allDone });
  conf.onchange = () => { s.abilityConfirmed = conf.checked; if (!s.abilitySummary) s.abilitySummary = composeSummary(s, a); markDirty(); render(); };
  box.append(h('h3', {}, '教案「與本單元教學相關之能力」欄敘述'),
    h('div', { class: 'hint' }, '由已確認的項目自動組合，可再修改。'),
    sum, h('button', { class: 'btn small', onclick: () => { s.abilitySummary = composeSummary(s, a); s.summaryEdited = false; markDirty(); render(); } }, '依已確認項目重新組合'),
    h('label', { class: 'inline' }, conf, allDone ? '我已逐項檢視，確認此生先備能力' : '（尚有未確認或未排除的項目）'));
  return box;
}
function onAbilityChange(s) { const a = S.plan.analyses[s.key]; if (!s.summaryEdited) s.abilitySummary = composeSummary(s, a); s.abilityConfirmed = false; markDirty(); }
function abilityItem(s, it) {
  const el = h('div', { class: 'ability' + (it.excluded ? ' excluded' : '') + (it.confirmed ? ' confirmed' : '') });
  const c = h('input', { type: 'checkbox', checked: it.confirmed }); c.onchange = () => { it.confirmed = c.checked; if (c.checked) it.excluded = false; onAbilityChange(s); render(); };
  const x = h('input', { type: 'checkbox', checked: it.excluded }); x.onchange = () => { it.excluded = x.checked; if (x.checked) it.confirmed = false; onAbilityChange(s); render(); };
  el.append(
    h('div', {}, badge(it.teacherText ? '教師確認' : '原文事實'), it.lowConfidence ? badge('OCR 信心低', 'b-missing') : null, ...it.domains.map(d => h('span', { class: 'chip' }, d))),
    h('div', { class: 'quote' }, it.quote),
    h('div', { class: 'meta' }, '佐證：' + it.evidence.label),
    h('div', { class: 'meta' }, '所需支持：', it.support.levels.length ? [badge('原文事實'), it.support.levels.join('、')] : [badge('資料不足'), '原句未描述協助程度']),
    h('div', { class: 'meta' }, '與本單元關聯：', badge('系統推估'), it.relevance.text),
    h('label', {}, '教師修改敘述（留白則使用原句）', bind(it, 'teacherText', h('textarea', { value: it.teacherText || '', rows: 2 }), () => onAbilityChange(s))),
    h('div', { class: 'row' }, h('label', { class: 'inline' }, c, '已確認'), h('label', { class: 'inline' }, x, '與本單元無關，排除')));
  return el;
}

// ---------- 4. 課綱 ----------
const TYPES = [['core', '核心素養'], ['performance', '學習表現'], ['content', '學習內容']];
async function stepCurriculum() {
  const p = S.plan, b = p.basic;
  const wrap = h('div', { class: 'card' }, h('h1', {}, '4. 確認課綱'));
  const kw = bind(b, 'keywords', h('input', { value: b.keywords || '', placeholder: '補充關鍵詞（例：坐姿、規範、指令）' }));
  const abil = p.students.filter(s => !s.excludeFromPlan).map(s => s.abilitySummary || '').filter(Boolean);
  const load = async (rerender = true) => { S.rec = await api('POST', '/api/curriculum/recommend', { context: ctx(), unit: `${b.unit || ''} ${b.keywords || ''}`, abilities: abil, limit: 12 }); S.ctxItems = null; if (rerender) render(); };
  if (!S.rec) await load(false).catch(e => toast(e.message));
  await revalidate(false);
  const rec = S.rec || { status: '待確認', reason: '' };
  wrap.append(h('div', { class: 'notice ' + (rec.status === '待確認' ? 'warn' : '') }, badge(rec.status), rec.status === '已載入'
      ? '推薦依「部別＋年級／學習階段＋領域／科目＋單元名稱＋學生能力」計算共同詞（系統推估），請逐項勾選；可展開該科目全部項目或搜尋其他科目。'
      : rec.reason),
    h('div', { class: 'row' }, h('div', { style: 'flex:1;min-width:220px' }, kw), h('button', { class: 'btn', onclick: load }, '重新推薦'),
      h('button', { class: 'btn', onclick: importDialog }, '匯入課綱資料')));
  if (rec.status !== '待確認') {
    const cols = h('div', { class: 'cols3' });
    for (const [k, label] of TYPES) cols.append(curColumn(k, label, rec[k] || []));
    wrap.append(cols);
  } else {
    wrap.append(h('p', {}, '目前教案的核心素養、學習表現、學習內容將顯示「待確認」。您可匯入官方資料，或用下方搜尋加入其他已載入課綱（將標示跨領域）。'));
  }
  wrap.append(searchBox());
  // 已選項目
  wrap.append(h('h2', {}, '已選項目（官方原文不可改；教師調整敘述另存並可追溯）'));
  for (const [k, label] of TYPES) {
    wrap.append(h('h3', {}, `${label}（${p.curriculum[k].length}）`));
    if (!p.curriculum[k].length) wrap.append(h('p', { class: 'muted' }, '尚未選擇（教案將顯示「待確認」）'));
    for (const x of p.curriculum[k]) wrap.append(selItem(k, x));
  }
  wrap.append(h('h2', {}, '議題融入'),
    h('p', { class: 'hint' }, '系統尚未載入議題學習主題與實質內涵代碼，請依《議題融入說明手冊》原文填寫（例：品德教育／品U1 …），系統不自動產生代碼。'),
    bind(p, 'issuesText', h('textarea', { value: p.issuesText || '' })));
  return wrap;
}
function isSel(k, id) { return S.plan.curriculum[k].some(x => x.itemId === id); }
function toggleSel(k, it, on) {
  const list = S.plan.curriculum[k];
  if (on && !isSel(k, it.id)) list.push({ itemId: it.id, code: it.code, type: it.type, subject: it.subject, officialText: it.text, teacherText: '', source: it.source, stageLabel: it.stageLabel });
  if (!on) S.plan.curriculum[k] = list.filter(x => x.itemId !== it.id);
  markDirty(); revalidate(false).then(render);
}
function curRow(k, it) {
  const c = h('input', { type: 'checkbox', checked: isSel(k, it.id), 'aria-label': it.code }); c.onchange = () => toggleSel(k, it, c.checked);
  return h('div', { class: 'cur-item' }, c, h('div', {},
    h('span', { class: 'code' }, it.code), ' ', it.text,
    h('small', {}, [it.dimension, it.stageLabel].filter(Boolean).join('｜')),
    it.reason ? h('small', {}, badge('系統推估'), it.reason) : null));
}
function curColumn(k, label, items) {
  const col = h('div', {}, h('h2', {}, label), h('div', { class: 'hint' }, `推薦 ${items.length} 項／本科目共 ${S.rec.totals?.[label] ?? '?'} 項`));
  for (const it of items) col.append(curRow(k, it));
  col.append(h('button', { class: 'btn small', onclick: () => showAll(k, label) }, `展開本科目全部${label}`));
  return col;
}
async function showAll(k, label) {
  S.ctxItems ||= (await api('POST', '/api/curriculum/items', { context: ctx() })).items;
  const items = S.ctxItems.filter(x => x.type === label);
  const filter = h('input', { placeholder: '篩選文字或代碼' }); const list = h('div', {});
  const draw = () => list.replaceChildren(...items.filter(x => !filter.value || x.text.includes(filter.value) || x.code.includes(filter.value)).map(x => curRow(k, x)));
  filter.oninput = draw; draw();
  modal(h('div', {}, h('h2', {}, `本科目全部${label}（${items.length}）`), filter, list, h('button', { class: 'btn', onclick: () => { closeModal(); render(); } }, '完成')), true);
}
function searchBox() {
  const q = h('input', { placeholder: '搜尋所有已載入課綱（代碼或文字），可加入跨領域項目' });
  const t = h('select', {}, h('option', { value: '' }, '全部類型'), ...TYPES.map(([, l]) => h('option', { value: l }, l)));
  const out = h('div', {});
  const run = async () => {
    const r = await api('GET', '/api/curriculum/search?' + new URLSearchParams({ q: q.value, type: t.value }));
    out.replaceChildren(...r.items.map(x => curRow(TYPES.find(([, l]) => l === x.type)[0], { ...x, reason: `${x.subject}${x.skillDomain ? '／' + x.skillDomain : ''}` })));
    if (!r.items.length) out.append(h('p', { class: 'muted' }, '查無資料'));
  };
  return h('details', {}, h('summary', {}, '搜尋其他科目／跨領域項目'), h('div', { class: 'row' }, h('div', { style: 'flex:1;min-width:200px' }, q), t, h('button', { class: 'btn', onclick: run }, '搜尋')), out);
}
function selItem(k, x) {
  const v = S.validation.find(r => r.itemId === x.itemId);
  const lvl = v ? v.level : 'ok';
  const conf = h('input', { type: 'checkbox', checked: x.teacherConfirmed });
  conf.onchange = () => { x.teacherConfirmed = conf.checked; markDirty(); revalidate(false).then(render); };
  const src = x.source || {};
  return h('div', { class: 'sel-item ' + (lvl === 'error' ? 'err' : lvl === 'warn' ? 'warn' : '') },
    h('div', { class: 'row space' }, h('strong', {}, x.code), h('button', { class: 'btn small danger', onclick: () => toggleSel(k, { id: x.itemId }, false) }, '移除')),
    h('div', { class: 'official' }, badge('官方原文'), x.officialText),
    h('div', { class: 'hint' }, `來源：${src.title || ''}（${src.version || ''}）${src.pdfPage ? ` PDF第${src.pdfPage}頁` : ''}${src.url ? '' : '；' + (src.urlNote || src.note || '')}`, src.url ? h('a', { href: src.url, target: '_blank', rel: 'noopener' }, ' 官方連結') : null),
    v && v.messages.length ? h('div', {}, ...v.messages.map(m => h('div', { class: 'hint' }, '⚠ ' + m))) : null,
    lvl === 'warn' || x.teacherConfirmed ? h('label', { class: 'inline' }, conf, '我已確認此項目適用本教案') : null,
    h('label', {}, '教師調整敘述（選填；教案將以此呈現並保留代碼對應官方原文）', bind(x, 'teacherText', h('textarea', { value: x.teacherText || '', rows: 2 }))));
}

// ---------- 5. 分組與目標 ----------
function stepGroups() {
  const p = S.plan; const wrap = h('div', { class: 'card' }, h('h1', {}, '5. 能力分組與學習目標'));
  const active = p.students.filter(s => !s.excludeFromPlan);
  if (!p.groups.length) p.groups = ['A', 'B', 'C'].map(k => ({ key: k, name: k + '組', studentKeys: [] }));
  const nSel = h('select', {}, ...[1, 2, 3, 4].map(n => h('option', { value: n, selected: p.groups.length === n }, n + ' 組')));
  nSel.onchange = () => {
    const n = Number(nSel.value);
    while (p.groups.length < n) { const k = String.fromCharCode(65 + p.groups.length); p.groups.push({ key: k, name: k + '組', studentKeys: [] }); }
    if (p.groups.length > n) { const drop = p.groups.splice(n); for (const g of drop) delete p.goals[g.key]; }
    markDirty(); render();
  };
  const suggest = async () => {
    const r = await api('POST', `/api/drafts/${S.draftId}/groups/suggest`, { names: p.groups.map(g => g.name) });
    p.groups = r.groups.map((g, i) => ({ ...g, name: p.groups[i]?.name || g.name })); p.groupRationale = r;
    markDirty(); render();
  };
  wrap.append(h('p', { class: 'muted' }, '依本單元相關先備能力的支持需求建議分組；不依障礙類別或年級決定。組數、組名與歸組皆可調整。'),
    h('div', { class: 'row' }, h('label', {}, '組數', nSel), h('button', { class: 'btn', onclick: suggest }, '依佐證建議分組')));
  if (p.groupRationale) wrap.append(h('div', { class: 'notice' }, badge('系統推估'), p.groupRationale.note,
    ...p.groupRationale.groups.flatMap(g => g.rationale.map(r => h('div', { class: 'hint' }, `${nameOf(r.studentKey)} → ${g.name}：支持需求指數 ${r.score}；${r.reasons.join('；') || '依佐證推估'}`))),
    ...(p.groupRationale.unassigned || []).map(u => h('div', { class: 'hint' }, `${nameOf(u.studentKey)}：${u.note}`))));
  const grid = h('div', { class: 'grid' });
  for (const g of p.groups) grid.append(h('label', {}, `組名（${g.key}）`, bind(g, 'name', h('input', { value: g.name }))));
  wrap.append(grid, h('h2', {}, '學生歸組'));
  for (const s of active) {
    const sel = h('select', {}, h('option', { value: '' }, '未分組'), ...p.groups.map(g => h('option', { value: g.key, selected: g.studentKeys.includes(s.key) }, g.name)));
    sel.onchange = () => { for (const g of p.groups) g.studentKeys = g.studentKeys.filter(k => k !== s.key); const g = p.groups.find(g => g.key === sel.value); if (g) g.studentKeys.push(s.key); markDirty(); };
    wrap.append(h('div', { class: 'row' }, h('span', { style: 'min-width:7rem' }, s.code || s.name), sel));
  }
  const genGoals = async () => {
    await saveNow();
    try { const r = await api('POST', `/api/drafts/${S.draftId}/goals/suggest`); p.goals = r.goals; p.goalNote = r.note; markDirty(); render(); }
    catch (e) { toast(e.message); }
  };
  wrap.append(h('h2', {}, '各組學習目標'), h('div', { class: 'row' }, h('button', { class: 'btn primary', onclick: genGoals }, Object.keys(p.goals).length ? '重新產生目標建議（會覆蓋）' : '產生目標建議')));
  if (p.goalNote) wrap.append(h('div', { class: 'notice' }, badge('系統推估'), p.goalNote));
  for (const g of p.groups) {
    const list = p.goals[g.key] ||= [];
    const missing = ['認知', '情意', '技能'].filter(d => !list.some(x => x.domain === d));
    wrap.append(h('h3', {}, g.name), missing.length && list.length ? h('div', { class: 'hint' }, `此組尚無：${missing.join('、')}目標（若與本單元無關可不設）`) : null,
      ...list.map(go => goalEditor(g, go)),
      h('button', { class: 'btn small', onclick: () => { list.push(newGoal(g)); markDirty(); render(); } }, '＋ 新增目標'));
  }
  return wrap;
}
const nameOf = (k) => { const s = S.plan.students.find(x => x.key === k); return s ? (s.code || s.name) : k; };
function newGoal(g) { const cur = S.plan.curriculum; return { id: uid(), groupKey: g.key, domain: '認知', situation: '', behavior: '', support: '', criterion: '', criterionSuggested: true, responseModes: ['口語'], performanceCodes: cur.performance.slice(0, 1).map(x => x.code), contentCodes: cur.content.slice(0, 1).map(x => x.code), assessment: '' }; }
function composeGoal(go) { return `${go.situation}，${go.support}，${go.behavior}，達成標準：${go.criterion}${go.criterionSuggested ? '（建議值，請教師確認）' : ''}。`.replace(/，，+/g, '，').replace(/^，/, ''); }
function goalEditor(g, go) {
  const comp = h('div', { class: 'composed' }, go.text || composeGoal(go));
  const upd = () => { go.text = composeGoal(go); comp.textContent = go.text; };
  const modes = ['口語', '指認', '手勢', '溝通輔具（圖卡／溝通板）'];
  const cur = S.plan.curriculum;
  const codeChecks = (list, field) => h('div', { class: 'chips' }, ...list.map(x => {
    const c = h('input', { type: 'checkbox', checked: (go[field] || []).includes(x.code) });
    c.onchange = () => { go[field] = c.checked ? [...new Set([...(go[field] || []), x.code])] : go[field].filter(y => y !== x.code); markDirty(); };
    return h('label', { class: 'inline chip' }, c, x.code);
  }));
  const dSel = h('select', {}, ...['認知', '情意', '技能'].map(d => h('option', { selected: go.domain === d }, d)));
  return h('div', { class: 'goal' },
    h('div', { class: 'row space' }, h('label', { class: 'inline' }, '類別', bind(go, 'domain', dSel)),
      h('button', { class: 'btn small danger', onclick: () => { S.plan.goals[g.key] = S.plan.goals[g.key].filter(x => x !== go); markDirty(); render(); } }, '刪除')),
    h('div', { class: 'grid' },
      h('label', {}, '情境', bind(go, 'situation', h('input', { value: go.situation }), upd)),
      h('label', {}, '協助程度', bind(go, 'support', h('input', { value: go.support }), upd)),
      h('label', {}, '可觀察行為', bind(go, 'behavior', h('input', { value: go.behavior }), upd)),
      h('label', {}, ['達成標準 ', go.criterionSuggested ? badge('建議值') : badge('教師確認')], bind(go, 'criterion', h('input', { value: go.criterion }), upd))),
    h('label', { class: 'inline' }, bind(go, 'criterionSuggested', h('input', { type: 'checkbox', checked: go.criterionSuggested }), () => { upd(); render(); }), '達成標準為建議值（尚待教師依學生資料確認）'),
    h('div', {}, h('strong', {}, '回應方式：'), h('div', { class: 'chips' }, ...modes.map(m => {
      const c = h('input', { type: 'checkbox', checked: (go.responseModes || []).includes(m) });
      c.onchange = () => { go.responseModes = c.checked ? [...(go.responseModes || []), m] : go.responseModes.filter(x => x !== m); markDirty(); };
      return h('label', { class: 'inline chip' }, c, m);
    }))),
    h('div', {}, h('strong', {}, '對應學習表現：'), codeChecks(cur.performance, 'performanceCodes')),
    h('div', {}, h('strong', {}, '對應學習內容：'), codeChecks(cur.content, 'contentCodes')),
    h('label', {}, '評量方式', bind(go, 'assessment', h('input', { value: go.assessment || '' }))),
    h('div', { class: 'hint' }, '教案呈現：'), comp);
}

// ---------- 6. 生成教案 ----------
const timeTotal = () => S.plan.activities.reduce((a, x) => a + (Number(x.minutes) || 0), 0);
function stepGenerate() {
  const p = S.plan; const wrap = h('div', { class: 'card' }, h('h1', {}, '6. 生成教案（教學流程）'));
  const unconfirmed = p.students.filter(s => !s.excludeFromPlan && !s.abilityConfirmed);
  if (unconfirmed.length) wrap.append(h('div', { class: 'notice warn' }, `尚有學生先備能力未確認：${unconfirmed.map(s => s.code || s.name).join('、')}。請先於步驟3逐項確認。`));
  const gen = async () => {
    await saveNow();
    const r = await api('POST', `/api/drafts/${S.draftId}/activities/suggest`); p.activities = r.activities; markDirty(); render();
  };
  const tb = h('span', { class: 'timebar ' + (timeTotal() === Number(p.basic.minutes) ? 'ok' : 'bad') }, `時間合計 ${timeTotal()}／${p.basic.minutes} 分`);
  wrap.append(h('div', { class: 'row space' }, h('button', { class: 'btn primary', onclick: gen, disabled: unconfirmed.length > 0 }, p.activities.length ? '重新產生教學活動（會覆蓋）' : '產生教學活動'), tb));
  const groups = p.groups.filter(g => g.studentKeys.length);
  const updTime = () => { tb.textContent = `時間合計 ${timeTotal()}／${p.basic.minutes} 分`; tb.className = 'timebar ' + (timeTotal() === Number(p.basic.minutes) ? 'ok' : 'bad'); };
  for (const a of p.activities) {
    a.groupSupport ||= {}; a.assessment ||= {};
    wrap.append(h('div', { class: 'goal' },
      h('div', { class: 'grid' }, h('label', {}, '活動階段', bind(a, 'phase', h('input', { value: a.phase }))), h('label', {}, '時間（分）', bind(a, 'minutes', h('input', { type: 'number', min: 0, value: a.minutes }), updTime))),
      h('label', {}, '教學活動內容', bind(a, 'content', h('textarea', { value: a.content, rows: 5 }))),
      h('label', {}, '教學資源', bind(a, 'resources', h('input', { value: a.resources || '' }))),
      h('div', { class: 'grid' }, ...groups.map(g => h('label', {}, `${g.name}支持`, bind(a.groupSupport, g.key, h('input', { value: a.groupSupport[g.key] || '' }))))),
      h('div', { class: 'grid' }, ...groups.map(g => h('label', {}, `${g.name}評量`, bind(a.assessment, g.key, h('input', { value: a.assessment[g.key] || '' }))))),
      h('button', { class: 'btn small danger', onclick: () => { p.activities = p.activities.filter(x => x !== a); markDirty(); render(); } }, '刪除此段')));
  }
  if (p.activities.length) wrap.append(h('button', { class: 'btn small', onclick: () => { p.activities.push({ id: uid(), phase: '', content: '', resources: '', minutes: 0, groupSupport: {}, assessment: {} }); markDirty(); render(); } }, '＋ 新增活動段落'));
  return wrap;
}

// ---------- 7. 預覽 ----------
function fieldsFromPlan() {
  const p = S.plan, b = p.basic, cur = p.curriculum;
  const items = (l) => l.map(x => `${x.code} ${x.teacherText || x.officialText}`).join('\n') || '待確認';
  const gl = [];
  for (const g of p.groups) { const gg = p.goals[g.key] || []; if (!g.studentKeys.length && !gg.length) continue; gl.push(`${g.name}目標`); gg.forEach((x, i) => gl.push(`${i + 1}.（${x.domain}）${x.text || composeGoal(x)}`)); }
  return { core: items(cur.core), focus: '學習表現：\n' + items(cur.performance) + '\n學習內容：\n' + items(cur.content), goals: gl.join('\n') || '待確認' };
}
function ed(obj, key, cls, opts = {}) {
  const td = h('td', { class: cls || '', contenteditable: 'true', 'aria-label': opts.label || key });
  td.textContent = obj[key] ?? ''; td.addEventListener('input', () => { obj[key] = opts.number ? Number(td.textContent) || 0 : td.textContent; markDirty(); });
  return td;
}
function stepPreview() {
  const p = S.plan, b = p.basic; p.previewed = true; markDirty();
  const f = fieldsFromPlan();
  const depts = [['kg', '幼兒園'], ['elem', '國小部'], ['jh', '國中部'], ['sh', '技高部']].map(([k, l]) => (k === b.dept ? '█' : '□') + l + (k === 'elem' ? '\n' : '')).join('');
  // 與 Word 相同的九欄網格（原檔欄寬，單位 pt）
  const W = [20.9, 22.5, 0.35, 48, 21.3, 63.7, 93.15, 148.85, 127.55], WT = W.reduce((x, y) => x + y);
  const t2 = h('table', { class: 'pv' }, h('colgroup', {}, ...W.map(w => h('col', { style: `width:${w / WT * 100}%` }))));
  const tr = (...c) => h('tr', {}, ...c);
  const lbl = (t, at = {}) => h('td', { class: 'lbl', ...at }, t);
  const span = (el, n) => { el.colSpan = n; return el; };
  t2.append(tr(lbl('教學日期', { colspan: 4 }), span(ed(b, 'dateText', 'c', { label: '教學日期' }), 3), lbl('教學者'), ed(b, 'teacher', 'c')));
  t2.append(tr(lbl('領域/科目名稱', { colspan: 4 }), span(ed(b, 'subjectLabel', 'c'), 3), lbl('單元名稱'), ed(b, 'unit', 'c')));
  t2.append(tr(lbl('教學總節數', { colspan: 4 }), ed(b, 'totalPeriods', 'c', { number: true }),
    h('td', { class: 'c', colspan: 2 }, '本節為第__', h('span', { contenteditable: 'true', oninput: (e) => { b.periodNo = Number(e.target.textContent) || ''; markDirty(); } }, String(b.periodNo || '')), '___節'),
    lbl('教學階段\n(年級/班級/組別)'), ed(b, 'stageText', 'c')));
  const order = {}; p.groups.forEach((g, i) => g.studentKeys.forEach(k => order[k] = i));
  const studs = p.students.filter(s => !s.excludeFromPlan).sort((a, c) => (order[a.key] ?? 99) - (order[c.key] ?? 99));
  const gname = (k) => (p.groups.find(g => g.studentKeys.includes(k))?.name || '').replace('組', '');
  t2.append(tr(lbl('學\n生\n先備能力\n分\n析', { rowspan: studs.length + 1 }), lbl('組別', { colspan: 2 }), lbl('姓名'), lbl('性別'), lbl('障礙\n類別'), lbl('與本單元教學相關之能力', { colspan: 3 })));
  for (const s of studs) t2.append(tr(h('td', { class: 'c', colspan: 2 }, gname(s.key)), ed(s, 'name', 'c'), ed(s, 'gender', 'c'), ed(s, 'disability', 'c'), span(ed(s, 'abilitySummary'), 3)));
  const ro = (t) => h('td', { colspan: 7, title: '請至「確認課綱」或「分組與目標」步驟修改，以維持官方原文追溯' }, t);
  t2.append(tr(lbl('課程\n架構', { colspan: 2 }), ro('')), tr(lbl('核心\n素養', { colspan: 2 }), ro(f.core)), tr(lbl('學習\n重點', { colspan: 2 }), ro(f.focus)),
    tr(lbl('議題\n融入', { colspan: 2 }), span(ed(p, 'issuesText'), 7)), tr(lbl('學習\n目標', { colspan: 2 }), ro(f.goals)));
  const t3 = h('table', { class: 'pv' }, h('colgroup', {}, ...[383.65, 48.7, 50.5, 62.9].map(w => h('col', { style: `width:${w / 545.75 * 100}%` }))),
    tr(h('th', {}, '教學活動'), h('th', {}, '教學\n資源'), h('th', {}, '教學\n時間'), h('th', { style: 'font-size:.75rem' }, '評量\n方式\n(需列出A、B、C組評量方式)')));
  for (const a of p.activities) {
    const content = h('td', {}, h('strong', {}, a.phase), h('div', { contenteditable: 'true', oninput: (e) => { a.content = e.target.innerText; markDirty(); } }, a.content),
      h('div', { class: 'hint' }, '【各組支持】' + Object.entries(a.groupSupport || {}).map(([k, v]) => `${k}組：${v}`).join('；')));
    t3.append(tr(content, ed(a, 'resources'), ed(a, 'minutes', 'c', { number: true }), h('td', {}, Object.entries(a.assessment || {}).map(([k, v]) => `${k}：${v}`).join('\n'))));
  }
  return h('div', { class: 'card' }, h('h1', { class: 'no-print' }, '7. 編輯預覽'),
    h('p', { class: 'hint no-print' }, '淡黃色欄位可直接修改；課綱與目標欄需回原步驟修改以保留官方原文追溯。預覽與 Word 使用相同表格結構；Word 的版面以匯出檔為準。'),
    h('div', { class: 'preview' }, h('div', { class: 'pv-head' }, h('div', { class: 'big' }, '臺北市立臺北特殊教育學校'), h('div', {}, depts), h('div', { class: 'big' }, '教學設計表')), t2, h('div', { style: 'height:.6rem' }), t3),
    h('div', { class: 'row no-print', style: 'margin-top:.6rem' }, h('button', { class: 'btn', onclick: () => window.print() }, '列印／另存 PDF（瀏覽器）')));
}

// ---------- 8. 匯出 ----------
async function stepExport() {
  await saveNow();
  const r = await api('GET', `/api/drafts/${S.draftId}/check`);
  const ack = h('input', { type: 'checkbox' });
  const dl = (ext) => async () => {
    if (r.issues.length && !ack.checked) return toast('請先勾選已了解提醒事項');
    await saveNow();
    const resp = await fetch(`/api/drafts/${S.draftId}/export.${ext}`, { credentials: 'same-origin' });
    if (!resp.ok) {
      const e = await resp.json().catch(() => ({}));
      if (resp.status === 503 && ext === 'pdf') { toast('此伺服器不提供 PDF 轉檔，已開啟預覽，請按「列印／另存 PDF」'); return go(6); }
      return toast(e.error || '匯出失敗');
    }
    const blob = await resp.blob(); const a = h('a', { href: URL.createObjectURL(blob), download: `北特教學設計表_${S.plan.basic.unit || '教案'}.${ext}` });
    document.body.append(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  };
  return h('div', { class: 'card' }, h('h1', {}, '8. 匯出'),
    r.issues.length ? h('div', { class: 'notice warn' }, h('strong', {}, '匯出前提醒：'), h('ul', {}, ...r.issues.map(i => h('li', {}, i))), h('label', { class: 'inline' }, ack, '我已了解，仍要匯出')) : h('div', { class: 'notice' }, '檢核通過：學生先備能力已確認、教學時間合計符合課時。'),
    h('div', { class: 'row' }, h('button', { class: 'btn primary', onclick: dl('docx') }, '下載 Word（可編輯）'), h('button', { class: 'btn', onclick: dl('pdf') }, '下載 PDF'),
      h('button', { class: 'btn', onclick: () => go(6) }, '回預覽列印')),
    h('div', { class: 'notice warn' }, '本教案與學生資料將於今晚 24:00 後自動刪除，請務必現在下載。下載的 Word 檔可在自己的電腦上繼續修改。'),
    h('p', { class: 'hint' }, 'Word 依北特「教學設計表」原始版型產生。匯出檔含學生資料，請存放於個人電腦並妥善保管。'));
}

boot();
