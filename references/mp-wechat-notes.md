# 公众号后台浏览器通道 —— 实测踩坑清单

来源：from skill `wechat-mp-draft` v1.3.2（森智道）SKILL.md 提炼，全部为实测结论。
调用 mp_* 脚本前先读本文件；遇到失败优先在这里找对应条目。

## 认证与浏览器

- 入口 URL 必须是 `https://mp.weixin.qq.com/`。直接开 `/cgi-bin/home`（无 `?token=`）会被判「请重新登录」，误以为 cookie 失效。
- 独立 profile：`scripts/mp_profile/`（Cookies 在 `Default/Network/Cookies`）。与用户日常浏览器登录态不共享；与 WorkBuddy 是否登录无关。
- 登录态过期表现：脚本又去截二维码。`MP_LOGIN_WAIT` 默认 900 秒，登录成功立即返回。
- 二维码约 4 分钟刷新一次；用户要扫的是放大版 `mp-login-qrcode-big.png`（~490px），原始 122px 扫不出。
- profile 被占用（SingletonLock）→ 关残留 Chromium 进程或删 `mp_profile` 重新扫码。
- `logout` = 删 `mp_profile`，分享技能前必做。

## 编辑器 DOM（2026 版）

- 没有 iframe（老教程 `#ueditor_0` 已废弃）。正文 `.mock-iframe-body .ProseMirror`；标题 `.title-editor__input .ProseMirror`；署名 `input#author`；摘要 `textarea#js_description`。
- 填 HTML 唯一可靠路径：真实点击聚焦 → `ctx.grant_permissions(['clipboard-read','clipboard-write'], origin='https://mp.weixin.qq.com')` → `navigator.clipboard.write` 写 `text/html` → `Cmd+V`（macOS）/ `Control+V`（Windows/Linux）。修饰键必须按平台选——2026-11-25 实测 mac 上 Control+V 不触发粘贴（注入只剩 10 字符），Control+A 也不全选。
  无效做法：合成 `ClipboardEvent('paste')`、`document.execCommand('insertHTML')`、直接改 `innerHTML`。
- 粘贴后可能弹「内容结构检测」，必须点「继续插入」，否则内容被静默丢弃（不是每次都弹，轮询 8 秒）。
- 结构检测两条硬规则：文字背景禁渐变（CTA 用纯色）；`line-height` 不能小于 `font-size`（19px→1.45、17px→1.55、14/13px→1.6）。
- 不要手算点击坐标（正文可高 5000+px，scrollIntoView 后 rect.y 为负）；用 `pg.click(selector)` 让 Playwright 算。
- 保存成功判据：短文本 Toast（≤12 字，形如「保存成功/已保存」）或 URL 出现 `appmsgid`；都没有就重试一次。
- 编辑器会自动存草稿——打开新建页并输入标题就可能落一篇草稿，调试残留用 `mp_drafts.py delete "关键字" --yes` 清。

## 封面

- 封面区悬停才出菜单；页面有 3 个同名 `.js_cover_btn_area`，`querySelector` 拿到的往往不是能点的。
- 可靠做法：先存草稿拿 `appmsgid`，再用 `mp_cover_set.py` 重开这篇设封面（保存前设封面会静默失败）。
- 图片库弹窗里 accept 含 `bmp` 的 file input 才是封面通道；accept 含 jpg/png 的是正文插图，用错会把封面图插进正文末尾。
- 图片库条目是 `<i>` 的 background-image，不是 `<img>`；必须真实鼠标点击条目容器 `.weui-desktop-img-picker__item` 中心坐标，`element.click()` 不触发选中。
- 刚上传的图微信要转码：条目已出现但标题为空、显示进度条时选中它 → 裁剪弹窗永远转圈。等「标题 == 文件名」再选，最长 90 秒；等不到就放弃，绝不兜底选第 0 条（会设错封面）。
- 「下一步 / 确认」要限定在可见弹窗内点击（`.weui-desktop-dialog` + `offsetParent` 过滤）；按钮文案是「确认」不是「确定」。
- 判断封面成功：读 `#js_cover_area .js_cover_preview_new` 的 `background-image` 相对本次基线是否变化，不要数 `<img>`（封面是 background-image，占位文案始终在 DOM）。

## 图片

- 正文图必须是 `mmbiz.qpic.cn` URL；file:/// 和 data-URI 无效。用 `mp_imglib_upload.py` 上传后按文件名取 URL 拼进 HTML。
- 缩略图是 `/300?wx_fmt=png`，换成 `/0?` 是原图；粘贴后微信改写为 `/640?` 并加 `class="rich_pages wxw-img"` 属正常。
- 每张正文图后面 ProseMirror 插一个 `<img class="ProseMirror-separator" src="">`；数图/删图必须排除它，6 张图的 `img` 总数是 12。
- 图片库是账号级的，同名图不会新增；重复上传会造成多份。

## 核验

- `mp_check.py <appmsgid> [预期图数]`：退出后重开草稿核对，输出 PASS/FAIL。检查 title/author/digest 有值、bodyLen>20、realImgs==正文图数、封面非默认、原图尺寸。
- 草稿打不开三种形态：`系统错误(320003)` 草稿不存在、`此草稿已被删除`、`此草稿已发表`——不是选择器失效。

## 覆盖草稿

- `mp_full.py push <article.py> --appmsgid N` 覆盖指定草稿，避免半成品堆积。
- 草稿箱列表 DOM：一张卡 `.weui-desktop-publish__cover-item`，标题 `.weui-desktop-publish__cover__title`；操作组 `.weui-desktop-publish__opr` 悬停才浮出，组内第 1 个图标是删除、第 2 个是编辑。
- `mp_drafts.py delete` 每删一篇都重新拉列表比对标题，发现少了不含关键字的草稿立刻报警；删除按钮必须过滤 `offsetParent`（真假两个同名按钮）。
- 列表页可能有隐藏的「未授权使用切换账号能力」对话框——绝不要点它的「退出登录」。

## 短文章

- **微信编辑器会剥离 `<colgroup>/<col>`**（2026-11-25 手机实测：colgroup 里的
  列宽在公众号后台/手机端全部失效，table-layout:fixed 平分列宽；PC 浏览器预览
  正常所以此前未发现）。列宽必须同时写在**每个 th/td 的内联样式**上。
- 引用/正文的 `text-align` 必须显式写 `left`：微信手机端对未指定段落默认
  两端对齐，PC 浏览器默认左对齐——不写死则三端不一致（手机「两端对齐」实拍）。
- 引用段不加「QUOTE」等装饰性英文标签（用户定稿：影响阅读）。
- 旧版用魔数 `正文长度<=200` 判注入失败，导致短文被重复粘贴。现按预期非空白字符数判定（下限=预期×0.7），每次尝试前先 `Ctrl+A`+`Delete` 清空。
