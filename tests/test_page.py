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
    {"0": "TWS:OTC01:INDEX", "6": SNAP['otc']['close'], "21": SNAP['otc']['prev'], "200007": ts(last['d']) + 13 * 3600 + 33 * 60}]}
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
    fxl = await pg.inner_text('#fxLag') if not await pg.eval_on_selector('#fxLag', 'e=>e.hidden') else ''
    lfx = [r for r in recent if r.get('fx') is not None]
    if recent[-1].get('fx') is None and lfx:
        check(tag + '最新一天匯率缺值時有標示', '匯率尚未取得' in fxl and recent[-1]['d'][5:].replace('-', '/') in fxl and lfx[-1]['d'][5:].replace('-', '/') in fxl, fxl or '（無標示）')
    else:
        check(tag + '匯率齊全時不顯示缺值標示', fxl == '', fxl or '（無）')
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
    # 國定假日休市說明（用固定日期呼叫頁面的判斷函式）
    hn = await pg.evaluate("window.__twMktNote({date:'2026-12-25',wd:'Fri',mins:600}, '2026-12-24')")
    check(tag + '國定假日（12/25 行憲紀念日）顯示休市說明', '休市' in hn and '行憲紀念日' in hn and '12/24（週四）' in hn, hn)
    wn = await pg.evaluate("window.__twMktNote({date:'2026-12-24',wd:'Thu',mins:600}, '2026-12-24')")
    check(tag + '一般交易日盤中不顯示休市說明', wn == '', wn or '（無）')
    pn = await pg.evaluate("window.__twMktNote({date:'2026-12-28',wd:'Mon',mins:480}, '2026-12-24')")
    check(tag + '假日後盤前顯示尚未開盤', '尚未開盤' in pn and '12/24' in pn, pn)
    sn = await pg.evaluate("[window.__twMktNote({date:'2026-11-24',wd:'Tue',mins:600}, '2026-11-23'), window.__twMktNote({date:'2026-11-24',wd:'Tue',mins:900}, '2026-11-23')]")
    check(tag + '交易日盤中畫面仍是前一交易日時標示非今日', all('非今日' in s and '11/23（週一）' in s and '休市' not in s for s in sn), ' / '.join(sn))
    yn = await pg.evaluate("window.__twMktNote({date:'2027-01-01',wd:'Fri',mins:600}, '2026-12-31')")
    check(tag + '2027 元旦顯示休市說明', '休市' in yn and '元旦' in yn and '12/31（週四）' in yn, yn)

    # 最上方：台股目前走勢分析
    otag = await pg.inner_text('#olkTag')
    check(tag + '走勢分析：顯示綜合判斷', otag in ('偏多', '震盪偏多', '區間震盪', '震盪偏空', '偏空'), otag)
    olis = await pg.eval_on_selector_all('#olkList li', 'es=>es.map(e=>e.querySelector(".k").textContent+"|"+e.querySelector(".s").textContent)')
    ks = [x.split('|')[0] for x in olis]
    check(tag + '走勢分析：列出今日、均線、近一個月、外資現貨、外資期貨、融資維持率 6 項', ks == ['今日', '均線位置', '近一個月', '外資現貨', '外資期貨', '融資維持率'], ','.join(ks))
    check(tag + '走勢分析：每項都有偏多／偏空／中性標示', all(x.split('|')[1] in ('偏多', '偏空', '中性') for x in olis), str(len(olis)))
    osc = await pg.inner_text('#olkScore')
    np_ = sum(1 for x in olis if x.endswith('偏多')); nn_ = sum(1 for x in olis if x.endswith('偏空'))
    sc_ = np_ - nn_
    exp_ = ('偏多' if sc_ >= 3 else '震盪偏多') if sc_ > 0 else (('偏空' if sc_ <= -3 else '震盪偏空') if sc_ < 0 else '區間震盪')
    check(tag + '走勢分析：偏多／偏空項數與判斷一致', f'{np_} 項偏多、{nn_} 項偏空' in osc and otag == exp_, f'{osc}｜{otag}')
    ov = await pg.inner_text('#olkView')
    check(tag + '走勢分析：顯示排程觀察與時間', ('排程觀察' in ov and SNAP['view']['asof'] in ov) if SNAP.get('view') else True, ov[:40])
    nws = SNAP.get('news', {}).get('items', [])
    nli = await pg.eval_on_selector_all('#olkNews li', 'es=>es.map(e=>e.querySelector(".s").textContent+"|"+e.querySelector("small").textContent)')
    check(tag + '消息面：國內外新聞、政策、能源逐項顯示', len(nli) == len(nws) and len(nws) >= 3, f'{len(nli)} 則')
    grps = await pg.eval_on_selector_all('#olkNews .grp', 'es=>es.map(e=>e.textContent)')
    check(tag + '消息面：分成國內、國際、能源三組', grps == ['國內新聞與政策', '國際新聞與政策', '能源'], ','.join(grps))
    check(tag + '消息面：每則有利多／利空／中性與日期來源', all(x.split('|')[0] in ('利多', '利空', '中性') and '｜' in x.split('|', 1)[1] for x in nli), str(nli[:1]))
    nh = await pg.inner_text('#olkNews h3')
    nu = sum(1 for x in nws if x['dir'] == '利多'); nd = sum(1 for x in nws if x['dir'] == '利空')
    check(tag + '消息面：標題顯示整理時間與利多利空項數', SNAP['news']['asof'] in nh and f'{nu} 項利多、{nd} 項利空' in nh, nh)
    nnew = sum(1 for x in nws if x.get('new'))
    nbad = await pg.eval_on_selector_all('#olkNews .nw', 'es=>es.length')
    check(tag + '消息面：本輪新增的消息有「新」標記且標題顯示新增則數', nbad == nnew and ((f'本輪新增 {nnew} 則' in nh) if nnew else ('本輪新增' not in nh)), f'{nbad}/{nnew}')
    esr = await pg.evaluate("window.__twEsc('<b>A&B\"</b>')")
    check(tag + '消息面：快照文字會跳脫 HTML 特殊字元', esr == '&lt;b&gt;A&amp;B&quot;&lt;/b&gt;', esr)
    nwr = await pg.eval_on_selector('#olkNews', 'e=>e.getBoundingClientRect().right')
    check(tag + '消息面：390px 內完整顯示', nwr <= 390, f'right={nwr:.0f}')
    otag2 = await pg.evaluate("""(()=>{ var s=document.getElementById('olkScore').textContent; return s; })()""")
    check(tag + '消息面：不列入 6 項自動判斷', '依 6 項指標' in otag2, otag2)
    otop = await pg.eval_on_selector('#outlook', 'e=>e.getBoundingClientRect().top')
    itop = await pg.eval_on_selector('#idx', 'e=>e.getBoundingClientRect().top')
    check(tag + '走勢分析：位在加權指數上方（頁面最上面）', otop < itop, f'{otop:.0f} < {itop:.0f}')
    ow = await pg.eval_on_selector('#olkCard', 'e=>e.getBoundingClientRect().right')
    check(tag + '走勢分析：390px 內完整顯示', ow <= 390, f'right={ow:.0f}')
    # 加權指數上方的更新頻率說明
    fq = await pg.inner_text('#freqNote')
    check(tag + '更新頻率：加權指數上方說明每 5 小時與盤中 30 秒', '每 5 小時' in fq and '30 秒' in fq and re.search(r'下次約 \d{2}/\d{2}（週.）\d{2}:\d{2}', fq), fq[-40:])
    ftop = await pg.eval_on_selector('#freqNote', 'e=>e.getBoundingClientRect().top')
    htop = await pg.eval_on_selector('#hero', 'e=>e.getBoundingClientRect().top')
    check(tag + '更新頻率：說明在加權指數卡片上方', ftop < htop, f'{ftop:.0f} < {htop:.0f}')
    ns = await pg.evaluate("""[window.__twNextSnap({date:'2026-11-23',mins:1341}), window.__twNextSnap({date:'2026-11-27',mins:1300}), window.__twNextSnap({date:'2026-12-24',mins:1300}), window.__twNextSnap({date:'2026-11-24',mins:600})]""")
    got = [(x['d'], x['hm']) for x in ns]
    check(tag + '更新頻率：下次快照時間正確（跨日、跨週末、跳過 12/25）', got == [('2026-11-24', '00:54'), ('2026-11-30', '00:54'), ('2026-12-28', '00:54'), ('2026-11-24', '10:54')], str(got))
    dv = await pg.evaluate("[window.__twDiff(-97863,-99219), window.__twDiff(null,-99219), window.__twDiff(-97863,null)]")
    check(tag + '籌碼增減缺值時回傳空值（台指期／融資融券共用）', dv[0] == 1356 and dv[1] is None and dv[2] is None, str(dv))
    nd = await pg.evaluate("[window.__twNextDelay(true,false,true), window.__twNextDelay(false,false,true), window.__twNextDelay(false,true,true), window.__twNextDelay(true,false,false), window.__twNextDelay(false,false,false)]")
    check(tag + '盤中自動更新排程（即時 30 秒、暫時斷線 60 秒重試、禁止連外與盤後不排程）', nd == [30000, 60000, 0, 0, 0], str(nd))
    if mode == 'fail':
        hol_ = set(re.findall(r"'(\d{4}-\d{2}-\d{2})':", re.search(r'var HOLIDAYS=\{(.*?)\};', src).group(1)))
        nw_ = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
        sess_ = nw_.weekday() < 5 and nw_.strftime('%Y-%m-%d') not in hol_ and 540 <= nw_.hour * 60 + nw_.minute <= 810
        mt0 = await pg.inner_text('#modeText')
        check(tag + '暫時斷線時說明重試方式（盤中每分鐘自動重試／盤後按重新整理）', ('每分鐘會自動重試' in mt0) if sess_ else ('可按「重新整理」再試' in mt0), mt0)
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
    mt_ = ch.get('maint', [])[-10:]
    mtn = await pg.eval_on_selector_all('#maintChart svg circle', 'es=>es.length')
    check(tag + '分析：融資維持率圖有資料', mtn == len(mt_) and mtn >= 4, f'{mtn} 點')
    refy = await pg.eval_on_selector_all('#maintChart svg line.ref', 'es=>es.length')
    check(tag + '分析：融資維持率圖有 120% 追繳參考線', refy == 1, f'{refy} 條')
    rlbl = await pg.eval_on_selector_all('#maintChart svg text.reflbl', 'es=>es.map(e=>e.textContent)')
    msub = await pg.inner_text('#maintSub')
    check(tag + '分析：追繳參考線標示 120% 且說明文字一致', rlbl == ['追繳 120%'] and '120%' in msub and '130%' in msub, f'{rlbl}｜{msub[-40:]}')
    mtr = await pg.inner_text('#maintRead')
    lastm = mt_[-1]
    check(tag + '分析：融資維持率讀數顯示最新日期、百分比與增減', lastm['d'][5:].replace('-', '/') in mtr and f"{lastm['r']:.2f}%" in mtr and '個百分點' in mtr, mtr)
    mtnote = await pg.inner_text('#maintNote')
    check(tag + '分析：融資維持率標示資料來源與日期', '快照' in mtnote and lastm['d'][5:].replace('-', '/') in mtnote, mtnote)
    mw = await pg.eval_on_selector('#maintChart svg', 'e=>e.getBoundingClientRect().right')
    check(tag + '分析：融資維持率圖在 390px 內', mw <= 390, f'right={mw:.0f}')
    for cid, rid in (('maChart', 'maRead'), ('instChart', 'instRead'), ('futChart', 'futRead'), ('mgChart', 'mgRead'), ('maintChart', 'maintRead')):
        r0 = await pg.inner_text('#' + rid)
        await pg.locator(f'#{cid} svg').scroll_into_view_if_needed()
        box = await pg.locator(f'#{cid} svg').bounding_box()
        await pg.mouse.click(box['x'] + box['width'] * 0.2, box['y'] + box['height'] * 0.5)
        await pg.wait_for_timeout(100)
        r1 = await pg.inner_text('#' + rid)
        gd = await pg.eval_on_selector(f'#{cid} .guide', 'e=>e.style.display')
        check(tag + f'分析：點 {cid} 會切換日期數值', r1 != r0 and re.match(r'\d{2}/\d{2}', r1) and gd != 'none', f'{r0[:12]} → {r1[:12]}')
    # 分析圖遇到缺值：線圖斷開、不畫點；長條圖不畫該根；讀數顯示「—」
    nul = await pg.evaluate("""()=>{
      var R=[{d:'2026-11-17',m:5087.21},{d:'2026-11-18',m:null},{d:'2026-11-19',m:4843.68},{d:'2026-11-20',m:4352.27}];
      window.__twChart('mgChart','mgRead',R,'m',{bar:false,color:'var(--c2)',dig:0,unit:' 億',label:'融資'});
      var c=document.querySelectorAll('#mgChart svg circle').length, d=document.querySelector('#mgChart svg path[stroke-linejoin]').getAttribute('d');
      var B=[{d:'2026-11-18',dn:120},{d:'2026-11-19',dn:null},{d:'2026-11-20',dn:-80}];
      window.__twChart('futChart','futRead',B,'dn',{bar:true,signColor:true,dig:0,unit:' 口',label:'增減'});
      var r=document.querySelectorAll('#futChart svg rect[rx]').length;
      var bx=document.querySelector('#mgChart svg').getBoundingClientRect();
      return {c:c,d:d,r:r,bx:[bx.x,bx.y,bx.width,bx.height]};
    }""")
    check(tag + '分析：融資缺值時不畫點、線段斷開', nul['c'] == 3 and nul['d'].count('M') == 2 and 'NaN' not in nul['d'], f"{nul['c']} 點、{nul['d'].count('M')} 段")
    check(tag + '分析：期貨增減缺值時不畫長條', nul['r'] == 2, f"{nul['r']} 根")
    bx = nul['bx']
    await pg.mouse.click(bx[0] + bx[2] * 0.38, bx[1] + bx[3] * 0.5)
    await pg.wait_for_timeout(100)
    mrd = await pg.inner_text('#mgRead')
    check(tag + '分析：缺值那天讀數顯示「—」且不算增減', '11/18' in mrd and '—' in mrd and '增減' not in mrd, mrd)
    await pg.evaluate('window.__twReAna()')
    mg2 = await pg.eval_on_selector_all('#mgChart svg circle', 'es=>es.length')
    check(tag + '分析：重畫後恢復正常資料', mg2 == mg, f'{mg2} 點')
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
    for href in ('#outlook', '#idx', '#trend', '#chips', '#ana', '#src', '#install', '#iter'):
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
