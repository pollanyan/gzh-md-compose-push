# -*- coding: utf-8 -*-
"""核查草稿：标题 / 署名 / 摘要 / 正文长度 / 真实图片数 / 封面，并给 PASS/FAIL 结论。

保存后**退出再重开**这篇草稿来读，不要只看保存瞬间的界面。

用法：python mp_check.py <appmsgid> [预期图片张数]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patchright.sync_api import sync_playwright  # noqa: E402

import mp_full as M  # noqa: E402

PROBE_JS = """()=>{
  const t=document.querySelector('.title-editor__input .ProseMirror');
  const b=document.querySelector('.mock-iframe-body .ProseMirror');
  const au=document.querySelector('#author');
  const ds=document.querySelector('#js_description');
  const all=b?[...b.querySelectorAll('img')]:[];
  // .ProseMirror-separator 是 ProseMirror 给每张图补的占位 img，不算真图
  const real=all.filter(i=>!(i.className||'').toString().includes('ProseMirror-separator'));
  const ca=document.querySelector('#js_cover_area');
  let coverUrl='';
  if(ca){
    const pv=ca.querySelector('.js_cover_preview_new')||ca.querySelector('[class*=cover__preview]');
    if(pv){ const s=getComputedStyle(pv).backgroundImage||'';
            const m=s.match(/url\\("?([^")]+)/); coverUrl=m? m[1]:''; }
  }
  return {
    title: t?t.innerText.trim():'(no title el)',
    author: au?au.value:'',
    digest: ds?ds.value:'',
    bodyLen: b?b.innerText.length:-1,
    imgCount: all.length,
    realImgs: real.length,
    realImgSizes: real.map(i=>i.naturalWidth+'x'+i.naturalHeight),
    separators: all.length-real.length,
    coverUrl,
    coverIsDefault: !coverUrl || /^data:/.test(coverUrl),
    imgParents: real.slice(0,3).map(i=>{
      const p=[]; let e=i;
      for(let k=0;k<3&&e;k++){p.push(e.tagName+(e.className?'.'+String(e.className).split(' ')[0]:''));e=e.parentElement;}
      return p.join(' < ');}),
  };
}"""


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not argv:
        print("用法: python mp_check.py <appmsgid> [预期图片张数]")
        return
    appmsgid = argv[0]
    expect = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else None

    with sync_playwright() as p:
        ctx = M.open_context(p)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        if not M.ensure_login(ctx, pg):
            ctx.close()
            return
        token = M.token_of(pg)
        if not token:
            print("!! 拿不到 token（登录态异常），无法打开草稿")
            print("RESULT: FAIL(登录态异常)")
            ctx.close()
            return
        pg.goto(M.EDIT_TPL % (appmsgid, token), wait_until="domcontentloaded",
                timeout=60000)
        err = ""
        for _ in range(20):
            pg.wait_for_timeout(1000)
            err = M.page_error(pg)
            if err:
                break
            try:
                if pg.evaluate("(s)=>!!document.querySelector(s)", M.BODY_SEL):
                    break
            except Exception:
                pass
        if err:
            print("!! 这篇草稿打不开: %s" % err)
            print("RESULT: FAIL(草稿不可用)")
            ctx.close()
            return
        if not M.wait_editor(pg, timeout=60):
            print("!! 编辑器没就绪，核验失败")
            print("RESULT: FAIL(编辑器未就绪)")
            ctx.close()
            return

        out = pg.evaluate(PROBE_JS)
        pg.screenshot(path=M.SHOT % "check-body", full_page=True)
        ctx.close()

    out["appmsgid"] = appmsgid
    print(json.dumps(out, ensure_ascii=False, indent=2))

    # ---- PASS / FAIL ----
    checks = []
    checks.append(("标题非空", bool(out["title"]) and out["title"] != "(no title el)"))
    checks.append(("标题≤64字", len(out["title"]) <= 64))
    # 署名以配置项 author（scripts/push_config.py 管理）为预期值：
    # 配置非空 → 草稿署名须一致；配置为空（默认留空）→ 草稿为空即 PASS。
    try:
        import push_config
        _expect_author = push_config.load()["author"]
    except Exception:
        _expect_author = ""
    if _expect_author:
        checks.append(("署名与配置一致(%s)" % _expect_author, out["author"] == _expect_author))
    else:
        checks.append(("署名留空(默认)", out["author"] == ""))
    checks.append(("摘要已填", bool(out["digest"])))
    # 不写死 200 字下限：短文是合法的，长度该由调用方判断。
    # 给了「预期图片张数」时，正文有图就说明注入成功；纯文字文章则只看非空。
    checks.append(("正文非空", out["bodyLen"] > 20))
    checks.append(("封面非默认", not out["coverIsDefault"]))
    if expect is not None:
        checks.append(("真图=%s张" % expect, out["realImgs"] == expect))
    else:
        checks.append(("正文有真图", out["realImgs"] > 0))

    print("\n--- 核验 ---")
    bad = 0
    for name, ok in checks:
        print("  %s %s" % ("PASS" if ok else "FAIL", name))
        bad += 0 if ok else 1
    print("  标题: %s" % out["title"])
    print("  正文长度: %s 字 / 真图 %s 张（另有 %s 个 ProseMirror 占位符）"
          % (out["bodyLen"], out["realImgs"], out["separators"]))
    print("  图片尺寸: %s" % ", ".join(out["realImgSizes"][:8]))
    print("  封面: %s" % ("默认占位（未设）" if out["coverIsDefault"] else out["coverUrl"][-90:]))
    print("RESULT: %s" % ("PASS" if bad == 0 else "FAIL(%s)" % bad))


if __name__ == "__main__":
    main()
