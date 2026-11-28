---
name: gzh-md-compose-push
display_name: 公众号排版与发布助手(Obsidian/Markdown)
display_name_en: GZH Markdown Compose & Push
description: "把 Markdown 与 Obsidian 笔记排版成公众号 HTML，并推送到公众号草稿箱：6 套主题（深浅两版）、本地与网络图片上传、代码高亮、Obsidian Callout 渲染。默认微信扫码免 AppID，可选官方 API（需 AppID/AppSecret）；排版方案→本地预览→推送草稿箱三段确认，全程可控。只写草稿，绝不代发布。"
description_zh: "把 Markdown 与 Obsidian 笔记排版成公众号 HTML，并推送到公众号草稿箱：6 套主题（深浅两版）、本地与网络图片上传、代码高亮、Obsidian Callout 渲染。默认微信扫码免 AppID，可选官方 API（需 AppID/AppSecret）；排版方案→本地预览→推送草稿箱三段确认，全程可控。只写草稿，绝不代发布。"
description_en: "Turn Markdown and Obsidian notes into styled WeChat HTML and push to the draft box — six themes in light and dark variants, local and web image upload, syntax highlighting, and native Obsidian callout rendering. WeChat QR login by default with no AppID required; official API is optional (AppID/AppSecret). Three-step confirmation — layout plan, local preview, draft push — keeps you in control. Drafts only; never published on your behalf."
examples_zh:
  - "把这篇 Markdown 排版成公众号文章，先看石墨极简风预览"
  - "把这篇 Obsidian 笔记排版成公众号文章，先看石墨极简风预览"
  - "把改好的稿子覆盖到原来那篇公众号草稿"
examples_en:
  - "Format this Markdown into a WeChat article and show me a graphite-minimal preview first"
  - "Format this Obsidian note into a WeChat article and show me a graphite-minimal preview first"
  - "Overwrite the existing WeChat draft with my revised article"
author: 严宝亮
version: 1.0.1
license: MIT
agent_created: true
---

# 公众号排版与发布助手(Obsidian/Markdown)（扫码 + API 双通道）

## 目的与边界

把一篇 Markdown 转成公众号可粘贴的合规 HTML，并推送到草稿箱。本技能**同时内置两条通道**：浏览器扫码（默认，无需凭证）与官方 API（可选，需 AppID/AppSecret）。两条通道都在本技能 `scripts/` 内，不依赖其它技能。

## 推送通道选择（默认扫码，API 需明确指定）

- **默认通道 = 浏览器扫码**（`scripts/mp_full.py`）。任何「推到公众号草稿箱」的请求一律先走扫码，不得主动改用接口。
- **可选通道 = 官方 API**（`scripts/wx_api_publish.py`，本技能内置）。只有当用户**明确说出**「用接口 / 用 API / 走官方 API / 我有 AppID」等字样并主动提供凭证时才用；用户未明确指定时，即使环境里有 AppID/Secret 也不要用。
- 使用 API 通道时：凭证用环境变量 `WX_APPID` / `WX_APPSECRET` 提供，不写入脚本、不落盘。先跑 `config-check`；若报 40164，提示用户**到公众号后台「开发设置 / IP 白名单」添加本机公网出口 IP**（微信按 TCP 源 IP 校验，客户端改配置/请求头无法绕过）；个人未认证号报 48001 时提示改用扫码通道或先完成认证。
- 不要因「API 更快 / 更省事」自行切换；通道选择权永远在用户。

**硬边界（务必先与用户对齐）：**
- 只写**草稿箱**，**绝不点「发表/群发/发布」**——发布权永远留给用户。
- 脚本路径用独立的浏览器 profile（`~/.config/gzh-md-compose-push/mp_profile`，可用 `GZH_MP_RUNTIME` 改目录），与用户日常 Chrome 登录态**不共享**、也不放进技能目录；第一次或登录态过期时必须扫码。
- 三段式确认，每段都要等用户明确同意才进入下一段，**不得一口气跑完**：
  1. 排版方案（主题选哪套 + 章节结构）→ 用户确认
  2. 生成本地 HTML + 预览页 → 用户确认满意
  3. 推送草稿箱（重复推送时先问覆盖还是新建）→ 用户确认

## 目录结构

```
scripts/
  obsidian_preprocess.py  # Obsidian 稿预处理：frontmatter/callout/内部引用双场景/块嵌入 → 纯净 Markdown
  md_to_gzh.py            # Markdown→公众号 HTML（6 主题 + 代码高亮 + 合规）
  validate_gzh_html.py    # 平台合规校验（ERROR 必须清零）
  wrap_preview.py         # 生成带「复制到公众号」按钮的预览页
  wx_api_publish.py       # API 可选通道：config-check/list/push/del（纯标准库）
  mp_full.py              # 扫码默认通道：登录 / 建草稿 / 覆盖草稿 / 正文注入
  mp_preflight.py         # 推送前环境检查：专用 profile 是否被占、锁是否陈旧（--fix 清理）
  mp_check.py             # 草稿回读核验（PASS/FAIL）
  mp_drafts.py            # 列出/删除草稿
  upload_md_images.py     # 扫描 Markdown 插图，上传微信图床并替换 src
  mp_imglib_upload.py     # 正文配图上传到微信图床
  mp_cover_set.py         # 单独设置/更换封面
  cover_prepare.py        # 封面归一化：本地路径/URL/AI 生成图 → 900×383
  push_config.py          # 用户配置项（author 署名等）：get/set/path，持久化到 ~/.config/gzh-md-compose-push/config.json
templates/
  article_template.py     # 文章模块模板（TITLE/DIGEST/AUTHOR/build_content）
assets/
  preview-template.html   # wrap_preview.py 依赖的预览外壳
references/
  user-conventions.md     # 用户排版特殊约定（超链接/角标/三层/列宽/来源/高亮）★ 必读
  browser-tool-contract.md # 扫码通道契约：把后台操作翻译成 Agent 浏览器工具调用（多数是 chrome-devtools-mcp）★ 扫码必读
  mp-wechat-notes.md      # 微信编辑器踩坑清单（粘贴/封面/图片/核验）
  ecosystem-survey.md     # 本次生态盘点与方案对比
doc/
  方案设计规格.md          # 设计规格（需求结论 / 参考技能取证 / 生态盘点 / 验证记录）
requirements.txt          # patchright（扫码脚本路径需要；扫码 + 含代码块时为必选，纯排版零依赖）
```

## 工作流

### 第 0 步：环境准备（按需，不预装）

依赖按需触发，不要预先手工安装：

- 纯排版 / 校验 / 预览的三个脚本只用标准库，**零依赖**。
- **先判断文章是否含代码块，再决定 patchright 是否必装**：
  - **含代码块（需代码高亮）→ patchright 必选**。工具路径的 `insertHTML` 虽能写入彩色 span，保存后微信后端会把它全部剥离，代码高亮必丢（2026-11-27 实测）。因此只要「扫码通道 + 含代码块」，无论 Agent 有没有浏览器工具，都必须走技能自带的 `mp_*.py` 脚本路径的原生剪贴板粘贴。
  - **无代码块时优先复用 Agent 的浏览器操作能力**，按 `references/browser-tool-contract.md` 的精确契约执行：多数 Agent 是安装了 [chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) 才具备该能力，也可能是宿主预装的其他等价工具、技能或插件；浏览器工具属于 Agent 侧能力，不绑定某个宿主。推送前先探测当前环境暴露的浏览器工具（MCP / skill / CLI 均可），**按能力适配**——能导航、能执行页面 JS、能发真实按键、能上传文件、有独立持久化 profile——再把契约里的 URL / 选择器 / JS / 判据翻译成该工具的具体调用。这条路不需要 patchright。
- Agent 没有任何满足契约的浏览器工具、或其接口做不到「写 text/html 剪贴板 + 发 Ctrl+V + 上传文件 + 独立持久化 profile」时（含代码块场景已在上一条强制），改用技能自带的 `mp_*.py` 脚本路径：它们依赖 `patchright`（几 MB 驱动库，缺失时脚本会提示 `python3 -m pip install patchright`），浏览器内核自动探测系统已装 Chrome/Edge/Chromium，普通用户无需预下载 Chromium。
- API 通道：`wx_api_publish.py` 纯标准库，只需凭证。

两种扫码执行器跑的是**同一份契约**（见 `references/browser-tool-contract.md`），差别只在调用方式：工具路径由 Agent 调 MCP / CLI 接口，脚本路径由 patchright 实现同一组单元。不要把「用 Agent 工具」当成自然语言自由发挥——每一步的 URL、选择器、JS、判据都是写死的。

**注意解释器一致性**：走 `mp_*.py` 脚本路径时，必须用装了 patchright 的那个 python；排版三脚本与 API 脚本用任意 python3 即可。

选择脚本路径时，后续所有脚本用 `python3 <SKILL>/scripts/<脚本>` 绝对路径调用。

### 第 1 步：排版方案（先确认，不落地）

1. 读取用户的 Markdown（路径或正文）。
2. **Obsidian 稿预处理**（仅当源文件来自 Obsidian / 含其专有语法时）：
   ```bash
   python3 <SKILL>/scripts/obsidian_preprocess.py <article.md> -o <article>_纯净.md
   ```
   处理 YAML frontmatter（title 单独写成 `<!-- gzh-title: ... -->` 标记行，正文的 `#`
   全部按章节渲染）、`> [!tip]` callout（原样保留给转换器按官方类型渲染，不在预处理里降级成加粗引用）、`[[笔记名]]` 内部引用按场景处理、`![[文件#块]]` 嵌入展开；
   超链接与图片行原样保留，由排版器统一收 reference。
   **内部引用双场景（2026-11-27 用户二次定稿）**：先收集 `![[文件#块]]` 成功展开的
   文件名集合——① **已引入**：`[[文件]]` 换成《文件》纯文本保留（读者在文中读得到，
   不算伪装资料），连「见 / 可参考」引导词与句子结构都不动；② **仅链接未引入**：
   擦除引用并修补上下文——引导词前是名词短语（「冲突具体案例，可参考 [[X]]」）
   就原位写「不在此展开」，是完整分句（「按…核算，见 [[X]]」）则连引导词一起删。
   代码块/行内代码里的方括号不动。切勿一律擦除：会留下「排查方法；」「冲突具体
   案例。」这类残句（用户实测反馈）。`![[文件#块]]` 是内容嵌入（展开后读者能直接
   读到），保留展开逻辑。
   不是 Obsidian 稿可跳过，直接用原文件做下一步。
3. **插图预处理**：若 Markdown 含 `![...](...)`，先上传图片并替换地址；本地路径、http/https 地址、data URI 都支持：
   ```bash
   python3 <SKILL>/scripts/upload_md_images.py <article>_纯净.md -o <article>_微信图.md
   ```
   （非 Obsidian 稿把输入换成 `<article.md>`。）这一步会调用 `mp_imglib_upload.py` 上传图片库并写出新 Markdown，后续排版一律用输出文件。没有插图时脚本原样写出。
4. **主题预览**：先跑一次生成全部主题的预览页，让用户直观挑选：
   ```bash
   python3 <SKILL>/scripts/md_to_gzh.py <article>_微信图.md --all-themes --preview-dir <工作区>/themes
   ```
   打开 `<工作区>/themes/index.html`，列出 6 套主题（摸鱼绿/红白色系/石墨极简风/留白禅意风/摸鱼票据风/橄榄手记），每套均有 浅色/深色 两种配色预览，请用户选一套（主题 + 配色）。用户偏好深色阅读时推荐 `--scheme dark`（写死的深底浅字卡片，读者任何模式下都稳定）。
5. 用 AskUserQuestion 给出：主题选项 + 章节结构概述 + **封面来源三选一**（这是封面唯一一次收集，之后不再追问）：
   - **① 自行提供封面**：用户可直接贴图、给本地文件路径或网络 URL——贴图/URL 先落成本地文件，再统一走 `cover_prepare.py` 归一化（中心裁剪 2.35:1 → 900×383）；
   - **② AI 自动生成封面**：按文章主题与所选配色生成提示词（无文字、构图主体居中、用主题强调色作点缀），调用图像生成能力产出后**必须**用 `cover_prepare.py` 归一化——生成图右下角的「AI生成」水印在底边，中心裁剪 2.35:1 后必然被去掉。**图像生成消耗额外额度（约 5–10 积分/张），询问前告知用户**；用户不满意可换构图重新生成。
   - **③ 不加封面**：草稿封面留空，后续可在公众号后台单独补。

   **同一轮提问里还要收集署名**：先跑 `push_config.py get author` 读已有配置——
   - 有值：把它作为默认展示，用户可直接确认或修改；
   - 无值：请用户输入（可跳过留空）。
   用户提交后**立即** `push_config.py set author "<署名>"` 持久化，并告知「下次推送自动使用，随时可改」；用户跳过则配置保持不变（回退默认 = 署名留空）。文章模块的 `AUTHOR` 由模板自动从配置读取，无需手填。

   选 ①② 时封面文件在确认推送前准备好，推送时直接使用；选 ③ 则推送时不带 `--cover`。
6. **停下等用户确认**。未确认前不生成最终文件。

### 第 2 步：生成本地文件（再确认）

用户确认方案后：

```bash
python3 <SKILL>/scripts/md_to_gzh.py <article>_微信图.md --theme <标识> -o <文章名>_排版_<主题>.html
python3 <SKILL>/scripts/validate_gzh_html.py <上面.html>          # 必须 0 ERROR / 0 WARNING
python3 <SKILL>/scripts/wrap_preview.py <上面.html>               # 产出 _预览.html
```

- 校验有 ERROR 就回转换器修，不得交付带 ERROR 的产物。
- **预览页只生成一个**：`wrap_preview.py` 默认产物已自带深浅自适应（跟随系统明暗 + 🌗 手动切换），**不要**再跑 `--dark` 生成第二个「_预览_深色.html」文件（2026-11-26 用户明确：单个文件已够，多文件冗余）。`--dark` 仅用于 `--scheme dark`（写死深底浅字）文章的强制深色快照，非常规交付物。
- 把 `_预览.html` 用 present_files 打开给用户看，并说明：代码块是**每行一个 leaf + 行内彩色 span**（这是修正过的关键点——早期逐 token 一个 leaf 会被公众号拆行、缩进错位）。
- **停下等用户确认满意**。不满意就回到第 1 步重来（换主题/改结构），不推送。

### 第 3 步：推送草稿箱（最后确认）

用户确认本地文件后，先按 `references/browser-tool-contract.md` 探测宿主浏览器工具，决定执行器：

- **有浏览器工具且文章无代码块**：按契约第一节的能力清单适配（任何接口等价的 MCP / skill / CLI 都行，不挑宿主，多数是 chrome-devtools-mcp），用该工具的接口执行登录、写标题、正文注入、上传图片、保存、设封面、回读核验；每一步的判据与「必读」踩坑清单一致。不装 patchright。
- **文章含代码块 → 无论有没有浏览器工具，都走 `mp_*.py` 脚本路径**（工具路径注入的代码高亮保存后会被微信剥离）；**无浏览器工具或接口不满足契约**（不能写 text/html 剪贴板、不能上传文件、无独立 profile）时同样走脚本路径。两种情况都用下面的 `mp_*.py` 命令，patchright 为必选依赖。

0. **推送前环境检查（两种情况都必做，不可跳过）**：
   ```bash
   python3 <SKILL>/scripts/mp_preflight.py --fix
   ```
   查出 `RESULT: PASS 可以推送` 才继续。它会检测专用 profile 是否被 chrome-devtools daemon / 残留浏览器进程占住、有没有陈旧 Singleton 锁，并只清理占用该 profile 的进程与锁（不碰用户日常 Chrome）。**2026-11-27 实测：工具路径的 daemon 曾常驻并锁住 profile，脚本路径直接报 ProcessSingleton 起不来**；这一步能提前发现并清掉，别等撞异常才处理。若 `--fix` 后仍 FAIL，停掉工具 daemon（`chrome-devtools stop`）再查。

1. **先问覆盖还是新建**（这是重复推送的必问项）：
   - 用 `mp_drafts.py list` 列出草稿箱现有草稿，让用户看标题。
   - AskUserQuestion：『覆盖同标题旧草稿』/『新建一篇草稿』。
   - 覆盖需拿到旧草稿的 `appmsgid`（列表里可查），推送时带 `--appmsgid N`。
2. **首次扫码**（登录态过期时脚本会自动再截二维码）：
   ```bash
   python3 <SKILL>/scripts/mp_full.py login
   ```
   脚本产出 `~/.config/gzh-md-compose-push/mp-login-qrcode-big.png`（放大版，配置目录，`GZH_MP_RUNTIME` 可改）——用 present_files 给用户扫。等 900 秒，登录成功自动返回并删除二维码文件。绝不落在技能目录。
3. **准备文章模块**：复制 `templates/article_template.py` 到工作区，填 `TITLE`（≤64 字）、`DIGEST`（≤120 字）；`AUTHOR` **不用手填**——模板自动读配置项 `author`（第 1 步收集并持久化），模块里显式改那一行可临时覆盖；`build_content()` 返回第 2 步的 HTML 文件内容：
   ```python
   TITLE = "文章标题"; DIGEST = "摘要"; AUTHOR = ""
   def build_content():
       return open("<文章名>_排版_<主题>.html", encoding="utf-8").read()
   ```
4. **推送**（正文图已在第 1 步上传并替换；封面已在第 1 步备好并归一化为 900×383，有封面加 `--cover`，选「不加」则草稿封面留空）：
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
- 正文**零超链接**：任何章节的链接都换成文字 + `[[N]]` 角标，全篇统一编号，
  URL 收进文末「附：取证来源」大章节 + References 纯文本 URL；
- 文章标题单独取（Obsidian frontmatter → `<!-- gzh-title: -->` 标记；旧稿取首个 `#`）；
  章节按正文实际标题级别判定：有 `#` 用 `#` 分章，否则用 `##` 分章；代码块里的 `#` 不算标题；
- `[[N]]` → `#2563EB` 蓝色 **右上角上标**（`vertical-align:super; font-size:10px`）；
- 三层对照用「图 + 强/平/弱状态表」（强=已覆盖/更优、平=有边界差异、弱=不可插件化）；
- 表格按内容比例列宽（`table-layout:fixed` + `width="%"` 属性 + `min-width:620px`），**不无脑加宽**，表头无底色、居中加粗，正文左对齐，窄屏可横滑；
- 行内代码蓝色 `#2563EB` 无底色；正文每段 1–3 处下划线标记；章节 44px 大编号 + 英文标签，
  小章节标题无竖线；引用块用浅灰背景块（浅 `#F5F5F5` / 深 `#383838`）+ 柔和左侧细线；
- 签名区不写死人名（用占位或用户给的署名），仅末尾一处。

## 关键实现依据（修复的坑）

- **Obsidian callout 特殊渲染（2026-11-27）**：照官方规格（`help.obsidian.md/callouts` + `docs.obsidian.md/Reference/CSS variables/Editor/Callout`）实现——13 内置类型各有独立色（左侧 3px 竖条 + 淡背景）与图标，别名（important→tip、summary/tldr→abstract、faq/help→question、error→danger、cite→quote 等）都识别，未知类型回退 note，大小写不敏感；`+/-` 折叠只作视觉标记（公众号不能真折叠，details/JS 会被剥）。预处理**不改写 callout 头**（旧版改成 `> **标题**` 导致类型全丢），由转换器 `callout_block()` 渲染；标题用 leaf 包裹否则校验器报 WARNING。
  **图标用单色线条 Unicode 符号**（`CALLOUT_ICONS`，如 warning=⚠、tip=♨，颜色取类型色），**不要用 Lucide SVG**——2026-11-27 真实推送回读实测：公众号粘贴阶段剥离 `<svg>`，绕过粘贴直接注入后保存又被服务端剥离，clip-path / data URI 背景图同样被删，只有纯文本节点存活（和代码高亮同类坑）。⚠ 必须用裸字符 U+26A0，加 FE0E 会变彩色 emoji。
- **代码高亮拆行 bug**：公众号把每个 `<span leaf>` 当原子节点重排。逐 token 一个 leaf 会让 `export const X = [` 被拆成 5 行、缩进错位、行距撑大。`md_to_gzh.py` 改为**每行一个 leaf，行内用不带 leaf 的彩色 span**，颜色保留且排版稳定。校验器已验证合规。**绝不改回图片方案**（用户明确否决）。
- **扫码登录**：patchright（Playwright stealth 分支）+ 独立 Chromium profile，二维码是 `.login__type__container__scan__qrcode`，放大 4 倍截图给用户扫；登录态存 `~/.config/gzh-md-compose-push/mp_profile/Default/Network/Cookies`，**绝不写进技能目录**，分享/同步技能前确认技能目录无此目录（含完整后台登录态）。
- **正文注入**：编辑器是 ProseMirror（`.mock-iframe-body .ProseMirror`，2026 版无 iframe）。脚本路径走 `clipboard.write(text/html)` + `Cmd+V`（mac）/ `Control+V` + 点「继续插入」。工具路径若 `press_key` 粘贴不触发（chrome-devtools CLI 实测会只剩占位符），可用 evaluate_script 的 `execCommand('selectAll'/'delete'/'insertHTML', html)` 写入正文——但 **2026-11-27 实测保存后微信会剥离代码块里的彩色 span**（注入 2434 个、重开剩 152 个），**含代码高亮的文章必须走脚本路径**（保存后 1862 个高亮 span 全保留），insertHTML 仅限无代码块文章兜底。始终禁止合成 paste 事件与直接改 innerHTML。
- **只存草稿**：`mp_full.py` 的 `click_text` 内置「发表/群发/发布」黑名单，杜绝误点。
- 其它踩坑见 `references/mp-wechat-notes.md`（封面悬停菜单、图片库真实点击、ProseMirror-separator、短文章判据等）。

## 安全

- 登录态目录 `~/.config/gzh-md-compose-push/mp_profile/` 是公众号后台完整 Cookies，**绝不外传**；`mp_full.py logout` 一键清除。二维码与调试截图也只落在该配置目录，不污染技能包。
- 二维码文件是活码，登录后脚本自动删除；不要手工留存。
- 校验器 `validate_gzh_html.py` 的 ERROR 必须清零；WARNING 也要检查到 0（半角标点在代码区内豁免）。

## 变更后的回归测试

只要改了转换器、预处理、契约、文档规则或依赖口径，交付前先跑
`python3 -m unittest discover -s tests -v`（技能根目录，38 项，默认离线）。
测试覆盖标题/章节、全篇 reference、代码高亮与横滑、表格、引用块、Obsidian
预处理、主题预览、预览页深浅切换、安全边界与文档一致性；全部通过才算改完。
真实草稿回读用 `GZH_LIVE=1 GZH_APPMSGID=<编号>` 开启，仅验证时可选。
**未经用户明确要求不做 git commit / git push。**
