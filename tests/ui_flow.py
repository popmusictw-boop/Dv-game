"""手機／平板端到端操作測試（Playwright）：登入→基本資料→上傳→確認能力→課綱→分組目標→生成→預覽→匯出。
用法：python tests/ui_flow.py http://127.0.0.1:5055 帳號 密碼 輸出資料夾 [mobile|tablet]
使用 tests/fixtures 中的「虛構」測試資料（非真實學生）。"""
import sys, os, re
from playwright.sync_api import sync_playwright

BASE, USER, PW, OUT = sys.argv[1:5]
MODE = sys.argv[5] if len(sys.argv) > 5 else 'mobile'
FIX = os.path.join(os.path.dirname(__file__), 'fixtures')
os.makedirs(OUT, exist_ok=True)
errors = []

def shot(page, name):
    page.screenshot(path=os.path.join(OUT, f'{MODE}_{name}.png'), full_page=True)

with sync_playwright() as p:
    b = p.chromium.launch()
    vp = dict(width=390, height=844) if MODE == 'mobile' else dict(width=820, height=1180)
    ctx = b.new_context(viewport=vp, device_scale_factor=2 if MODE == 'mobile' else 1, has_touch=True, is_mobile=(MODE == 'mobile'), accept_downloads=True, locale='zh-TW')
    page = ctx.new_page()
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('dialog', lambda d: d.accept())
    page.goto(BASE)
    page.fill('input[name=username]', USER); page.fill('input[name=password]', PW)
    page.click('button[type=submit]')
    page.wait_for_selector('#btnNew'); page.click('#btnNew')
    page.wait_for_selector('#stepBody select')
    # 1 基本資料
    page.select_option('select[aria-label=部別]', 'sh')
    page.fill('input[aria-label=班級]', '高三餐飲A組')
    page.select_option('select[aria-label=科別]', '餐飲服務科')
    opts = page.eval_on_selector_all('select[aria-label="領域／科目"] option', 'os => os.map(o => o.textContent)')
    assert '食材處理實作' in opts and '車輛外部清理實作' not in opts, '技高部科別篩選技能領域失敗'
    assert '餐飲服務禮儀實作' in opts and '居家點心實作' not in opts, '本校科目依科別篩選失敗'
    page.select_option('select[aria-label="領域／科目"]', 'sch:餐飲服務禮儀實作')
    page.wait_for_selector('select[aria-label=教學大綱單元]')
    page.select_option('select[aria-label=教學大綱單元]', label='（四）接待禮儀')
    assert page.input_value('input[placeholder="例：上課好好坐"]') == '接待禮儀'
    shot(page, '1a_school_course')
    page.select_option('select[aria-label="領域／科目"]', 'sn:社會技巧')
    page.fill('input[placeholder="例：上課好好坐"]', '上課好好坐')
    shot(page, '1_basic')
    page.click('#btnNext')
    # 2 上傳
    page.wait_for_selector('text=資料處理說明')
    for code, fn in (('甲', '虛構學生甲_觀察紀錄.txt'), ('乙', '虛構學生乙_評量紀錄.txt'), ('丙', '虛構學生丙_IEP摘要.txt')):
        page.fill('input[placeholder^="學生姓名或代號"]', code); page.click('text=＋ 新增學生')
        page.wait_for_selector(f'.student h2:text-is("{code}")')
        card = page.locator('.student', has=page.locator(f'h2:text-is("{code}")'))
        card.locator('input[type=file]').set_input_files(os.path.join(FIX, fn))
        page.wait_for_selector(f'text={fn}'); page.wait_for_timeout(1000)  # 等上傳後畫面更新完成
    shot(page, '2_upload')
    page.click('#btnNext')
    # 3 先備能力
    page.wait_for_selector('text=確認先備能力')
    for i in range(3):
        btn = page.locator('.student button:text-is("擷取分析")').first
        btn.click(); page.wait_for_timeout(800)
    assert page.locator('.student button:text-is("擷取分析")').count() == 0, '仍有學生未分析'
    page.wait_for_selector('.ability')
    # 逐項確認
    while True:
        boxes = page.locator('.ability label.inline:has-text("已確認") input:not(:checked)')
        if boxes.count() == 0: break
        boxes.first.click(); page.wait_for_timeout(250)
    while page.locator('label.inline:has-text("我已逐項檢視") input:not(:checked)').count():
        page.locator('label.inline:has-text("我已逐項檢視") input:not(:checked)').first.click(); page.wait_for_timeout(400)
    shot(page, '3_abilities')
    page.click('#btnNext')
    # 4 課綱
    page.wait_for_selector('.cols3')
    cols = page.locator('.cols3 > div')
    for ci, n in ((0, 1), (1, 2), (2, 2)):
        for k in range(n):
            cols.nth(ci).locator('.cur-item input[type=checkbox]').nth(k).click(); page.wait_for_timeout(700)
    page.fill('textarea >> nth=-1', '品德教育（議題學習主題代碼待教師依手冊填寫）')
    shot(page, '4_curriculum')
    assert page.locator('.sel-item').count() == 5
    # 跨領域檢核：回第1步改領域，應出現檢核視窗
    page.click('.stepper button >> nth=0'); page.wait_for_selector('select[aria-label="領域／科目"]')
    page.select_option('select[aria-label="領域／科目"]', 'sn:生活管理')
    page.wait_for_selector('text=已選課綱項目需要重新檢核')
    shot(page, '1b_revalidate')
    page.click('text=稍後在課綱步驟處理')
    page.select_option('select[aria-label="領域／科目"]', 'sn:社會技巧')
    page.wait_for_timeout(800)
    if page.locator('dialog[open]').count(): page.click('text=稍後在課綱步驟處理')
    page.click('.stepper button >> nth=4')
    # 5 分組與目標
    page.wait_for_selector('text=依佐證建議分組'); page.click('text=依佐證建議分組'); page.wait_for_timeout(600)
    page.click('text=產生目標建議'); page.wait_for_selector('.goal .composed')
    shot(page, '5_groups_goals')
    page.click('#btnNext')
    # 6 生成
    page.wait_for_selector('text=產生教學活動'); page.click('text=產生教學活動'); page.wait_for_selector('.timebar.ok')
    shot(page, '6_generate')
    page.click('#btnNext')
    # 7 預覽
    page.wait_for_selector('table.pv'); shot(page, '7_preview')
    page.click('#btnNext')
    # 8 匯出
    page.wait_for_selector('button:has-text("下載 Word")')
    with page.expect_download() as d: page.click('button:has-text("下載 Word（可編輯）")')
    d.value.save_as(os.path.join(OUT, f'{MODE}_export.docx'))
    with page.expect_download(timeout=120000) as d: page.click('button:has-text("下載 PDF")')
    d.value.save_as(os.path.join(OUT, f'{MODE}_export.pdf'))
    shot(page, '8_export')
    b.close()
print('UI flow OK', MODE)
print('console errors:', errors)
