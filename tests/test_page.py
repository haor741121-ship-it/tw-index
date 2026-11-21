"""台股即時指數網頁：自動化功能測試（按鈕、下載、複製、導覽、即時／快照兩種情境）

用法：python3 test_page.py index.html [輸出資料夾]
需要：Python Playwright；Chrome 位於 /usr/bin/google-chrome（或設定 CHROME 環境變數）
做法：用 page.route 攔截鉅亨網與 FinMind 的請求，回傳和真實 API 同格式的模擬資料，
      所以不需要網路也能完整測試。結束時印出每一項 PASS/FAIL，任何 FAIL 會以 exit code 1 結束。
"""
import asyncio, json, math, os, re, sys, datetime
from playwright.async_api import async_playwright

HTML = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'index.html')
OUT = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(HTML)); os.makedirs(OUT, exist_ok=True)
CHROME = os.environ.get('CHROME', '/usr/bin/google-chrome')

src = open(HTML, encoding='utf-8').read()
SNAP = json.loads(re.search(r'<script id="snapshot"[^>]*>(.*?)</script>', src, re.S).group(1))


def ts(d):
    return int(datetime.datetime.fromisoformat(d + 'T00:00:00+08:00').timestamp())


recent = SNAP['recent']
last = recent[-1]
QUOTE = {"statusCode": 200, "data": [
    {"0": "TWS:TSE01:INDEX", "6": SNAP['taiex']['close'], "21": SNAP['taiex']['prev'], "19": SNAP['taiex'].get('open'),
     "12": SNAP['taiex'].get('high'), "13": SNAP['taiex'].get('low'), "200007": ts(last['d']) + 13 * 3600 + 33 * 60},
    {"0": "TWS:OTC01:INDEX", "6": 263.31, "21": 285.33, "200007": ts(last['d']) + 13 * 3600 + 33 * 60}]}
start = ts(last['d']) + 9 * 3600
MIN = {"data": {"t": [start + 60 * i for i in range(271)][::-1],
                "c": [round(SNAP['taiex']['prev'] - 1500 * i / 270 + 100 * math.sin(i / 9), 2) for i in range(271)][::-1]}}
DAY = {"data": {"t": [ts(r['d']) for r in recent][::-1], "c": [r['c'] for r in recent][::-1]}}
FX = {"data": {"t": [ts(r['d']) for r in recent if r.get('fx')][::-1], "c": [r['fx'] for r in recent if r.get('fx')][::-1]}}
ch = SNAP.get('chips', {})
inst_rows = []
for r in ch.get('inst', []):
    for name, v in (("Foreign_Investor", r['f']), ("Investment_Trust", r['t']), ("Dealer_self", r['p']), ("total", r['s'])):
        inst_rows.append({"date": r['d'], "name": name, "buy": max(v, 0) * 1e8, "sell": max(-v, 0) * 1e8})
margin_rows = []
for r in ch.get('margin', []):
    margin_rows.append({"date": r['d'], "name": "MarginPurchaseMoney", "TodayBalance": r['m'] * 1e8})
    margin_rows.append({"date": r['d'], "name": "ShortSale", "TodayBalance": r['s']})
fut_rows = [{"date": r['d'], "institutional_investors": "外資", "long_open_interest_balance_volume": 10000,
             "short_open_interest_balance_volume": 10000 - r['n']} for r in ch.get('fut', [])]
price_rows = [{"date": r['d'], "close": r['c'], "open": r['c'], "max": r['c'], "min": r['c']} for r in recent[-5:]]

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))


async def scenario(p, mode):
    b = await p.chromium.launch(executable_path=CHROME)
    ctx = await b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, accept_downloads=True)
    await ctx.grant_permissions(['clipboard-read', 'clipboard-write'])
    pg = await ctx.new_page()
    errs, calls = [], {'n': 0}

    async def h(route):
        u = route.request.url
        calls['n'] += 1
        if mode in ('fail', 'csp'):
            return await route.abort()
        body = None
        if 'quote/quotes' in u: body = QUOTE
        elif 'resolution=1' in u: body = MIN
        elif 'FX:USDTWD' in u: body = FX
        elif 'resolution=D' in u: body = DAY
        elif 'TaiwanStockTotalInstitutionalInvestors' in u: body = {"data": inst_rows}
        elif 'TaiwanStockTotalMarginPurchaseShortSale' in u: body = {"data": margin_rows}
        elif 'TaiwanFuturesInstitutionalInvestors' in u: body = {"data": fut_rows}
        elif 'TaiwanStockPrice' in u: body = {"data": price_rows}
        if body is None:
            return await route.abort()
        await route.fulfill(status=200, content_type='application/json',
                            headers={'access-control-allow-origin': '*'}, body=json.dumps(body))

    await ctx.route('https://**/*', h)
    pg.on('pageerror', lambda e: errs.append(str(e)))
    target = HTML
    if mode == 'csp':
        # 模擬 Claude App／預覽：用 CSP 禁止所有對外連線
        target = os.path.join(OUT, '_csp_test.html')
        open(target, 'w', encoding='utf-8').write(src.replace('<head>', '<head><meta http-equiv="Content-Security-Policy" content="connect-src \'none\'">', 1))
    await pg.goto('file://' + target)
    await pg.wait_for_timeout(1500)
    tag = f'[{mode}] '

    price = await pg.inner_text('#price')
    check(tag + '指數數字有顯示', re.search(r'\d', price), price)
    pill = await pg.inner_text('#modePill')
    check(tag + '模式標籤正確', (pill == '快照') if mode != 'live' else (pill != '快照' and pill != '載入中'), pill)
    check(tag + '近一個月走勢圖有顯示', not await pg.eval_on_selector('#dailyWrap', 'e=>e.hidden'))
    paths = await pg.eval_on_selector_all('#daily svg path', 'es=>es.length')
    check(tag + '走勢圖有加權與匯率兩條線', paths >= 2, f'{paths} 條')
    if mode == 'live':
        check(tag + '盤中走勢有顯示', not await pg.eval_on_selector('#intraWrap', 'e=>e.hidden'))
        it = await pg.inner_text('#intraTitle')
        md_ = last['d'][5:].replace('-', '/')
        today_ = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d')
        check(tag + '盤中走勢標題標示日期（非今日時註明）', md_ in it and (('非今日' in it) if last['d'] != today_ else ('非今日' not in it)), it)
    for tid, label in (('instTbl', '三大法人'), ('marginTbl', '融資融券'), ('futTbl', '期貨淨口數')):
        n = await pg.eval_on_selector_all(f'#{tid} tr', 'es=>es.length')
        check(tag + f'{label}表格有資料', n >= 4, f'{n} 列')
    cm = await pg.inner_text('#chipsMode')
    check(tag + '籌碼資料來源標示', ('即時' in cm) if mode == 'live' else ('快照' in cm), cm)
    lag = (await pg.inner_text('#marginLag')).strip() if await pg.is_visible('#marginLag') else ''
    il, ml = (ch.get('inst') or [{}])[-1].get('d', ''), (ch.get('margin') or [{}])[-1].get('d', '')
    ms_missing = (ch.get('margin') or [{}])[-1].get('s') is None
    check(tag + '融資融券落後一天時有標示', ('晚上 9 點' in lag) if (ml and il and ml < il) else (('融券餘額尚未取得' in lag) if ms_missing else lag == ''), lag or '（無標示）')
    # 融券缺值時不可算出假的增減（缺值不能被當成 0）
    r1 = await pg.eval_on_selector_all('#marginTbl tr:nth-child(2) td', 'es=>es.map(e=>e.textContent)')
    if ms_missing:
        check(tag + '融券缺值時餘額與增減都顯示「—」', len(r1) == 5 and r1[3] == '—' and r1[4] == '—', ' | '.join(r1))
    else:
        check(tag + '融券增減有數值', len(r1) == 5 and r1[4] != '—', ' | '.join(r1))
    # 390px 寬度：三張籌碼表不需左右滑動就能看完所有欄位
    for tid in ('instTbl', 'marginTbl', 'futTbl'):
        sw_ = await pg.eval_on_selector(f'#{tid}', 'e=>[e.scrollWidth, e.parentNode.clientWidth]')
        check(tag + f'{tid} 在 390px 寬度完整顯示', sw_[0] <= sw_[1] + 1, f'{sw_[0]}/{sw_[1]}px')
    asof = await pg.inner_text('#asof')
    check(tag + '指數卡片標示資料時間', ('抓取於' in asof) if mode == 'live' else ('快照時間 ' + SNAP['updated'] in asof), asof)
    # 週末／盤前休市說明
    tw_ = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    mk = (await pg.inner_text('#mktNote')).strip() if await pg.is_visible('#mktNote') else ''
    tdl_ = last['d'][5:].replace('-', '/')
    if tw_.weekday() >= 5:
        check(tag + '週末顯示休市說明與最近交易日', '休市' in mk and tdl_ in mk and ('週六' if tw_.weekday() == 5 else '週日') in mk, mk)
    elif tw_.hour < 9 and last['d'] != tw_.strftime('%Y-%m-%d'):
        check(tag + '盤前顯示尚未開盤說明', '尚未開盤' in mk and tdl_ in mk, mk)
    else:
        check(tag + '交易日不顯示休市說明', '休市' not in mk, mk or '（無）')
    mt = await pg.inner_text('#modeText')
    if mode == 'csp':
        check(tag + '在 Claude App 環境說明「不能連外」而不是「連線失敗」', '不能連外' in mt and '失敗' not in mt, mt)
    if mode == 'fail':
        check(tag + '斷線時提示可重試', '連不上' in mt, mt)
    check(tag + '快照有標示時間', mode == 'live' or SNAP['updated'] in mt, mt)

    # 重新整理按鈕位置：在頁面最上方（標題列）
    rb = await pg.eval_on_selector('#refreshBtn', 'e=>{const r=e.getBoundingClientRect();return [r.top, r.right]}')
    check(tag + '重新整理按鈕位於頁面最上方', rb[0] < 100 and rb[1] <= 390, f'top={rb[0]:.0f}')

    # 分析圖表
    ns = await pg.eval_on_selector_all('#anaStats .stat', 'es=>es.length')
    check(tag + '分析：統計卡片有顯示', ns >= 6, f'{ns} 張')
    mp = await pg.eval_on_selector_all('#maChart svg path', 'es=>es.length')
    check(tag + '分析：均線圖有收盤＋兩條均線', mp >= 3, f'{mp} 條')
    ir = await pg.eval_on_selector_all('#instChart svg rect', 'es=>es.length')
    idots = await pg.eval_on_selector_all('#instChart svg circle', 'es=>es.length')
    check(tag + '分析：三大法人長條圖有資料', ir >= 10 and idots >= 4, f'{ir} 段、{idots} 點')
    fr = await pg.eval_on_selector_all('#futChart svg rect', 'es=>es.length')
    check(tag + '分析：期貨淨口數長條圖有資料', fr >= 4, f'{fr} 根')
    fills = await pg.eval_on_selector_all('#futChart svg rect', 'es=>es.map(e=>e.getAttribute("fill"))')
    fu, fd = fills.count('var(--up)'), fills.count('var(--down)')
    fdiff = [b2['n'] - a2['n'] for a2, b2 in zip(ch.get('fut', [])[:-1], ch.get('fut', [])[1:])][-10:]
    check(tag + '分析：期貨日增減長條紅漲綠跌', fu == sum(1 for x in fdiff if x > 0) and fd == sum(1 for x in fdiff if x < 0), f'紅 {fu}／綠 {fd}')
    frd = await pg.inner_text('#futRead')
    check(tag + '分析：期貨讀數同時顯示增減與當日淨口數', '增減' in frd and '當日淨口數' in frd and '口' in frd, frd)
    mg = await pg.eval_on_selector_all('#mgChart svg circle', 'es=>es.length')
    check(tag + '分析：融資餘額圖有資料', mg >= 4, f'{mg} 點')
    for cid, rid in (('maChart', 'maRead'), ('instChart', 'instRead'), ('futChart', 'futRead'), ('mgChart', 'mgRead')):
        r0 = await pg.inner_text('#' + rid)
        await pg.locator(f'#{cid} svg').scroll_into_view_if_needed()
        box = await pg.locator(f'#{cid} svg').bounding_box()
        await pg.mouse.click(box['x'] + box['width'] * 0.2, box['y'] + box['height'] * 0.5)
        await pg.wait_for_timeout(100)
        r1 = await pg.inner_text('#' + rid)
        gd = await pg.eval_on_selector(f'#{cid} .guide', 'e=>e.style.display')
        check(tag + f'分析：點 {cid} 會切換日期數值', r1 != r0 and re.match(r'\d{2}/\d{2}', r1) and gd != 'none', f'{r0[:12]} → {r1[:12]}')
    await pg.evaluate('window.scrollTo(0,0)')

    # 重新整理按鈕
    before = calls['n']
    await pg.click('#refreshBtn')
    await pg.wait_for_timeout(1500)
    toast = await pg.inner_text('#toast')
    if mode != 'csp':
        check(tag + '重新整理：按得下去且有發出請求', calls['n'] > before, f'{calls["n"] - before} 個請求')
    check(tag + '重新整理：有回饋訊息', ('已更新' in toast) if mode == 'live' else ('快照' in toast), toast)
    check(tag + '重新整理：按鈕恢復可按', await pg.is_enabled('#refreshBtn'))
    lc = await pg.inner_text('#lastChk')
    exp = '（即時）' if mode == 'live' else ('不能連外' if mode == 'csp' else '未連上')
    check(tag + '重新整理：旁邊顯示「上次檢查 HH:MM」與結果', re.search(r'上次檢查 \d{2}:\d{2}', lc) and exp in lc, lc)

    # 導覽列
    for href in ('#idx', '#trend', '#chips', '#ana', '#src', '#install', '#iter'):
        await pg.click(f'nav a[href="{href}"]')
        await pg.wait_for_timeout(250)
        top = await pg.eval_on_selector(href, 'e=>e.getBoundingClientRect().top')
        check(tag + f'導覽 {href} 可跳轉', -5 <= top <= 140, f'top={top:.0f}')

    # 下載按鈕
    async with pg.expect_download(timeout=5000) as dl_info:
        await pg.click('#dlBtn')
    dl = await dl_info.value
    path = os.path.join(OUT, f'downloaded_{mode}.html')
    await dl.save_as(path)
    got = open(path, encoding='utf-8').read()
    check(tag + '下載：檔名正確', dl.suggested_filename == 'tw-index.html', dl.suggested_filename)
    check(tag + '下載：內容完整', got.count('data-keep') >= 3 and 'id="snapshot"' in got and 'id="iterlog"' in got)
    check(tag + '下載：沒有夾帶已渲染的資料', '<tr>' not in got.split('id="instTbl"')[1][:30])
    # 下載的檔案本身能開、能跑
    pg2 = await ctx.new_page()
    e2 = []
    pg2.on('pageerror', lambda e: e2.append(str(e)))
    await pg2.goto('file://' + os.path.abspath(path))
    await pg2.wait_for_timeout(1200)
    check(tag + '下載的檔案可正常開啟執行', not e2 and re.search(r'\d', await pg2.inner_text('#price')), '; '.join(e2))
    await pg2.close()

    # 複製按鈕
    await pg.click('#copyBtn')
    await pg.wait_for_timeout(400)
    try:
        clip = await pg.evaluate('navigator.clipboard.readText()')
    except Exception as e:
        clip = ''
    check(tag + '複製原始碼：剪貼簿內容正確', clip.startswith('<!DOCTYPE html>') and 'id="snapshot"' in clip, f'{len(clip)} 字')

    # 迭代紀錄
    n = await pg.eval_on_selector_all('#logList .when', 'es=>es.length')
    check(tag + '迭代紀錄有顯示且有日期時間', n >= 1 and re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', await pg.inner_text('#logList .when')))
    # 迭代紀錄收合
    st = await pg.eval_on_selector_all('#logList details.entry', 'ds=>ds.map(d=>d.open)')
    check(tag + '迭代紀錄：每筆可收合，只有最新一筆預設展開', len(st) == n and st[:1] == [True] and not any(st[1:]), f'{sum(st)}/{len(st)} 展開')
    await pg.click('#logList details.entry:nth-of-type(1) > summary')
    await pg.wait_for_timeout(150)
    o1 = await pg.eval_on_selector('#logList details.entry', 'd=>d.open')
    vis = await pg.eval_on_selector('#logList details.entry', 'd=>d.offsetHeight - d.querySelector("summary").offsetHeight')
    check(tag + '迭代紀錄：點標題可收合最新一筆', o1 is False and vis <= 2, f'open={o1}, 內容高 {vis}px')
    if len(st) > 1:
        await pg.click('#logList details.entry:nth-of-type(2) > summary')
        await pg.wait_for_timeout(150)
        o2 = await pg.eval_on_selector('#logList details.entry:nth-of-type(2)', 'd=>d.open')
        check(tag + '迭代紀錄：點標題可展開較早一筆', o2 is True, f'open={o2}')
    await pg.click('#logToggle')
    await pg.wait_for_timeout(150)
    st2 = await pg.eval_on_selector_all('#logList details.entry', 'ds=>ds.map(d=>d.open)')
    lb2 = await pg.inner_text('#logToggle')
    check(tag + '迭代紀錄：「全部展開」按鈕展開全部', all(st2) and lb2 == '全部收合', f'{sum(st2)}/{len(st2)}，按鈕={lb2}')
    await pg.click('#logToggle')
    await pg.wait_for_timeout(150)
    st3 = await pg.eval_on_selector_all('#logList details.entry', 'ds=>ds.map(d=>d.open)')
    lb3 = await pg.inner_text('#logToggle')
    check(tag + '迭代紀錄：「全部收合」按鈕收合全部', not any(st3) and lb3 == '全部展開', f'{sum(st3)}/{len(st3)}，按鈕={lb3}')
    tb = await pg.eval_on_selector('#logToggle', 'e=>{var r=e.getBoundingClientRect();return [r.right, r.height]}')
    check(tag + '迭代紀錄：收合按鈕在 390px 內完整顯示', tb[0] <= 390 and tb[1] >= 24, f'right={tb[0]:.0f}')
    # 版面不溢出
    ov = await pg.evaluate('document.documentElement.scrollWidth - window.innerWidth')
    check(tag + '手機寬度不會左右溢出', ov <= 1, f'{ov}px')
    us = await pg.inner_text('#updState')
    check(tag + '自動更新：連不上 GitHub 時顯示原因、不影響頁面', '無法檢查更新' in us, us)
    check(tag + '沒有 JavaScript 錯誤', not errs, '; '.join(errs))

    await pg.evaluate('window.scrollTo(0,0)')
    await pg.screenshot(path=os.path.join(OUT, f'shot_{mode}.png'), full_page=True)
    await b.close()


async def update_scenario(p, newer):
    """下載的網頁檔自動更新：模擬 GitHub 上有更新版（newer=True）或同版（newer=False）"""
    tag = '[更新-' + ('有新版' if newer else '同版') + '] '
    remote = src
    if newer:
        remote = re.sub(r'("version":\s*")v[\d.]+', r'\1v99.0', remote, count=1).replace('<h1>台股即時指數</h1>', '<h1>台股即時指數<span id="newMark">NEW</span></h1>', 1)
    b = await p.chromium.launch(executable_path=CHROME)
    ctx = await b.new_context(viewport={'width': 390, 'height': 844})
    pg = await ctx.new_page()
    errs, hits = [], {'raw': 0}

    async def h(route):
        u = route.request.url
        if 'raw.githubusercontent.com/haor741121-ship-it/tw-index/main/index.html' in u:
            hits['raw'] += 1
            return await route.fulfill(status=200, content_type='text/plain', headers={'access-control-allow-origin': '*'}, body=remote)
        return await route.abort()

    await ctx.route('https://**/*', h)
    pg.on('pageerror', lambda e: errs.append(str(e)))
    await pg.goto('file://' + HTML)
    await pg.wait_for_timeout(2500)
    us = await pg.inner_text('#updState')
    if newer:
        mark = await pg.query_selector('#newMark')
        check(tag + '打開下載檔會自動換成 GitHub 上的新版', mark is not None and 'v99.0' in us, us)
        check(tag + '換版後不會一直重複檢查（只抓 1 次）', hits['raw'] == 1, f"{hits['raw']} 次")
        check(tag + '換版後頁面仍正常顯示指數與迭代紀錄', re.search(r'\d', await pg.inner_text('#price')) and await pg.eval_on_selector_all('#logList details.entry', 'ds=>ds.length') >= 1)
        await pg.click('#refreshBtn'); await pg.wait_for_timeout(800)
        check(tag + '換版後重新整理按鈕可用', await pg.is_enabled('#refreshBtn'))
    else:
        check(tag + '同版時不換頁並顯示「已是最新版」', '已是最新版' in us and await pg.query_selector('#newMark') is None, us)
    check(tag + '沒有 JavaScript 錯誤', not errs, '; '.join(errs))
    await b.close()


async def main():
    check('原始檔只有一個 doctype（沒有多包一層外框）', len(re.findall(r'^<!doctype', src, re.I | re.M)) == 1 and src.lstrip().lower().startswith('<!doctype html>\n<html'))
    check('原始檔結尾沒有多餘的 </body></html>', src.rstrip().endswith('</html>') and len(re.findall(r'^</body>', src, re.M)) == 1)
    async with async_playwright() as p:
        for m in ('live', 'fail', 'csp'):
            await scenario(p, m)
        await update_scenario(p, True)
        await update_scenario(p, False)
    fails = 0
    for n, ok, d in results:
        print(('PASS ' if ok else 'FAIL ') + n + (f'（{d}）' if d else ''))
        fails += (not ok)
    print(f'\n共 {len(results)} 項，失敗 {fails} 項')
    sys.exit(1 if fails else 0)

asyncio.run(main())
