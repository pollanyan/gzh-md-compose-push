# -*- coding: utf-8 -*-
"""把本地图片上传到微信图片库，并抓回每张图的 mmbiz URL。

正文里的 <img> 必须是 mmbiz.qpic.cn 的 URL，本地路径 / data-URI 都不生效，
所以「正文配图」这一步绕不开。

用法：
  python mp_imglib_upload.py 图1.png 图2.png ... [--out 输出目录]

产出：imglib_urls.json —— [{file, title, thumb, full}, ...]
  默认写到**当前工作目录**（文章模块通常就在那儿，它按 __file__ 找这个 json）。
  用 --out 可以指定到别处。

环境变量：MP_HEADLESS=0 可开有头模式看界面。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patchright.sync_api import sync_playwright  # noqa: E402

import mp_full as M  # noqa: E402

LIST_JS = """()=>[...document.querySelectorAll('.weui-desktop-img-picker__item')]
  .map(e=>{
    const t=e.querySelector('.weui-desktop-img-picker__img-title');
    const th=e.querySelector('.weui-desktop-img-picker__img-thumb');
    let url='';
    if(th){
      const bg=getComputedStyle(th).backgroundImage||'';
      const m=bg.match(/url\\(["']?([^"')]+)/);
      if(m) url=m[1];
      if(!url){const im=th.querySelector('img'); if(im) url=im.src||im.getAttribute('data-src')||'';}
    }
    if(!url){
      const any=[...e.querySelectorAll('*')].map(x=>{
        const s=getComputedStyle(x).backgroundImage||'';
        const mm=s.match(/url\\(["']?([^"')]+)/); return mm?mm[1]:'';}).filter(Boolean);
      url=any[0]||'';
    }
    return {title:((t&&t.innerText)||'').trim(), thumb:url,
            html:e.outerHTML.slice(0,300)};
  })"""


def main():
    args = sys.argv[1:]
    out_dir = os.getcwd()
    if "--out" in args:
        i = args.index("--out")
        out_dir = os.path.abspath(args[i + 1])
        del args[i:i + 2]
    paths = [os.path.abspath(a) for a in args if os.path.exists(a)]
    missing = [a for a in args if not os.path.exists(a)]
    if missing:
        M.log("!! 跳过不存在的文件: %s" % ", ".join(missing))
    if not paths:
        sys.exit("没有找到要上传的图片")
    names = [os.path.basename(p) for p in paths]
    M.log("待上传 %s 张 → %s" % (len(paths), ", ".join(names)))
    if len(set(names)) != len(names):
        M.log("!! 有重名文件，图片库里按文件名区分会混淆，建议先改名")

    with sync_playwright() as p:
        ctx = M.open_context(p)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        if not M.ensure_login(ctx, pg):
            ctx.close()
            return
        token = M.token_of(pg)
        if not token:
            M.log("!! 拿不到 token（登录态异常），无法打开图片库")
            ctx.close()
            return
        pg.goto(M.NEW_TPL % token, wait_until="domcontentloaded", timeout=60000)
        if not M.wait_editor(pg, timeout=60):
            M.log("!! 编辑器没就绪")
            ctx.close()
            return

        # 打开图片库
        pg.evaluate("""()=>{const e=document.querySelector('.js_cover_btn_area');
          if(e)e.scrollIntoView({block:'center'});}""")
        pg.wait_for_timeout(2000)
        geo = pg.evaluate("""()=>{const e=document.querySelector('.js_cover_btn_area');
          if(!e)return null;const r=e.getBoundingClientRect();
          return {x:r.x+r.width/2,y:r.y+r.height/2};}""")
        if geo:
            pg.mouse.click(geo["x"], geo["y"])
            pg.wait_for_timeout(2500)
        M.log("从图片库选择 -> %s" % M.click_text(pg, "从图片库选择"))
        pg.wait_for_timeout(6000)

        if not pg.evaluate("(s)=>!!document.querySelector(s)", M.DIALOG):
            M.log("!! 图片库弹窗没打开（登录态或页面结构变了），放弃")
            ctx.close()
            return

        before = [i["title"] for i in (pg.evaluate(LIST_JS) or [])]
        M.log("上传前库内条目=%s" % len(before))
        dup = [n for n in names if n in before]
        if dup:
            M.log("!! 库内已有同名图（不会新增，可能取到旧图）: %s" % ", ".join(dup))

        # 上传文件（accept 含 bmp 的那个 input 才是图片库通道；
        # accept 含 jpg/png 的是「正文插图」通道，用错会把封面图插进正文末尾）
        target = None
        for h in pg.query_selector_all("input[type=file]"):
            if "bmp" in (h.get_attribute("accept") or ""):
                target = h
                break
        if target is None:
            sys.exit("!! 找不到图片库 file input")
        target.set_input_files(paths)
        M.log("已提交 %s 个文件，等待上传…" % len(paths))
        pg.wait_for_timeout(3000)

        # 轮询等待新条目出现
        now = before
        for _ in range(24):
            now = [i["title"] for i in (pg.evaluate(LIST_JS) or [])]
            if len(now) >= len(before) + len(paths):
                break
            pg.wait_for_timeout(2500)
        M.log("上传后库内条目=%s（本次 +%s）" % (len(now), len(now) - len(before)))
        if len(now) < len(before) + len(paths):
            M.log("!! 入库数量没达标，可能有同名被跳过或超时，请核对下面的条目")
        pg.screenshot(path=M.SHOT % "imglib-uploaded")

        items = pg.evaluate(LIST_JS) or []
        out, empty = [], []
        for it in items:
            if not it["thumb"]:
                empty.append(it["title"])
                continue
            # 缩略图是 /300?wx_fmt=...，把 /300? 换成 /0? 就是原图
            out.append({"file": os.path.basename(it["title"]),
                        "title": it["title"],
                        "thumb": it["thumb"],
                        "full": it["thumb"].replace("/300?", "/0?")})
        if empty:
            M.log("!! 有 %s 个条目抓不到 URL（已跳过）: %s"
                  % (len(empty), ", ".join(empty[:5])))

        missing_url = [n for n in names if n not in [o["title"] for o in out]]
        if missing_url:
            M.log("!! 这些文件没在图片库里找到 URL: %s" % ", ".join(missing_url))

        os.makedirs(out_dir, exist_ok=True)
        out_json = os.path.join(out_dir, "imglib_urls.json")
        with open(out_json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        M.log("已写出 %s（%s 条）" % (out_json, len(out)))

        print(json.dumps(
            [{"title": o["title"], "full": o["full"][:110]} for o in out[-8:]],
            ensure_ascii=False, indent=2))
        ctx.close()


if __name__ == "__main__":
    main()
