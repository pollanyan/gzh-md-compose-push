---
name: gzh-md-compose-push
display_name: 公众号 Markdown 排版推送
display_name_en: GZH Markdown Compose & Push
description: "本技能用于将 Markdown 排版成微信公众号 HTML 并推送到草稿箱，内置浏览器扫码（默认，无需凭证）与官方 API（可选，需 AppID/AppSecret）双通道。提供 6 套主题预览、代码高亮、图片/封面上传、草稿覆盖与回读核验，并遵循三段式确认（排版方案→确认→本地文件→确认→推送）。当用户要求『公众号排版』『把 Markdown 转公众号格式』『推到公众号草稿箱』『发公众号但不想用 AppID』『个人公众号推草稿』，或明确要求『用 API/接口方式推送』时，应使用本技能。"
description_zh: "将 Markdown 排版成公众号 HTML 并推送到草稿箱：6 主题深浅配色、扫码/API 双通道、插图自动上传、合规校验。"
description_en: "Compose Markdown into styled WeChat Official Account HTML and push it to the draft box: 6 themes with light/dark schemes, QR/API channels, auto image upload, and compliance validation."
author: pollanyan
version: 1.0.0
license: MIT
agent_created: true
---

# 公众号 Markdown 排版推送（扫码 + API 双通道）

## 目的与边界

把一篇 Markdown 转成公众号可粘贴的合规 HTML，并推送到草稿箱。本技能**同时内置两条通道**：浏览器扫码（默认，无需凭证）与官方 API（可选，需 AppID/AppSecret）。两条通道都在本技能 `scripts/` 内，不依赖其它技能。

## 推送通道选择（默认扫码，API 需明确指定）

- **默认通道 = 浏览器扫码**（`scripts/mp_full.py`）。任何「推到公众号草稿箱」的请求一律先走扫码，不得主动改用接口。
- **可选通道 = 官方 API**（`scripts/wx_api_publish.py`，本技能内置）。只有当用户**明确说出**「用接口 / 用 API / 走官方 API / 我有 AppID」等字样并主动提供凭证时才用；用户未明确指定时，即使环境里有 AppID/Secret 也不要用。
- 使用 API 通道时：凭证用环境变量 `WX_APPID` / `WX_APPSECRET` 提供，不写入脚本、不落盘。先跑 `config-check`；若报 40164，提示用户**到公众号后台「开发设置 / IP 白名单」添加本机公网出口 IP**（微信按 TCP 源 IP 校验，客户端改配置/请求头无法绕过）；个人未认证号报 48001 时提示改用扫码通道或先完成认证。
- 不要因「API 更快 / 更省事」自行切换；通道选择权永远在用户。

**硬边界（务必先与用户对齐）：**
- 只写**草稿箱**，**绝不点「发表/群发/发布」**——发布权永远留给用户。
- 用技能自带的独立浏览器 profile（`scripts/mp_profile/`），与用户日常 Chrome 登录态**不共享**；第一次或登录态过期时必须扫码。
- 三段式确认，每段都要等用户明确同意才进入下一段，**不得一口气跑完**：
  1. 排版方案（主题选哪套 + 章节结构）→ 用户确认
  2. 生成本地 HTML + 预览页 → 用户确认满意
  3. 推送草稿箱（重复推送时先问覆盖还是新建）→ 用户确认

## 目录结构

```
scripts/
  md_to_gzh.py            # Markdown→公众号 HTML（6 主题 + 代码高亮 + 合规）
  validate_gzh_html.py    # 平台合规校验（ERROR 必须清零）
  wrap_preview.py         # 生成带「复制到公众号」按钮的预览页
  wx_api_publish.py       # API 可选通道：config-check/list/push/del（纯标准库）
  mp_full.py              # 扫码默认通道：登录 / 建草稿 / 覆盖草稿 / 正文注入
  mp_check.py             # 草稿回读核验（PASS/FAIL）
  mp_drafts.py            # 列出/删除草稿
  upload_md_images.py     # 扫描 Markdown 插图，上传微信图床并替换 src
  mp_imglib_upload.py     # 正文配图上传到微信图床
  mp_cover_set.py         # 单独设置/更换封面
templates/
  article_template.py     # 文章模块模板（TITLE/DIGEST/AUTHOR/build_content）
assets/
  preview-template.html   # wrap_preview.py 依赖的预览外壳
references/
  user-conventions.md     # 用户排版特殊约定（超链接/角标/三层/列宽/来源/高亮）★ 必读
  browser-tool-contract.md # 扫码通道契约：把后台操作翻译成 Agent 自带浏览器工具调用 ★ 扫码必读
  mp-wechat-notes.md      # 微信编辑器踩坑清单（粘贴/封面/图片/核验）
  ecosystem-survey.md     # 本次生态盘点与方案对比
doc/
  方案设计规格.md          # 设计规格（需求结论 / 参考技能取证 / 生态盘点 / 验证记录）
requirements.txt          # patchright（仅扫码脚本路径需要，纯排版零依赖）
```

## 工作流

### 第 0 步：环境准备（按需，不预装）

依赖按需触发，不要预先手工安装：

- 纯排版 / 校验 / 预览的三个脚本只用标准库，**零依赖**。
- **扫码通道优先复用 Agent 自带的浏览器工具**，按 `references/browser-tool-contract.md` 的精确契约执行：推送前先探测宿主暴露的浏览器工具（MCP / skill / CLI 均可），**按能力适配**——能导航、能执行页面 JS、能发真实按键、能上传文件、有独立持久化 profile——再把契约里的 URL / 选择器 / JS / 判据翻译成该工具的具体调用。这条路不需要 patchright。
- 只有宿主没有任何浏览器工具、或其接口做不到「写 text/html 剪贴板 + 发 Ctrl+V + 上传文件 + 独立持久化 profile」时，才改用技能自带的 `mp_*.py` 脚本路径：它们依赖 `patchright`（几 MB 驱动库，缺失时脚本会提示 `python3 -m pip install patchright`），浏览器内核自动探测系统已装 Chrome/Edge/Chromium，普通用户无需预下载 Chromium。
- API 通道：`wx_api_publish.py` 纯标准库，只需凭证。

两种扫码执行器跑的是**同一份契约**（见 `references/browser-tool-contract.md`），差别只在调用方式：工具路径由 Agent 调 MCP / CLI 接口，脚本路径由 patchright 实现同一组单元。不要把「用 Agent 工具」当成自然语言自由发挥——每一步的 URL、选择器、JS、判据都是写死的。

**注意解释器一致性**：走 `mp_*.py` 脚本路径时，必须用装了 patchright 的那个 python；排版三脚本与 API 脚本用任意 python3 即可。

选择脚本路径时，后续所有脚本用 `python3 <SKILL>/scripts/<脚本>` 绝对路径调用。

### 第 1 步：排版方案（先确认，不落地）

1. 读取用户的 Markdown（路径或正文）。
2. **插图预处理**：若 Markdown 含 `![...](...)`，先上传图片并替换地址；本地路径、http/https 地址、data URI 都支持：
   ```bash
   python3 <SKILL>/scripts/upload_md_images.py <article.md> -o <article>_微信图.md
   ```
   这一步会调用 `mp_imglib_upload.py` 上传图片库并写出新 Markdown，后续排版一律用输出文件。没有插图时脚本原样写出。
3. **主题预览**：先跑一次生成全部主题的预览页，让用户直观挑选：
   ```bash
   python3 <SKILL>/scripts/md_to_gzh.py <article>_微信图.md --all-themes --preview-dir <工作区>/themes
   ```
   打开 `<工作区>/themes/index.html`，列出 6 套主题（摸鱼绿/红白色系/石墨极简风/留白禅意风/摸鱼票据风/橄榄手记），每套均有 浅色/深色 两种配色预览，请用户选一套（主题 + 配色）。用户偏好深色阅读时推荐 `--scheme dark`（写死的深底浅字卡片，读者任何模式下都稳定）。
4. 用 AskUserQuestion 给出：主题选项 + 章节结构概述 + 是否需要封面图。**封面路径在这里一次性收集**，推送时直接使用；用户不给就留空，后续不再追问。
5. **停下等用户确认**。未确认前不生成最终文件。

### 第 2 步：生成本地文件（再确认）

用户确认方案后：

```bash
python3 <SKILL>/scripts/md_to_gzh.py <article>_微信图.md --theme <标识> -o <文章名>_排版_<主题>.html
python3 <SKILL>/scripts/validate_gzh_html.py <上面.html>          # 必须 0 ERROR / 0 WARNING
python3 <SKILL>/scripts/wrap_preview.py <上面.html>               # 产出 _预览.html
```

- 校验有 ERROR 就回转换器修，不得交付带 ERROR 的产物。
- 把 `_预览.html` 用 present_files 打开给用户看，并说明：代码块是**每行一个 leaf + 行内彩色 span**（这是修正过的关键点——早期逐 token 一个 leaf 会被公众号拆行、缩进错位）。
- **停下等用户确认满意**。不满意就回到第 1 步重来（换主题/改结构），不推送。

### 第 3 步：推送草稿箱（最后确认）

用户确认本地文件后，先按 `references/browser-tool-contract.md` 探测宿主浏览器工具，决定执行器：

- **有浏览器工具**：按契约第一节的能力清单适配（任何接口等价的 MCP / skill / CLI 都行），用该工具的接口执行登录、写标题、正文注入、上传图片、保存、设封面、回读核验；每一步的判据与「必读」踩坑清单一致。不装 patchright。
- **无浏览器工具或接口不满足契约**（不能写 text/html 剪贴板、不能上传文件、无独立 profile）：用下面的 `mp_*.py` 脚本路径。

1. **先问覆盖还是新建**（这是重复推送的必问项）：
   - 用 `mp_drafts.py list` 列出草稿箱现有草稿，让用户看标题。
   - AskUserQuestion：『覆盖同标题旧草稿』/『新建一篇草稿』。
   - 覆盖需拿到旧草稿的 `appmsgid`（列表里可查），推送时带 `--appmsgid N`。
2. **首次扫码**（登录态过期时脚本会自动再截二维码）：
   ```bash
   python3 <SKILL>/scripts/mp_full.py login
   ```
   脚本产出 `scripts/mp-login-qrcode-big.png`（放大版）——用 present_files 给用户扫。等 900 秒，登录成功自动返回并删除二维码文件。
3. **准备文章模块**：复制 `templates/article_template.py` 到工作区，填 `TITLE`（≤64 字）、`DIGEST`（≤120 字）、`AUTHOR`，`build_content()` 返回第 2 步的 HTML 文件内容：
   ```python
   TITLE = "文章标题"; DIGEST = "摘要"; AUTHOR = ""
   def build_content():
       return open("<文章名>_排版_<主题>.html", encoding="utf-8").read()
   ```
4. **推送**（正文图已在第 1 步上传并替换；有封面加 `--cover`，无封面则草稿封面留空）：
   - 工具路径：按契约执行同一组单元（标题 / 正文 / 保存 / 封面 / 核验）。
   - 脚本路径：
   ```bash
   python3 <SKILL>/scripts/mp_full.py push <文章模块.py> [--appmsgid N] [--cover 封面.png]
   ```
5. **回读核验**（必做）：保存后 URL 里出现 `appmsgid`，用它核验：
   ```bash
   python3 <SKILL>/scripts/mp_check.py <appmsgid> [预期图片数]
   ```
   输出 `RESULT: PASS` 才算推送成功；FAIL 就按 references 的踩坑清单排查。
6. 报告：草稿标题、appmsgid、核验结果，并再次提醒**发布需用户自己到后台点**。

### 第 3 步之 API 备选通道（用户明确要求时才用）

仅当用户明确说「用 API / 接口方式」并提供凭证时执行：

1. 让用户以环境变量提供凭证：`export WX_APPID=wx...`、`export WX_APPSECRET=...`（不写入脚本、不落盘）。
2. `python3 <SKILL>/scripts/wx_api_publish.py config-check` 检查凭证与连通性：
   - 报 **40164**：提示用户到公众号后台「设置与开发 / 开发设置 / IP 白名单」添加本机公网出口 IP（`curl ifconfig.me` 可查），微信按 TCP 源 IP 校验，客户端无法绕过；加白后重试。
   - 报 **48001**：个人未认证号无接口权限，提示改用扫码通道或先完成认证。
3. 排版方案与本地 HTML 仍走第 1、2 步的三段式确认。
4. `python3 <SKILL>/scripts/wx_api_publish.py push <排版.html> --title '标题' [--digest '摘要'] [--author ''] [--cover 图.png]` 创建草稿（只调 `draft/add`，不调发布类接口）。
5. 报告 media_id，提醒到后台草稿箱手动发布；`list` / `del <media_id>` 管理草稿，`clear-token` 在换 IP/换凭证后清缓存。

## 必读 reference：`references/user-conventions.md`

生成任何 HTML 前先读它。里面固化了用户多轮返工后的硬约定，转换器已按此实现：
- 正文**零超链接**，来源走「附：取证来源」大章节 + References 纯文本 URL；
- `[[N]]` → `#2563EB` 蓝色 **右上角上标**（`vertical-align:super; font-size:10px`）；
- 三层对照用「图 + 强/平/弱状态表」（强=已覆盖/更优、平=有边界差异、弱=不可插件化）；
- 表格按内容比例列宽（`<colgroup>` + `table-layout:fixed`），**不无脑加宽**，表头无底色、全左对齐；
- 行内代码蓝色 `#2563EB` 无底色；正文每段 1–3 处下划线标记；章节 44px 大编号 + 英文标签；
- 签名区不写死人名（用占位或用户给的署名），仅末尾一处。

## 关键实现依据（修复的坑）

- **代码高亮拆行 bug**：公众号把每个 `<span leaf>` 当原子节点重排。逐 token 一个 leaf 会让 `export const X = [` 被拆成 5 行、缩进错位、行距撑大。`md_to_gzh.py` 改为**每行一个 leaf，行内用不带 leaf 的彩色 span**，颜色保留且排版稳定。校验器已验证合规。**绝不改回图片方案**（用户明确否决）。
- **扫码登录**：patchright（Playwright stealth 分支）+ 独立 Chromium profile，二维码是 `.login__type__container__scan__qrcode`，放大 4 倍截图给用户扫；登录态存 `scripts/mp_profile/Default/Network/Cookies`，**分享技能前必须删除此目录**（含完整后台登录态）。
- **正文注入**：编辑器是 ProseMirror（`.mock-iframe-body .ProseMirror`，2026 版无 iframe）。唯一可靠的 HTML 注入方式是 `clipboard.write(text/html)` + `Control+V` + 点「继续插入」；合成 paste 事件/insertHTML/改 innerHTML 都无效。
- **只存草稿**：`mp_full.py` 的 `click_text` 内置「发表/群发/发布」黑名单，杜绝误点。
- 其它踩坑见 `references/mp-wechat-notes.md`（封面悬停菜单、图片库真实点击、ProseMirror-separator、短文章判据等）。

## 安全

- 登录态目录 `scripts/mp_profile/` 是公众号后台完整 Cookies，**绝不外传**；`mp_full.py logout` 一键清除。
- 二维码文件是活码，登录后脚本自动删除；不要手工留存。
- 校验器 `validate_gzh_html.py` 的 ERROR 必须清零；WARNING 也要检查到 0（半角标点在代码区内豁免）。
