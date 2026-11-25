# -*- coding: utf-8 -*-
"""草稿箱管理：列出现有草稿 / 按标题关键字删除草稿。

为什么单独做一个：`--appmsgid` 覆盖只能覆盖你知道 ID 的那一篇。实际场景里
「上次跑失败留下的半成品」「调试产生的垃圾草稿」都得先看见才能处理。
以前只能靠人肉点后台，这里把实测出来的 DOM 结构固化下来。

用法：
  python mp_drafts.py list
  python mp_drafts.py delete "关键字"            # 只删标题含关键字的草稿
  python mp_drafts.py delete "关键字" --yes      # 跳过二次确认（供自动化调用）

环境变量：MP_HEADLESS=0 可开有头模式看界面。

⚠️ 本脚本**只删草稿**，永不点「发表」；也不会碰弹窗里的「退出登录」。

实测到的结构（改版时照这个找）：
  .weui-desktop-publish__cover-item       一张草稿卡（标题 + 更新时间）
  .weui-desktop-publish__opr              悬停才浮出的操作组
    a.weui-desktop-icon20.weui-desktop-icon-btn  第 1 个 + tooltip「删除」= 删除
    span.publish_enable_button / a...link_send-multi              = 发表
  删除图标点下去后，同组里**预渲染但隐藏**的 BUTTON「删除」/「取消」变为可见。
  注意：这些元素即便隐藏也存在于 DOM，所以取按钮必须过滤 offsetParent。
"""
import sys

import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patchright.sync_api import sync_playwright  # noqa: E402

import mp_full as M  # noqa: E402

LIST_URL = ("https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=list"
            "&type=77&begin=0&count=20&token=%s&lang=zh_CN")

CARDS_JS = """()=>[...document.querySelectorAll('.weui-desktop-publish__cover-item')]
  .map(e=>({title:((e.querySelector('.weui-desktop-publish__cover__title')||{}).innerText||'').trim(),
            tip:((e.querySelector('.weui-desktop-publish__tips')||{}).innerText||'').trim(),
            hasCover:!!(e.querySelector('img')||/url\\(/.test(
              getComputedStyle(e).backgroundImage||''))}))"""

FIND_JS = """(kw)=>{
  const items=[...document.querySelectorAll('.weui-desktop-publish__cover-item')];
  const oprs=[...document.querySelectorAll('.weui-desktop-publish__opr')];
  const idx=items.findIndex(e=>(e.innerText||'').includes(kw));
  if(idx<0) return null;
  const it=items[idx];
  it.scrollIntoView({block:'center'});
  const r=it.getBoundingClientRect();
  // 删除图标在「操作组」里，而操作组跟卡片是兄弟节点。必须配对到**这张**卡片的
  // 操作组，顺序：① 同一父容器里的那个 → ② 按同索引配对 → ③ 纵向中心离这张卡最近的。
  // 老代码直接退到「页面第一个 .weui-desktop-publish__opr」：一旦配对错位，
  // 就会点到别的草稿的删除图标——那是真的会删错东西的。
  const sib=it.parentElement? it.parentElement.querySelector('.weui-desktop-publish__opr') : null;
  let opr=sib, paired='sibling';
  if(!opr && oprs[idx]){ opr=oprs[idx]; paired='index'; }
  if(!opr){
    let best=null, bestD=Infinity;
    for(const o of oprs){
      const b=o.getBoundingClientRect();
      const d=Math.abs((b.y+b.height/2)-(r.y+r.height/2));
      if(d<bestD){ bestD=d; best=o; }
    }
    opr=best; paired=opr? 'nearest':'none';
  }
  const icon=opr? opr.querySelector('a.weui-desktop-icon-btn') : null;
  const b=icon? icon.getBoundingClientRect() : null;
  return {idx, paired,
          nHits:items.filter(e=>(e.innerText||'').includes(kw)).length,
          title:(it.innerText||'').trim().slice(0,40),
          card:{x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)},
          icon:b? {x:Math.round(b.x+b.width/2), y:Math.round(b.y+b.height/2)} : null};
}"""


def open_list(pg):
    tok = M.token_of(pg)
    pg.goto(LIST_URL % tok, wait_until="domcontentloaded", timeout=60000)
    for _ in range(30):
        pg.wait_for_timeout(1000)
        if pg.evaluate("(s)=>!!document.querySelector(s)",
                       ".weui-desktop-publish__cover-item"):
            break
        if M.page_error(pg):
            break
    return pg.evaluate(CARDS_JS) or []


def main():
    args = sys.argv[1:]
    mode = args[0] if args else "list"
    yes = "--yes" in args
    kw = args[1] if len(args) > 1 and not args[1].startswith("--") else ""

    if mode == "delete" and not kw:
        print("用法: python mp_drafts.py delete \"标题关键字\" [--yes]")
        return
    if mode not in ("list", "delete"):
        print("用法: python mp_drafts.py list | delete \"关键字\" [--yes]")
        return

    with sync_playwright() as p:
        ctx = M.open_context(p)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        if not M.ensure_login(ctx, pg):
            ctx.close()
            return

        cards = open_list(pg)
        print("草稿箱现有 %s 篇:" % len(cards))
        for i, c in enumerate(cards, 1):
            print("  %s. %s  [%s]%s" % (i, c["title"] or "(无标题)", c["tip"],
                                        "" if c["hasCover"] else "  (无封面)"))

        if mode == "list":
            ctx.close()
            return

        matched = [c for c in cards if kw in c["title"]]
        if not matched:
            print("没有标题含「%s」的草稿，未做任何改动" % kw)
            ctx.close()
            return
        print("\n将删除 %s 篇标题含「%s」的草稿：" % (len(matched), kw))
        for c in matched:
            print("  - %s" % c["title"])
        if not yes:
            try:
                ans = input("确认删除？输入 yes 继续: ").strip().lower()
            except EOFError:                      # 非交互环境（自动化调用）
                ans = ""
            if ans != "yes":
                print("已取消（自动化调用请加 --yes）")
                ctx.close()
                return

        # 逐篇删。每轮都重新拉列表、重新定位坐标（页面重排后旧坐标会失效）。
        # 每删一篇都比对一次标题清单：少了**不该少**的就在日志里报警 ——
        # 万一操作组配对错位删错了，能立刻看见，而不是悄悄删掉别人的草稿。
        prev_titles = [c["title"] for c in cards]
        for round_no in range(len(matched) + 3):
            if not [c for c in cards if kw in c["title"]]:
                break
            info = pg.evaluate(FIND_JS, kw)
            if not info or not info.get("icon"):
                print("!! 找不到删除图标，停手（后台可能改版了）")
                break
            M.log("删除第 %s 篇: %s（操作组配对=%s）"
                  % (round_no + 1, info["title"], info.get("paired")))
            pg.mouse.move(info["card"]["x"], info["card"]["y"])
            pg.wait_for_timeout(2000)
            pg.mouse.click(info["icon"]["x"], info["icon"]["y"])
            pg.wait_for_timeout(2000)
            r = pg.evaluate("""()=>{
              const bs=[...document.querySelectorAll('button,a')].filter(e=>e.offsetParent
                && (e.innerText||'').trim()==='删除');
              if(!bs.length) return 'no-confirm-btn';
              const el=bs[bs.length-1]; (el.closest('button,a')||el).click();
              return 'clicked-confirm';}""")
            M.log("  确认 -> %s" % r)
            pg.wait_for_timeout(6000)

            cards = open_list(pg)
            now_titles = [c["title"] for c in cards]
            gone = [t for t in prev_titles if t not in now_titles]
            wrong = [t for t in gone if kw not in t]
            M.log("  本轮消失 %s 篇%s" % (len(gone),
                                        ("：" + " / ".join(gone)) if gone else ""))
            if wrong:
                M.log("  !! 其中有不含「%s」的：%s —— 疑似删错，请立刻人工核对草稿箱"
                      % (kw, " / ".join(wrong)))
            prev_titles = now_titles

        left = [c for c in cards if kw in c["title"]]
        print("\n结果：剩余 %s 篇，其中标题含「%s」的 %s 篇" % (len(cards), kw, len(left)))
        ctx.close()


if __name__ == "__main__":
    main()
