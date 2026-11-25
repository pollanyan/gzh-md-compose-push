# -*- coding: utf-8 -*-
"""公众号草稿推送（浏览器通道，无需 AppID）。

用法：
  python mp_full.py login                                  # 探测结构 + 首次扫码
  python mp_full.py push <article.py> [--appmsgid N] [--cover 图.png] [--force]
  python mp_full.py logout                                 # 清除登录态（删 mp_profile）

环境变量：
  MP_LOGIN_WAIT   等扫码的秒数，默认 900（15 分钟）。登录成功会立刻返回，不会白等。
  MP_HEADLESS     1=无头（默认）；0=有头，调试时用来看界面。

说明：
  微信后台编辑器的正文是 ProseMirror（在 .mock-iframe-body 内，不是 iframe），
  必须用「真实鼠标点击聚焦 + 真实剪贴板 + Ctrl+V」才能把带样式的 HTML 灌进去。
  脚本只点「保存为草稿」，**绝不点「发表」**。
"""
import glob
import json
import os
import re
import shutil
import sys
import time

try:
    from patchright.sync_api import sync_playwright
except ImportError:
    raise SystemExit(
        "缺少浏览器驱动 patchright（只在本脚本推送时需要，纯排版脚本无需安装）。\n"
        "自动安装： python3 -m pip install patchright\n"
        "装完重跑本命令即可；浏览器内核会自动探测系统已装的 Chrome，无需手工配置。"
    )

BASE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(BASE, "mp_profile")
QR_OUT = os.path.join(BASE, "mp-login-qrcode.png")
QR_BIG = os.path.join(BASE, "mp-login-qrcode-big.png")
LOG = os.path.join(BASE, "mp_full.log")
SHOT = os.path.join(BASE, "mp-shot-%s.png")

MP_HOME = "https://mp.weixin.qq.com/"
NEW_TPL = ("https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit"
           "&isNew=1&type=77&createType=0&token=%s&lang=zh_CN&scene=21")
EDIT_TPL = ("https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit"
            "&type=77&appmsgid=%s&token=%s&lang=zh_CN")

BODY_SEL = ".mock-iframe-body .ProseMirror"
TITLE_SEL = ".title-editor__input .ProseMirror"
LEN_JS = "(s)=>{const e=document.querySelector(s);return e?e.innerText.length:-1;}"
DIALOG = ".weui-desktop-dialog"

WAIT_SECONDS = int(os.environ.get("MP_LOGIN_WAIT", "900"))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

# 主文件里不该出现的按钮文案（防止误点「发表」）
FORBIDDEN_LABELS = ("发表", "群发", "发布")


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def headless():
    return os.environ.get("MP_HEADLESS", "1") != "0"


# ---------------------------------------------------------------- 浏览器

def _browser_build(path):
    """从 ms-playwright 路径里抠出 Chromium 构建号，例如 chromium-1091 → 1091。

    不能按目录名做字符串排序（`chromium-999` 会排在 `chromium-1091` 后面），
    也不能按修改时间排序（「最近装的」不等于「版本最高的」，重装一份旧版就会选错）。
    目录名里的数字才是真正的版本。
    """
    p = path.replace("\\", "/")
    m = re.search(r"chromium(?:_headless_shell)?-(\d+)", p)
    if m:
        return int(m.group(1))
    m = re.search(r"-(\d+)/", p)
    return int(m.group(1)) if m else 0


# 系统已装浏览器的常见位置（自动探测，无需用户手工 export MP_CHROME）
SYSTEM_CHROME = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",   # macOS
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",          # Windows
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",         # Linux
    "/usr/bin/chromium", "/usr/bin/chromium-browser",
]


def find_chrome():
    """跨平台自动定位浏览器，优先级：MP_CHROME > 系统已装 Chrome > ms-playwright。

    系统已装的 Chrome/Edge 自动探测，用户无需手工配置环境变量或下载 Chromium。
    只有以上都没有时才返回 None（交给 patchright 自己找）；ms-playwright 缓存
    里若有多份，选**构建号最大**的，同版本取修改时间新的。
    正规 Chromium 优先于 `chrome-headless-shell`（后者不能开有头模式）。
    """
    env = os.environ
    # ① 显式覆盖（高级用法，普通用户不需要）
    override = env.get("MP_CHROME", "").strip()
    if override:
        if os.path.exists(override):
            log("使用 MP_CHROME 指定浏览器: %s" % override)
            return override
        log("!! MP_CHROME 指向的文件不存在: %s" % override)

    # ② 自动探测系统已装浏览器（含 PATH 里的 google-chrome/chromium）
    for p in SYSTEM_CHROME:
        if p and os.path.exists(p):
            log("自动探测到系统浏览器: %s" % p)
            return p
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            log("自动探测到系统浏览器(PATH): %s" % found)
            return found

    # ③ ms-playwright 缓存（patchright install chromium 下载的）
    roots = []
    if env.get("LOCALAPPDATA"):                       # Windows
        roots.append(os.path.join(env["LOCALAPPDATA"], "ms-playwright"))
    if env.get("HOME"):                               # macOS
        roots.append(os.path.join(env["HOME"], "Library", "Caches", "ms-playwright"))
    if env.get("XDG_CACHE_HOME"):                     # Linux
        roots.append(os.path.join(env["XDG_CACHE_HOME"], "ms-playwright"))
    elif env.get("HOME"):
        roots.append(os.path.join(env["HOME"], ".cache", "ms-playwright"))
    full_pats = ("**/chrome-win64/chrome.exe", "**/chrome-win/chrome.exe",
                 "**/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
                 "**/chrome-linux*/chrome")
    shell_pats = ("**/chrome-headless-shell*/chrome-headless-shell*",)
    full, shell = [], []
    for r in roots:
        for pat in full_pats:
            full += glob.glob(os.path.join(r, pat), recursive=True)
        for pat in shell_pats:
            shell += glob.glob(os.path.join(r, pat), recursive=True)
    hits = full or shell
    if not hits:
        log("未找到任何浏览器，尝试 patchright 内置查找（可能需要 patchright install chromium）")
        return None
    if not full:
        log("只找到 chrome-headless-shell（有头模式不可用），仍使用它")

    def _key(p):
        try:
            mt = os.path.getmtime(p)
        except Exception:
            mt = 0
        return (_browser_build(p), mt)

    hits.sort(key=_key)
    picked = hits[-1]
    log("选用浏览器 %s（构建号 %s）" % (picked, _browser_build(picked)))
    return picked


def launch_kwargs(viewport=None):
    kw = dict(headless=headless(),
              viewport=viewport or {"width": 1440, "height": 950},
              user_agent=UA,
              args=["--disable-blink-features=AutomationControlled",
                    "--no-first-run", "--no-default-browser-check"])
    exe = find_chrome()
    if exe:
        kw["executable_path"] = exe
    return kw


class BrowserBusy(RuntimeError):
    pass


def open_context(p):
    """打开持久化 context；profile 被占用时给一句人话的提示。"""
    try:
        return p.chromium.launch_persistent_context(PROFILE, **launch_kwargs())
    except Exception as e:
        msg = str(e).split("\n")[0]
        if "SingletonLock" in str(e) or "ProcessSingleton" in str(e) or "lock" in msg.lower():
            raise BrowserBusy(
                "浏览器 profile 被占用（上一次运行可能没退干净）：%s\n"
                "  处理：关掉残留的 Chromium 进程后重试；仍不行就删掉 %s 重新扫码。"
                % (msg, PROFILE))
        raise


def logged_in(pg):
    return "cgi-bin/home" in pg.url or ("token=" in pg.url and "login" not in pg.url)


def appmsgid_of(pg):
    m = re.search(r"appmsgid=(\d+)", pg.url)
    return m.group(1) if m else None


def page_error(pg):
    """识别页面级错误文案。返回人话描述，正常页面返回 ''。

    实测到的三种「草稿打不开」形态：
      a) `系统错误(320003)`               —— 带错误码
      b) `此草稿已被删除`                 —— 没有错误码
      c) `此草稿已发表，可前往发表记录查看` —— 没有错误码，草稿已被发布出去
    旧版本只会报「等编辑器超时」，很容易被误判成选择器失效或网络慢。
    """
    try:
        t = pg.evaluate("()=>document.body?document.body.innerText:''") or ""
    except Exception:
        return ""
    m = re.search(r"系统错误\((\d+)\)", t)
    if m:
        code = m.group(1)
        if code == "320003":
            return "系统错误(320003) —— 这篇草稿不存在（已被删除，或已发表、已移出草稿箱）"
        return "系统错误(%s) —— 微信后台拒绝了这次访问（token 过期 / 草稿不存在 / 参数不对）" % code
    if "此草稿已被删除" in t:
        return "此草稿已被删除（appmsgid 已失效，不能再编辑）"
    if "此草稿已发表" in t:
        return "此草稿已发表 —— 它已移出草稿箱，想改就重新建一篇"
    if re.search(r"请重新登录|重新登录", t):
        return "需要重新登录（登录态已失效）"
    return ""


def token_of(pg):
    m = re.search(r"token=(\d+)", pg.url)
    if m:
        return m.group(1)
    try:
        m = re.search(r"token=(\d+)", pg.content())
        return m.group(1) if m else None
    except Exception:
        return None


def save_qr(pg):
    """抓登录二维码，并额外产出一张放大的（浏览器渲染放大，不需要 Pillow）。

    原图只有 ~122px，直接发给用户根本扫不出来。这里把元素放大 4 倍后
    再截图，得到 ~490px 的清晰码，省掉 uv + pillow 那一步。
    """
    el = None
    t0 = time.time()
    while time.time() - t0 < 20:
        try:
            el = pg.query_selector(".login__type__container__scan__qrcode")
        except Exception:
            el = None
        if el:
            break
        pg.wait_for_timeout(1000)
    if not el:
        log("!! 没找到二维码元素，整页截图兜底 → %s" % QR_OUT)
        try:
            pg.screenshot(path=QR_OUT)
        except Exception as e:
            log("二维码截图异常: %s" % e)
        return False

    try:
        el.screenshot(path=QR_OUT)
        pg.screenshot(path=QR_BIG)          # 兜底值，下面成功就覆盖掉
        ok = pg.evaluate("""(sel)=>{
          const el=document.querySelector(sel);
          if(!el) return false;
          el.style.transform='scale(4)';
          el.style.transformOrigin='0 0';
          el.style.position='fixed';
          el.style.left='0px'; el.style.top='0px';
          el.style.zIndex='2147483647';
          el.style.background='#fff';
          el.style.padding='16px';
          return true;
        }""", ".login__type__container__scan__qrcode")
        if ok:
            pg.wait_for_timeout(600)
            box = el.bounding_box()
            if box:
                pg.screenshot(path=QR_BIG, clip={
                    "x": 0, "y": 0,
                    "width": min(box["width"], 900), "height": min(box["height"], 900)})
                log("二维码已放大 → %s" % QR_BIG)
        pg.evaluate("""(sel)=>{const el=document.querySelector(sel);
          if(el){el.style.transform='';el.style.transformOrigin='';
                 el.style.position='';el.style.left='';el.style.top='';
                 el.style.zIndex='';el.style.background='';el.style.padding='';}}""",
                    ".login__type__container__scan__qrcode")
        pg.wait_for_timeout(300)
    except Exception as e:
        log("二维码放大失败（用原图即可）: %s" % str(e).split("\n")[0])
    return True


def clean_qr():
    """登录成功后删掉二维码文件——它是一张可被扫进后台的活码，不该留在磁盘上。"""
    for f in (QR_OUT, QR_BIG):
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass


def ensure_login(ctx, pg):
    pg.goto(MP_HOME, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(4000)
    if logged_in(pg):
        log("已有登录态: %s" % pg.url)
        return True

    if not save_qr(pg):
        log("首个二维码没截到，等页面渲染后重试一次")
        pg.wait_for_timeout(5000)
        save_qr(pg)
    log("未登录，已抓二维码 → %s（放大版 %s）" % (QR_OUT, QR_BIG))
    log("请用微信扫一扫登录；本次最多等 %s 秒" % WAIT_SECONDS)

    t0 = time.time()
    deadline = t0 + WAIT_SECONDS
    qr_stamp = t0
    while time.time() < deadline:
        if logged_in(pg):
            log("登录成功: %s" % pg.url)
            clean_qr()
            return True
        # 微信二维码本身有有效期（约 5 分钟），到点就刷新页面换一张新码，
        # 否则用户看到的是已经失效的旧码，白扫。
        if time.time() - qr_stamp > 260:
            log("二维码超过约 4 分钟，刷新页面换新码")
            try:
                pg.reload(wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(3000)
                if not logged_in(pg):
                    save_qr(pg)
                qr_stamp = time.time()
            except Exception as e:
                log("刷新失败: %s" % str(e).split("\n")[0])
                qr_stamp = time.time()
        pg.wait_for_timeout(3000)
    log("等待登录超时（%s 秒）。重新运行会生成新二维码。" % WAIT_SECONDS)
    return False


def wait_editor(pg, timeout=60):
    """轮询等编辑器（标题 + 正文）挂载完，别用固定 sleep 赌。

    同时识别页面级错误：`系统错误(320003)` 表示**这篇草稿不存在**
    （已被删除，或已经发表过、移出了草稿箱）。以前这种情况只会报
    「等编辑器超时」，很容易被误判成选择器失效/网络慢，白查半天。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        err = page_error(pg)
        if err:
            log("!! 页面报错: %s" % err)
            return False
        try:
            st = pg.evaluate("(a)=>[!!document.querySelector(a.t),!!document.querySelector(a.b)]",
                             {"t": TITLE_SEL, "b": BODY_SEL})
            if st[0] and st[1]:
                return True
        except Exception:
            pass
        pg.wait_for_timeout(1000)
    log("!! 等编辑器超时（%ss），标题=%s 正文=%s，URL=%s" % (
        timeout, pg.evaluate("(s)=>!!document.querySelector(s)", TITLE_SEL),
        pg.evaluate("(s)=>!!document.querySelector(s)", BODY_SEL), pg.url))
    return False


# ---------------------------------------------------------------- 页面操作

def click_center(pg, sel, dy=30):
    """用原生点击（自动滚动定位到可见点）聚焦元素，并校验焦点。"""
    try:
        pg.click(sel, timeout=6000)
    except Exception as e:
        log("原生点击失败 %s: %s" % (sel, str(e).split("\n")[0]))
    pg.wait_for_timeout(600)
    focused = pg.evaluate(
        "(s)=>{const e=document.querySelector(s);"
        "return !!e && (e.contains(document.activeElement) || e===document.activeElement);}",
        sel)
    log("点击 %s 焦点在编辑器内=%s" % (sel, focused))
    return focused


def set_clipboard_html(pg, html, plain):
    return pg.evaluate("""async (a)=>{
      try{
        const item=new ClipboardItem({
          'text/html': new Blob([a.html],{type:'text/html'}),
          'text/plain': new Blob([a.plain],{type:'text/plain'})});
        await navigator.clipboard.write([item]);
        return 'ok';
      }catch(e){return 'err:'+e.name+':'+e.message;}
    }""", {"html": html, "plain": plain})


def click_text(pg, label, sels="a,button,div,span,li", scope=None):
    """按可见文字精确点击最后一个匹配元素。

    scope 给了 CSS 选择器时（如 `.weui-desktop-dialog`），优先在**可见弹窗内**找，
    找不到再退回整页 —— 否则「下一步 / 确认」很容易点到背景里同名的按钮。
    绝不允许点到「发表」类按钮。
    """
    if label in FORBIDDEN_LABELS:
        log("!! 拒绝点击危险按钮: %s" % label)
        return "blocked"
    return pg.evaluate("""(a)=>{
      const pick=(root)=>{
        const all=[...root.querySelectorAll(a.sels)];
        const hit=all.filter(e=>e.offsetParent && (e.innerText||'').trim()===a.label);
        return hit.length? hit[hit.length-1] : null;
      };
      let el=null;
      if(a.scope){
        for(const r of [...document.querySelectorAll(a.scope)].filter(x=>x.offsetParent)){
          el=pick(r); if(el) break;
        }
      }
      if(!el) el=pick(document);
      if(!el) return 'none';
      const t=el.closest('a,button,li')||el;
      t.click();
      return 'clicked';
    }""", {"label": label, "sels": sels, "scope": scope})


def text_len_of(html):
    """估算正文 HTML 会渲染出多少「非空白字符」，用作注入成功的判据。

    以前这里用的是魔数 `after <= 200` 判失败 —— 于是**任何短于 200 字的文章
    都会被误判成注入失败**，进而走重试分支把正文**重复粘贴一遍**。
    实测：一篇 60 字的短文被粘成 135 字（图片也翻倍）。
    现在改成按预期文字长度算，短文也能正确判定。
    """
    txt = re.sub(r"<[^>]+>", " ", html)
    return len(re.sub(r"\s+", "", txt))


def wait_and_dismiss(pg, labels=("继续插入",), timeout=8):
    """粘贴后「内容结构检测」弹窗**不是每次都会出现**（实测时有时无）。

    所以不能等固定 2.5s 就断言「有没有弹窗」，而是轮询一段时间：
    出现就点掉，不出现就放过。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        for lb in labels:
            if click_text(pg, lb, scope=DIALOG) == "clicked":
                return lb
        pg.wait_for_timeout(500)
    return "none"


def _focus_body(pg):
    if not click_center(pg, BODY_SEL):
        log("点击未取得焦点，尝试 JS 聚焦")
        pg.evaluate("(s)=>{const e=document.querySelector(s);if(e)e.focus();}", BODY_SEL)
        pg.wait_for_timeout(600)


# macOS 的编辑快捷键是 Cmd（Meta），Windows/Linux 是 Ctrl——2026-11-25 首次
# 真实推送时发现：在 mac 上发 Control+V 不触发粘贴（注入只得到 10 字符）、
# Control+A 也不全选，必须按平台选修饰键。
MOD = "Meta" if sys.platform == "darwin" else "Control"


def _clear_body(pg):
    pg.keyboard.press(MOD + "+A")
    pg.keyboard.press("Delete")
    pg.wait_for_timeout(500)


def paste_body(pg, html, want_imgs=0):
    plain = re.sub("<[^>]+>", " ", html)
    want_text = text_len_of(html)
    floor = max(20, int(want_text * 0.7))

    def attempt():
        _focus_body(pg)
        _clear_body(pg)                      # 每次都先清空，避免重试时内容翻倍
        r = set_clipboard_html(pg, html, plain)
        if str(r).startswith("err:"):
            log("!! 剪贴板被拒（缺 clipboard 权限？）: %s" % r)
        pg.keyboard.press(MOD + "+V")
        pg.wait_for_timeout(2000)
        hit = wait_and_dismiss(pg, ("继续插入",))
        log("结构检测弹窗 -> %s" % hit)
        pg.wait_for_timeout(1200)
        n = pg.evaluate(LEN_JS, BODY_SEL)
        got_imgs = count_body_imgs(pg)["real"]
        return n, got_imgs

    before = pg.evaluate(LEN_JS, BODY_SEL)
    after, got = attempt()
    log("正文长度 %s -> %s（预期非空白字符 %s，下限 %s）；图片 %s/%s"
        % (before, after, want_text, floor, got, want_imgs))

    ok = after >= floor and got >= want_imgs
    if not ok:
        log("正文注入不达标，清空后重试一次")
        after, got = attempt()
        log("重试后 长度=%s 图片=%s" % (after, got))
        ok = after >= floor and got >= want_imgs
    return ok


def set_title(pg, title):
    click_center(pg, TITLE_SEL)
    pg.wait_for_timeout(500)
    if not pg.evaluate("(s)=>{const e=document.querySelector(s);"
                       "return !!e&&(e.contains(document.activeElement)||e===document.activeElement);}",
                       TITLE_SEL):
        pg.evaluate("(s)=>{const e=document.querySelector(s);if(e)e.focus();}", TITLE_SEL)
        pg.wait_for_timeout(400)
    # 先清空已有标题，避免重复追加
    pg.keyboard.press(MOD + "+A")
    pg.keyboard.press("Delete")
    pg.wait_for_timeout(400)
    pg.keyboard.type(title, delay=8)
    pg.wait_for_timeout(1200)
    got = pg.evaluate("(s)=>{const e=document.querySelector(s);return e?e.innerText.trim():'';}", TITLE_SEL)
    log("标题已填: %s" % got)
    return got[:6] == title[:6]


def count_body_imgs(pg):
    """.ProseMirror-separator 是 ProseMirror 给每张图补的占位 img，不能算数。"""
    return pg.evaluate("""()=>{
      const all=[...document.querySelectorAll('.mock-iframe-body img')];
      const real=all.filter(i=>!(i.className||'').toString().includes('ProseMirror-separator'));
      return {all:all.length, real:real.length};
    }""")


def remove_body_images(pg, keep=0):
    """清掉误插进正文的图片，只删到剩余 <= keep 张。

    keep 用于文章自带配图的情况：正文 HTML 里本来就有 N 张图，
    不能把它们当成误插的封面图删掉。
    只点真图（排除 .ProseMirror-separator），否则会点到 0 尺寸的占位符。
    """
    n0 = count_body_imgs(pg)["real"]
    if n0 <= keep:
        log("正文真图=%s（<= 预期 %s），无需清理" % (n0, keep))
        return True
    for _ in range(max(0, n0 - keep) + 2):
        n = count_body_imgs(pg)["real"]
        if n <= keep:
            break
        try:
            pg.evaluate("""()=>{const a=[...document.querySelectorAll('.mock-iframe-body img')]
              .filter(i=>!(i.className||'').toString().includes('ProseMirror-separator'));
              if(a.length) a[a.length-1].scrollIntoView({block:'center'});}""")
            pg.wait_for_timeout(400)
            imgs = pg.query_selector_all(
                ".mock-iframe-body img:not(.ProseMirror-separator)")
            if not imgs:
                break
            imgs[-1].click()
            pg.wait_for_timeout(700)
            pg.keyboard.press("Delete")
            pg.wait_for_timeout(1200)
        except Exception as e:
            log("删正文图失败: %s" % str(e).split("\n")[0])
            break
    left = count_body_imgs(pg)["real"]
    log("正文真图 %s -> %s（预期保留 %s）" % (n0, left, keep))
    return left == keep


def load_from_base(name):
    """从**本脚本所在目录**精确加载模块，不走 sys.path 搜索。

    为什么必须这样：`push` 会把文章所在目录也加进 sys.path，而文章目录里
    很可能残留着一份旧的同名脚本（比如早期调试时拷过去的 `mp_cover_set.py`）。
    普通 `import` 会命中那份旧副本 —— 后果是 `--cover` 的参数被解析错、甚至
    执行到旧副本的 `main()`（实测现象：日志里 `目标封面=文章名.py`）。
    这里用文件路径直接加载，彻底绕开遮蔽问题。
    """
    import importlib.util
    path = os.path.join(BASE, name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def add_sys_path(art_dir):
    """保证 sys.path 的顺序是 [脚本目录, 文章目录, ...]。

    顺序反了的话，文章目录里的同名文件会遮蔽技能自己的脚本
    （实测：文章目录里一份旧的 `mp_cover_set.py` 抢走了 import，
    导致 `--cover` 参数被解析成文章名）。
    """
    if BASE in sys.path:
        sys.path.remove(BASE)
    sys.path.insert(0, BASE)
    if art_dir and os.path.abspath(art_dir) != BASE:
        if art_dir in sys.path:
            sys.path.remove(art_dir)
        sys.path.insert(1, art_dir)
    log("sys.path 前两位: %s" % sys.path[:2])


def load_article(path):
    """按**文件路径**加载文章模块。

    不用 `__import__(文件名)`：文件名里带点号时（如 `article.v2.py`），
    Python 会把它当成 `article.v2` 子包路径去找，直接 ModuleNotFoundError。
    按路径精确加载则任何合法文件名都能用。
    """
    import importlib.util
    path = os.path.abspath(path)
    mod_name = re.sub(r"\W", "_", os.path.splitext(os.path.basename(path))[0]) or "article"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("无法加载文章模块: %s" % path)
    mod = importlib.util.module_from_spec(spec)
    # 登记进 sys.modules：模块名不是 __main__，所以文章里的
    # `if __name__ == "__main__"` 不会误触发；同时 spec 已设好 __file__，
    # 文章靠 __file__ 定位 imglib_urls.json 的逻辑不受影响。
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    log("已加载文章模块 %s（模块名 %s）" % (path, mod_name))
    return mod


def save_draft(pg):
    """点「保存为草稿」并**校验真的保存成功**（弹 Toast 或 URL 出现 appmsgid）。

    返回 appmsgid / 'saved' / None。
    """
    before = appmsgid_of(pg)
    for attempt in range(1, 3):
        r = pg.evaluate("""()=>{
          const all=[...document.querySelectorAll('a,button,div,span')];
          const hit=all.filter(e=>e.offsetParent && (e.innerText||'').trim()==='保存为草稿');
          if(!hit.length) return 'not-found';
          const el=hit[hit.length-1]; (el.closest('a,button')||el).click();
          return 'clicked';
        }""")
        log("保存为草稿（第%s次）-> %s" % (attempt, r))
        if r == "not-found":
            return None
        for _ in range(25):
            pg.wait_for_timeout(1000)
            # Toast 元素必须"短"，否则会匹配到包着整块导航的大容器
            # （实测：裸匹配 innerText 会把整个侧边栏当成保存回执）
            toast = pg.evaluate("""()=>{
              const es=[...document.querySelectorAll('div,span,p,em,i')]
                .filter(e=>e.offsetParent)
                .map(e=>(e.innerText||'').trim())
                .filter(t=>t.length>0 && t.length<=12 && /保存成功|已保存|草稿已保存/.test(t));
              return es.length? es[0].slice(0,20):'';}""")
            now = appmsgid_of(pg)
            if toast:
                log("保存回执: %s" % toast)
                return now or before or "saved"
            if now and now != before:
                log("保存回执: URL 出现 appmsgid=%s" % now)
                return now
        log("第%s次保存未收到回执，重试" % attempt)
        pg.wait_for_timeout(2000)
    log("!! 保存未确认（请人工去草稿箱看一眼）")
    return None


def push(pg, mod, appmsgid=None, cover=None, force=False):
    res = {"appmsgid": None, "title": False, "body": False,
           "imgs": 0, "want_imgs": 0, "cover": None, "error": ""}
    token = token_of(pg)
    log("token=%s appmsgid=%s" % (token, appmsgid))
    if not token:
        log("!! 拿不到 token（登录态异常）")
        res["error"] = "拿不到 token"
        return res
    url = (EDIT_TPL % (appmsgid, token)) if appmsgid else (NEW_TPL % token)
    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    if not wait_editor(pg):
        res["error"] = page_error(pg) or "编辑器未就绪"
        if appmsgid and res["error"]:
            log("!! 覆盖草稿 %s 失败：%s\n   换个 appmsgid，或去掉 --appmsgid 新建一篇。"
                % (appmsgid, res["error"]))
        log("RESULT: %s" % json.dumps(res, ensure_ascii=False))
        return res
    log("编辑器 URL=%s" % pg.url)
    pg.screenshot(path=SHOT % "editor")

    title = mod.TITLE
    if len(title) > 64:
        log("!! 标题 %s 字，超过微信 64 上限，会被截断" % len(title))
    res["title"] = set_title(pg, title)

    digest = getattr(mod, "DIGEST", "")
    if len(digest) > 120:
        log("!! 摘要 %s 字，超过微信 120 上限，截断到 120" % len(digest))
        digest = digest[:120]
    for sel, val, label in (("#author", getattr(mod, "AUTHOR", ""), "署名"),
                            ("#js_description", digest, "摘要")):
        try:
            pg.fill(sel, val, timeout=5000)
            log("%s 已填(%s)" % (label, sel))
        except Exception as e:
            log("!! %s 填写失败: %s" % (label, e))

    html = mod.build_content()
    want = html.count("<img")
    res["want_imgs"] = want
    log("正文 HTML 长度=%s，自带图片=%s 张" % (len(html), want))
    res["body"] = paste_body(pg, html, want_imgs=want)

    c = count_body_imgs(pg)
    log("粘贴后正文图片=%s（真图 %s，预期 %s）" % (c["all"], c["real"], want))
    if c["real"] != want:
        remove_body_images(pg, keep=want)
    res["imgs"] = count_body_imgs(pg)["real"]

    if not res["body"] and not force:
        log("!! 正文注入失败，**不保存**（避免存一篇空白草稿）。确认要存就加 --force")
        pg.screenshot(path=SHOT % "filled", full_page=True)
        return res

    pg.screenshot(path=SHOT % "filled", full_page=True)
    saved = save_draft(pg)
    pg.screenshot(path=SHOT % "saved", full_page=True)
    log("保存后 URL=%s" % pg.url)
    res["appmsgid"] = saved if (saved and saved != "saved") else appmsgid

    # ---- 封面：保存后用 appmsgid 重开一次，走 mp_cover_set 的稳妥流程 ----
    if cover and os.path.exists(cover) and res["appmsgid"]:
        C = load_from_base("mp_cover_set")
        res["cover"] = C.set_cover(pg, res["appmsgid"], cover, save=True)
    elif cover:
        log("!! 未拿到 appmsgid，跳过封面（可稍后手动跑 mp_cover_set.py）")

    log("结果: appmsgid=%s 标题=%s 正文=%s 真图=%s/%s 封面=%s" % (
        res["appmsgid"], res["title"], res["body"], res["imgs"], want, res["cover"]))
    log("RESULT: %s" % json.dumps(res, ensure_ascii=False))
    return res


# ---------------------------------------------------------------- 入口

def do_logout():
    if os.path.isdir(PROFILE):
        try:
            shutil.rmtree(PROFILE)
            log("已删除登录态目录 %s（下次运行需重新扫码）" % PROFILE)
        except Exception as e:
            log("!! 删除失败（可能有残留浏览器进程）: %s" % e)
    else:
        log("没有登录态目录，无需清理: %s" % PROFILE)
    clean_qr()


def main():
    args = sys.argv[1:]
    mode = args[0] if args else "check"
    art, appmsgid, cover, force = None, None, None, "--force" in args
    if "push" in args:
        i = args.index("push")
        if len(args) > i + 1 and not args[i + 1].startswith("-"):
            art = args[i + 1]
    if "--appmsgid" in args:
        appmsgid = args[args.index("--appmsgid") + 1]
    if "--cover" in args:
        cover = args[args.index("--cover") + 1]

    log("=== 启动 mode=%s art=%s appmsgid=%s force=%s ===" % (mode, art, appmsgid, force))

    if mode == "logout":
        do_logout()
        return

    if mode == "push" and not art:
        log("用法: python mp_full.py push <article.py> [--appmsgid N] [--cover 图.png]")
        return
    if art and not os.path.exists(art):
        log("!! 找不到文章模块: %s" % art)
        return
    if cover:
        cover = os.path.abspath(cover)
        if not os.path.exists(cover):
            log("!! 找不到封面图: %s" % cover)
            return

    try:
        with sync_playwright() as p:
            ctx = open_context(p)
            try:
                ctx.grant_permissions(["clipboard-read", "clipboard-write"],
                                      origin="https://mp.weixin.qq.com")
            except Exception as e:
                log("剪贴板授权失败: %s" % e)
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            if ensure_login(ctx, pg):
                if mode == "push" and art:
                    # 文章模块可能不在脚本目录：把它所在目录也加进 sys.path
                    art_abs = os.path.abspath(art)
                    add_sys_path(os.path.dirname(art_abs))
                    mod = load_article(art_abs)
                    push(pg, mod, appmsgid, cover, force)
                else:
                    # login / check：进新建页探一下编辑器结构，确认选择器没过期
                    tok = token_of(pg)
                    if tok:
                        pg.goto(NEW_TPL % tok, wait_until="domcontentloaded", timeout=60000)
                        ready = wait_editor(pg, timeout=30)
                        log("编辑器结构就绪=%s" % ready)
                    log("BODY_SEL 存在=%s" % pg.evaluate("(s)=>!!document.querySelector(s)", BODY_SEL))
                    log("TITLE_SEL 存在=%s" % pg.evaluate("(s)=>!!document.querySelector(s)", TITLE_SEL))
            ctx.close()
    except BrowserBusy as e:
        log(str(e))
    except Exception as e:
        log("!! 运行异常: %s" % str(e).split("\n")[0])
        raise
    log("=== 结束 ===")


if __name__ == "__main__":
    # 以脚本方式运行时，模块名是 __main__。这里把它登记成 `mp_full`，
    # 于是 mp_cover_set / mp_check 里的 `import mp_full as M` 会**复用当前这个
    # 已经跑起来的模块**（同一份配置与日志），而不是把本文件再加载一遍。
    sys.modules["mp_full"] = sys.modules[__name__]
    main()
