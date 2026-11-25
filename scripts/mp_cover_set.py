# -*- coding: utf-8 -*-
"""给草稿设置封面（可单独重跑，不影响正文）。

关键：封面区是「悬停才出现操作菜单」的交互 —— 必须先把鼠标移到封面上，
再点菜单里的按钮，才能打开「从图片库选择」。

本文件既可当脚本跑，也可被 mp_full.py `import` 复用（`set_cover()`）。

用法：
  python mp_cover_set.py <appmsgid> <封面图.png>
  python mp_cover_set.py <appmsgid> <封面图.png> --no-save

环境变量：MP_HEADLESS=0 可开有头模式看界面。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patchright.sync_api import sync_playwright  # noqa: E402

import mp_full as M  # noqa: E402

# 封面是否已设置：封面是 background-image（不是 <img>），
# 所以用「相对本次运行开始时的背景图是否变化」来判断，最可靠。
COVER_STATE_JS = """(baseline)=>{
  const ca=document.querySelector('#js_cover_area');
  if(!ca) return {ok:false, why:'no area'};
  const pv=ca.querySelector('.js_cover_preview_new')||ca.querySelector('[class*=cover__preview]');
  let bg='';
  if(pv){ const s=getComputedStyle(pv).backgroundImage||'';
          const m=s.match(/url\\("?([^")]+)/); bg=m? m[1]:''; }
  const changed = !!bg && bg !== baseline;
  return {ok: changed, changed, baselineTail:(baseline||'').slice(-40),
          previewBgTail: bg.slice(-40),
          previewEl: !!pv};
}"""

MENU_JS = """()=>[...document.querySelectorAll('a,li,div,span,button')]
  .filter(e=>e.offsetParent && (e.innerText||'').trim().length>1
              && (e.innerText||'').trim().length<12)
  .filter(e=>/封面|图片库|正文选择|AI 配图|扫码/.test(e.innerText||''))
  .map(e=>({t:(e.innerText||'').trim(),
            cls:(e.className||'').toString().slice(0,50),
            r:(()=>{const b=e.getBoundingClientRect();
                    return Math.round(b.x)+','+Math.round(b.y)+','+
                           Math.round(b.width)+'x'+Math.round(b.height);})()}))
  .slice(0,20)"""

# 裁剪弹窗里的按钮，只认这几个 —— **不包含「保存」**，
# 否则万一页面上有独立的「保存」按钮会被误点。
CONFIRM_LABELS = ("下一步", "确认", "确定", "完成", "使用")

# 图片库条目：缩略图是 <i> 的背景图（不是 <img>），标题在 __img-title 里。
FIND_ITEM_JS = """(name)=>{
  const items=[...document.querySelectorAll('.weui-desktop-img-picker__item')];
  const idx=items.findIndex(e=>{
    const t=e.querySelector('.weui-desktop-img-picker__img-title');
    return t && (t.innerText||'').trim()===name;});
  return {idx, total:items.length,
          titles: items.slice(0,5).map(e=>((e.querySelector(
            '.weui-desktop-img-picker__img-title')||{}).innerText||'').trim())};
}"""


def _wait_item(pg, name, timeout=90):
    """轮询等待「标题 == name」的图片库条目出现。

    刚上传的图微信侧要转码，期间条目已在列表里但**标题是空串**
    （缩略图位置是一张白底绿进度条的占位卡）。此时若选中它，
    后面的「编辑封面」裁剪弹窗会一直转圈加载不完，最终封面设不上 ——
    所以必须等标题真的出现，才算这张图处理完了。
    """
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        last = pg.evaluate(FIND_ITEM_JS, name)
        if last.get("idx", -1) >= 0:
            return last
        pg.wait_for_timeout(2000)
    return last or {"idx": -1, "total": 0, "titles": []}


def _wait_crop_ready(pg, timeout=60):
    """等「编辑封面」裁剪弹窗加载完（转圈消失）。

    点「下一步」之后、图还没从 CDN 拉下来的那几秒里，弹窗只有「上一步」，
    这时点「确认」是空点，最后按 Escape 会把整个设封面流程取消掉。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        busy = pg.evaluate("""()=>{
          const ds=[...document.querySelectorAll('.weui-desktop-dialog')]
            .filter(e=>e.offsetParent);
          return ds.some(d=>[...d.querySelectorAll(
            '.weui-desktop-loading,[class*="loading"],[class*="spin"]')]
            .some(e=>e.offsetParent && e.getBoundingClientRect().width>4));
        }""")
        if not busy:
            return True
        pg.wait_for_timeout(1500)
    return False


def _baseline_bg(pg):
    return pg.evaluate("""()=>{const ca=document.querySelector('#js_cover_area');
      const pv=ca&&(ca.querySelector('.js_cover_preview_new')||ca.querySelector('[class*=cover__preview]'));
      if(!pv) return '';
      const s=getComputedStyle(pv).backgroundImage||'';
      const m=s.match(/url\\("?([^")]+)/); return m? m[1]:'';}""")


def _next_disabled(pg):
    return pg.evaluate("""()=>{
      const all=[...document.querySelectorAll('a,button,div,span')]
        .filter(e=>e.offsetParent && (e.innerText||'').trim()==='下一步');
      if(!all.length) return null;
      return all.map(e=>/disabled/.test((e.className||'').toString()));
    }""")


def set_cover(pg, appmsgid, cover, save=True):
    """在已登录的 page 上给草稿 appmsgid 设置封面。返回 True/False。

    save=True 时确认封面生效后才点「保存为草稿」。
    """
    cover = os.path.abspath(cover)
    base = os.path.basename(cover)
    M.log("目标封面=%s" % base)

    tok = M.token_of(pg)
    if not tok:
        M.log("!! 拿不到 token，无法设封面")
        return False
    pg.goto(M.EDIT_TPL % (appmsgid, tok), wait_until="domcontentloaded", timeout=60000)
    if not M.wait_editor(pg, timeout=60):
        M.log("!! 编辑器没就绪，放弃设封面")
        return False

    BASE_BG = _baseline_bg(pg)
    M.log("基线封面背景尾段=%s" % BASE_BG[-46:])
    if not BASE_BG:
        M.log("（基线为空 —— 可能是全新草稿还没封面，这是正常的）")

    # ---- 1) 滚到封面区并悬停 ----
    geo = pg.evaluate("""()=>{const e=document.querySelector('#js_cover_area');
      if(!e)return null; e.scrollIntoView({block:'center'});
      const r=e.getBoundingClientRect();
      return {x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)};}""")
    if not geo:
        M.log("!! 页面上没有 #js_cover_area")
        return False
    M.log("封面区中心=%s" % geo)
    pg.wait_for_timeout(1800)
    pg.mouse.move(geo["x"], geo["y"])
    pg.wait_for_timeout(1800)
    # 在封面上小范围晃动，触发 hover 菜单
    pg.mouse.move(geo["x"] - 20, geo["y"] - 10)
    pg.wait_for_timeout(600)
    pg.mouse.move(geo["x"] + 20, geo["y"] + 10)
    pg.wait_for_timeout(1500)
    M.log("悬停后可见菜单: %s" % json.dumps(pg.evaluate(MENU_JS), ensure_ascii=False))
    pg.screenshot(path=M.SHOT % "cs-1-hover")

    # ---- 2) 点开封面操作菜单 ----
    opened = pg.evaluate("""()=>{
      // 优先点悬停浮层里的按钮
      const scope=document.querySelector('.js_cover_preview_new')||document;
      const cands=[...scope.querySelectorAll('.js_cover_btn_area,.pop-opr__button,a,span')]
        .filter(e=>e.offsetParent);
      const hit=cands.find(e=>/封面/.test(e.innerText||''));
      if(hit){ (hit.closest('a,.js_cover_btn_area')||hit).click(); return 'clicked-menu:'+hit.innerText.trim(); }
      const b=scope.querySelector('.js_cover_btn_area');
      if(b){ b.click(); return 'clicked-btnarea'; }
      return 'none';
    }""")
    M.log("打开封面菜单 -> %s" % opened)
    pg.wait_for_timeout(2500)
    M.log("菜单项: %s" % json.dumps(pg.evaluate(MENU_JS), ensure_ascii=False))
    pg.screenshot(path=M.SHOT % "cs-2-menu")

    # ---- 3) 从图片库选择 ----
    r = M.click_text(pg, "从图片库选择")
    M.log("从图片库选择 -> %s" % r)
    if r != "clicked":
        # 兜底：直接点带 js_imagedialog 的按钮
        r2 = pg.evaluate("""()=>{const e=document.querySelector('a.js_imagedialog');
          if(!e) return 'no-el';
          if(e.offsetParent===null){const p=document.querySelector('#js_cover_null');
            if(p) p.style.display='block';}
          e.click(); return 'js-clicked';}""")
        M.log("兜底点击 -> %s" % r2)
    pg.wait_for_timeout(6000)
    pg.screenshot(path=M.SHOT % "cs-3-lib")

    # 图片库弹窗若没**真正显示**，后面全是白做，直接判失败
    # （注意：弹窗 DOM 一直都在，只查存在会误判，必须查可见性）
    if not pg.evaluate("(s)=>[...document.querySelectorAll(s)].some(e=>e.offsetParent)",
                       M.DIALOG):
        M.log("!! 图片库弹窗没打开，放弃（请在后台手动设封面）")
        return False

    # ---- 4) 上传文件到图片库（已有同名图则跳过，避免污染素材库）----
    res = _wait_item(pg, base, timeout=8)          # 已经在库里？
    if res.get("idx", -1) >= 0:
        M.log("图片库已有同名图，跳过上传")
    else:
        target = None
        for h in pg.query_selector_all("input[type=file]"):
            if "bmp" in (h.get_attribute("accept") or ""):
                target = h
                break
        if target is None:
            M.log("!! 找不到图片库上传 input，请在后台手动设封面")
            return False
        target.set_input_files(cover)
        M.log("已上传，等微信侧转码入库（最长 90s）…")
        res = _wait_item(pg, base, timeout=90)
    pg.screenshot(path=M.SHOT % "cs-4-uploaded")

    # ---- 5) 按文件名选中（真实鼠标点击 + 校验选中态）----
    # 缩略图是 <i class="...__img-thumb">，JS .click() 不会触发选中，
    # 必须用真实鼠标点击条目容器；选中后条目会带 .selected
    #
    # 等不到目标条目就**直接放弃**（不兜底选第 0 条）—— 兜底会把别的图
    # 设成这篇的封面，属于静默毁数据；宁可让人去后台手动设。
    if res.get("idx", -1) < 0:
        M.log("!! 等不到条目「%s」入库（现有：%s）—— 不做兜底选择，"
              "避免给这篇草稿设错封面。可到后台手动设封面。"
              % (base, " / ".join(res.get("titles") or []) or "(列表为空)"))
        return False
    M.log("目标条目: %s" % json.dumps(res, ensure_ascii=False))

    selected = False
    for attempt in range(4):
        box = pg.evaluate("""(i)=>{
          const items=[...document.querySelectorAll('.weui-desktop-img-picker__item')];
          const it=items[i]; if(!it) return null;
          it.scrollIntoView({block:'center'});
          const r=it.getBoundingClientRect();
          return {x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)}; }""", res["idx"])
        if not box:
            break
        pg.mouse.click(box["x"], box["y"])
        pg.wait_for_timeout(1500)
        st = pg.evaluate("""()=>{
          const items=[...document.querySelectorAll('.weui-desktop-img-picker__item')];
          const s=items.filter(e=>e.classList.contains('selected'));
          return {nSel:s.length,
                  titles:s.map(e=>((e.querySelector('.weui-desktop-img-picker__img-title')||{}).innerText||'').trim())};
        }""")
        M.log("  第%s次点击后选中项=%s" % (attempt + 1, json.dumps(st, ensure_ascii=False)))
        if st["nSel"] > 0:
            selected = True
            break
        pg.wait_for_timeout(1200)
    if not selected:
        M.log("!! 未能选中图片（下一步会是灰的）")
        pg.screenshot(path=M.SHOT % "cs-5-selected")
        return False
    pg.screenshot(path=M.SHOT % "cs-5-selected")

    nd = _next_disabled(pg)
    M.log("下一步按钮 disabled=%s" % nd)
    if nd and all(nd):
        M.log("!! 「下一步」是灰的，选图没生效，放弃（避免把状态点坏）")
        return False

    # ---- 6) 下一步 / 确认 ----
    # 点「下一步」后弹出的「编辑封面」裁剪弹窗，图片要联网加载 + 渲染裁剪预览，
    # 常见 5 秒后还在转圈（弹窗里只有「上一步」）。所以不能固定等待后只试一次，
    # 必须**轮询等待按钮出现**（最长 45s/步），否则会误判「封面未生效」而放弃。
    ok = False
    for step in range(8):
        hit = None
        t0 = time.time()
        while time.time() - t0 < 45:
            for label in CONFIRM_LABELS:
                if M.click_text(pg, label, scope=M.DIALOG) == "clicked":
                    hit = label
                    break
            if hit:
                break
            pg.wait_for_timeout(1500)
        M.log("步骤 %s -> %s（等待 %.0fs）" % (step, hit, time.time() - t0))
        if not hit:
            break
        pg.wait_for_timeout(4000)
        pg.screenshot(path=M.SHOT % ("cs-6-step%s" % step))
        if hit == "下一步":
            ready = _wait_crop_ready(pg)
            M.log("  裁剪弹窗加载完成=%s" % ready)
        st = pg.evaluate(COVER_STATE_JS, BASE_BG)
        M.log("  封面状态: %s" % json.dumps(st, ensure_ascii=False))
        if st.get("ok"):
            M.log("  ✓ 封面已生效，停止点击")
            ok = True
            break

    pg.keyboard.press("Escape")
    pg.wait_for_timeout(1500)
    st = pg.evaluate(COVER_STATE_JS, BASE_BG)
    ok = bool(st.get("ok"))
    M.log("最终封面状态: %s" % json.dumps(st, ensure_ascii=False))
    pg.screenshot(path=M.SHOT % "cs-7-final")

    # ---- 7) 保存 ----
    if save and ok:
        r = M.click_text(pg, "保存为草稿", sels="a,button,span,div")
        M.log("保存为草稿 -> %s" % r)
        pg.wait_for_timeout(7000)
        M.log("保存后 URL=%s" % pg.url)
    elif save:
        M.log("!! 封面未生效，不保存（避免把状态写坏）")
    return ok


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(argv) < 2:
        M.log("用法: python mp_cover_set.py <appmsgid> <封面图.png> [--no-save]")
        return
    appmsgid, cover = argv[0], argv[1]
    if not appmsgid.isdigit():
        M.log("!! appmsgid 应该是纯数字，收到: %s" % appmsgid)
        return
    if not os.path.exists(cover):
        M.log("!! 找不到封面图: %s" % cover)
        return
    save = "--no-save" not in sys.argv

    try:
        with sync_playwright() as p:
            ctx = M.open_context(p)
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                ctx.grant_permissions(["clipboard-read", "clipboard-write"],
                                      origin="https://mp.weixin.qq.com")
            except Exception:
                pass
            if M.ensure_login(ctx, pg):
                set_cover(pg, appmsgid, cover, save=save)
            ctx.close()
    except M.BrowserBusy as e:
        M.log(str(e))
    except Exception as e:
        M.log("!! 运行异常: %s" % str(e).split("\n")[0])
        raise


if __name__ == "__main__":
    main()
