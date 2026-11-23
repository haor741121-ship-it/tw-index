"""美股走勢模擬：自動化測試。用法：python3 test_page.py index.html out"""
import sys, os, re, json, asyncio
from playwright.async_api import async_playwright
SRC=os.path.abspath(sys.argv[1]); OUT=sys.argv[2] if len(sys.argv)>2 else 'out'; os.makedirs(OUT,exist_ok=True)
HTML=open(SRC,encoding='utf-8').read()
RAW='https://raw.githubusercontent.com/haor741121-ship-it/tw-index/main/us-sim/index.html'
res=[]
def ok(n,c): res.append((n,bool(c))); print(('PASS ' if c else 'FAIL ')+n)
def bump(h,dr):
    m=re.search(r'(<script id="data"[^>]*>)(.*?)(</script>)',h,re.S); d=json.loads(m.group(2)); d['round']=d['round']+dr; d['lead']='TEST-NEW' if dr>0 else d['lead']
    return h[:m.start(2)]+json.dumps(d,ensure_ascii=False)+h[m.end(2):]
async def page_with(b, remote, name):
    ctx=await b.new_context(viewport={'width':390,'height':844},accept_downloads=True,ignore_https_errors=True)
    await ctx.grant_permissions(['clipboard-read','clipboard-write'],origin='https://local.test')
    errs=[]; p=await ctx.new_page(); p.on('pageerror',lambda e: errs.append(str(e)))
    async def local(r): await r.fulfill(status=200,content_type='text/html',body=HTML)
    async def raw(r):
        if remote is None: await r.abort()
        else: await r.fulfill(status=200,content_type='text/plain',body=remote,headers={'access-control-allow-origin':'*'})
    await p.route('https://local.test/**',local); await p.route(re.compile(r'https://raw\.githubusercontent\.com/.*'),raw)
    await p.goto('https://local.test/index.html'); await p.wait_for_timeout(1500)
    await p.screenshot(path=f'{OUT}/shot_{name}.png',full_page=True)
    return ctx,p,errs
window_h=844
async def main():
    async with async_playwright() as pw:
        b=await pw.chromium.launch(executable_path=os.environ.get('CHROME','/usr/bin/google-chrome'),args=['--no-sandbox'])
        # 1 同版
        ctx,p,errs=await page_with(b,HTML,'same')
        D=json.loads(re.search(r'<script id="data"[^>]*>(.*?)</script>',HTML,re.S).group(1))
        ok('標題輪次顯示', (await p.text_content('#round')).strip()=='第 %d 輪'%D['round'])
        ok('情境卡片 3 張', await p.locator('#scenarios .sc').count()==len(D.get('scenarios',[])))
        ok('走勢圖 SVG', await p.locator('#chart svg').count()==1 or not D.get('hist'))
        U=D.get('ust') or {}
        ok('美債區塊與說明', await p.locator('#ust').count()==1 and '10 年期和 2 年期差在哪' in (await p.text_content('#ust')))
        ok('美債卡片 3 張', await p.locator('#ustCards .stat').count()==3)
        ok('美債走勢圖', (await p.locator('#ustChart svg').count()==1) if len(U.get('hist',[]))>=2 else (await p.locator('#ustChart .empty').count()==1))
        LG=(D.get('leaders') or {}).get('items',[])
        ok('龍頭股區塊', await p.locator('#leaders').count()==1)
        ok('龍頭股清單', (await p.locator('#ldList .ld').count()==len(LG)) if LG else (await p.locator('#ldList .empty').count()==1))
        ok('同版顯示已是最新', '已是最新版' in (await p.text_content('#updState')))
        ok('無水平溢出', await p.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'))
        for a in await p.locator('nav a').all():
            href=await a.get_attribute('href'); await a.click(); await p.wait_for_timeout(250)
            top=await p.evaluate(f'document.querySelector("{href}").getBoundingClientRect().top')
            atb=await p.evaluate('window.scrollY+window.innerHeight>=document.documentElement.scrollHeight-2')
            ok(f'導覽 {href} 可跳轉', abs(top)<120 or (atb and 0<=top<window_h))
        async with p.expect_download() as di: await p.click('#dlBtn')
        dl=await di.value; path=f'{OUT}/{dl.suggested_filename}'; await dl.save_as(path); txt=open(path,encoding='utf-8').read()
        ok('下載檔名 us-sim.html', dl.suggested_filename=='us-sim.html')
        ok('下載內容完整（含資料與自動更新）', txt.startswith('<!DOCTYPE html>') and 'id="data"' in txt and 'UPDATE_URL' in txt)
        n_bad=await p.evaluate('t=>{const d=new DOMParser().parseFromString(t,"text/html");return d.querySelectorAll("script:not([data-keep])").length+(d.querySelectorAll("script[data-keep]").length===3?0:100)}',txt)
        ok('下載內容只含 3 個 data-keep script', n_bad==0)
        await p.click('#copyBtn'); await p.wait_for_timeout(300)
        clip=await p.evaluate('navigator.clipboard.readText()')
        ok('複製原始碼', clip.startswith('<!DOCTYPE html>') and 'id="data"' in clip)
        ok('同版無 JS 錯誤', not errs); await ctx.close()
        # 2 下載檔本身能開、且會自動更新到新版
        global HTML0; HTML0=HTML
        ctx,p,errs=await page_with(b,bump(HTML,1),'newer')
        ok('有新版會自動換成新版', (await p.text_content('#lead'))=='TEST-NEW')
        ok('顯示已自動更新', '自動更新' in (await p.text_content('#updState')))
        ok('新版無 JS 錯誤', not errs); await ctx.close()
        # 3 GitHub 較舊 → 不換
        ctx,p,errs=await page_with(b,bump(HTML,-1),'older')
        ok('遠端較舊不覆蓋', (await p.text_content('#lead'))!='TEST-NEW' and '已是最新版' in (await p.text_content('#updState')))
        await ctx.close()
        # 4 斷線
        ctx,p,errs=await page_with(b,None,'offline')
        ok('斷線顯示檔案內版本', '無法檢查更新' in (await p.text_content('#updState')))
        ok('斷線無 JS 錯誤', not errs); await ctx.close()
        await b.close()
    f=[n for n,c in res if not c]; print(f'\n共 {len(res)} 項，通過 {len(res)-len(f)} 項'+('' if not f else '，失敗：'+'、'.join(f)))
    sys.exit(1 if f else 0)
asyncio.run(main())
