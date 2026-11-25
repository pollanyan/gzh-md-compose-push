# 浏览器通道：Agent 自带工具的复用契约

本文件回答一个问题：**扫码通道能不能不装 patchright，直接让 Agent 用它自己的浏览器工具做？** 能。Agent 的浏览器工具本身就是 skill / MCP 提供的接口，Agent 调接口操作浏览器；技能只需把公众号后台的精确操作写成一份与工具无关的契约，让 Agent 用当前宿主提供的接口去执行。

## 一、先探测当前 Agent 的浏览器工具

按宿主实际提供的能力选择，不要假设某一种工具一定存在。常见情况：

| 宿主 / 工具                          | 调用方式                                      | 适合本契约                          |
| ------------------------------------ | --------------------------------------------- | ----------------------------------- |
| chrome-devtools MCP（如 WorkBuddy）  | MCP 工具：`new_page` / `navigate_page` / `take_snapshot` / `evaluate_script` / `click` / `press_key` / `upload_file` / `take_screenshot` | ✅ 最合适：能执行 JS、能上传文件、有独立持久化 profile |
| chrome-devtools-cli skill            | shell 命令：`chrome-devtools evaluate_script ...`、`upload_file`、`press_key` 等 | ✅ 与 MCP 等价，适合脚本化执行      |
| computer-use 类工具                  | 截图 + 坐标点击 + 键盘                        | ⚠️ 可做，但慢且脆，**不要用坐标做正文注入** |
| 无任何浏览器工具                     | —                                             | ❌ 退回技能自带 `mp_*.py`（patchright） |

探测按**能力**判断，不按工具名字。先列出宿主暴露的工具 / 已装 skill / MCP server 配置，再逐项核对六项必需能力：

1. 打开任意 URL（导航）；
2. 在页面里执行 JS——写剪贴板、读 DOM 都靠它；
3. 发送真实按键（Ctrl+V、Ctrl+A 等）；
4. 上传本地文件（图片库 file input）；
5. 独立的持久化浏览器环境，登录态不混入用户日常浏览器；
6. 截图（放大二维码给用户扫）。

六项全满足 → 走工具路径，把第二节契约单元翻译成该工具的接口调用（见第四节）。缺 2 或 4 任一项 → 正文注入或图片上传做不了，**退回 `mp_*.py` 脚本路径**，不要硬凑。computer-use 类工具没有第 2 项，只能承担扫码、按钮点击和上传，正文注入必须另有 JS 执行能力。

上面表格只列常见宿主；任何接口等价的工具（Playwright MCP、browser-use 等）都按同样方式适配，不用改契约。

## 二、契约的操作单元（工具无关）

每一步只描述“要达成什么”，参数给出可直接用的 JS / 选择器。Agent 把这些单元翻译成当前工具的具体调用。

### 0. 独立登录态

用浏览器工具自带的**持久化 profile**，不要复用用户日常 Chrome 的登录态。chrome-devtools MCP 用它的默认持久 profile；脚本路径用 `scripts/mp_profile/`。两者互不影响。

### 1. 打开入口并取 token

入口必须是 `https://mp.weixin.qq.com/`。直接开无 `token` 参数的子页会被判「请重新登录」。从地址栏 URL 取 `token`，后续编辑页 URL：

```text
新建：https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token=<TOKEN>&lang=zh_CN&scene=21
覆盖：https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=77&appmsgid=<ID>&token=<TOKEN>&lang=zh_CN
```

### 2. 扫码登录

未登录时页面出现二维码元素 `.login__type__container__scan__qrcode`。截图后放大约 4 倍交给用户扫（原始约 122px 扫不出）；最长等 900 秒；登录后删掉临时二维码图片。二维码约 4 分钟刷新，过期重新截。

### 3. 填标题 / 署名 / 摘要

- 标题：`.title-editor__input .ProseMirror`，先点击取得焦点 → `Control+A` → `Delete` → 输入标题（≤64 字）→ 回读前 6 字校验。
- 署名：`input#author`；摘要：`textarea#js_description`（≤120 字）。

### 4. 写正文（关键，唯一可靠路径）

正文编辑器是 `.mock-iframe-body .ProseMirror`（2026 版**无 iframe**）。必须按顺序：

1. 真实点击编辑器取得焦点，再 `Control+A` → `Delete` 清空；
2. 执行 JS 写剪贴板（同时写 `text/html` 和 `text/plain`）：

   ```js
   async (a) => {
     const item = new ClipboardItem({
       'text/html': new Blob([a.html], {type: 'text/html'}),
       'text/plain': new Blob([a.plain], {type: 'text/plain'})
     });
     await navigator.clipboard.write([item]);
   }
   ```

3. 发 `Control+V`；
4. 轮询最多 8 秒，若出现「内容结构检测」弹窗（`.weui-desktop-dialog`），点「继续插入」——不点内容会被静默丢弃；
5. 读 `.mock-iframe-body` 的 `innerText.length`，按 HTML 预期非空白字符数的 0.7 倍作下限（下限最小 20）；不达标则清空重试一次。

**禁止**：合成 `ClipboardEvent('paste')`、`document.execCommand('insertHTML')`、直接改 `innerHTML`——公众号编辑器会丢弃。也**不要自己算坐标点击**：正文可高达数千像素，`scrollIntoView` 后坐标可能为负；用工具的 DOM 定位 / 选择器点击。

### 5. 正文配图

正文 `<img>` 的 src 必须是 `mmbiz.qpic.cn` URL。用 `mp_imglib_upload.py` 或工具的文件上传接口把图片进图片库后取 URL 拼进 HTML。数图时排除 ProseMirror 自动补的 `<img class="ProseMirror-separator">`，否则会多数一倍。

### 6. 保存草稿

精确匹配可见文字「保存为草稿」并点击（取最后一个可见匹配，避免点到同名隐藏按钮）。成功判据二者之一：短 Toast（≤12 字，含「保存成功 / 已保存 / 草稿已保存」）或 URL 出现 `appmsgid`。最多重试 2 次；都拿不到回执就报失败，不要当作成功。

**硬约束**：点击任何按钮前检查文字，命中「发表 / 群发 / 发布」一律拒绝。

### 7. 封面（可选）

- 不传封面 → 跳过，草稿封面为空，之后仍可在后台单独设置；
- 传封面 → **必须先存草稿拿到 `appmsgid`，再重开这篇草稿设封面**（保存前设会静默失败）。封面区 `#js_cover_area` 悬停才出现菜单，且页面有多个同名按钮，必须限定在可见弹窗内点。
- 图片库里 accept 含 `bmp` 的 file input 才是封面通道（含 jpg/png 的是正文插图通道，用错会把封面插进正文末尾）。图片条目是 `<i>` 的背景图，要用真实鼠标点击条目容器 `.weui-desktop-img-picker__item` 中心，`element.click()` 不触发选中。
- 刚上传的图要等条目标题等于文件名（最长 90 秒）再选，等不到就放弃，**绝不兜底选第一条**。
- 成功后读 `#js_cover_area .js_cover_preview_new` 的 `background-image` 相对基线是否变化来判定，不要数 `<img>`。

### 8. 回读核验

用 `appmsgid` 重开草稿，核对标题 / 署名 / 摘要有值、正文长度 > 20、真图数等于预期、封面非默认。全部满足输出 PASS，否则 FAIL 并按 `mp-wechat-notes.md` 排查。

## 三、为什么这不是「自然语言随便驱动」

「用 Agent 自带工具」不等于「说一句人话让 Agent 自由发挥」。上面每一步都是**确定的工具调用**：URL、选择器、JS、判据、禁止动作都写死了。Agent 的角色是把这些单元翻译成当前宿主的接口调用（chrome-devtools MCP 的 `evaluate_script` / `upload_file`，或 CLI 的同名命令，或 computer-use 的键盘 + 点击），而不是自己决定怎么操作公众号后台。这样同一份契约在不同 Agent 上执行结果一致。

脚本路径（`mp_*.py`）和工具路径执行的是**同一份契约**：脚本只是把上面的单元用 patchright 实现了一遍。所以「复用 Agent 自带工具」和「跑技能脚本」不是两套流程，是同一流程的两种执行器。

## 四、按探测结果动态生成调用

Agent 在运行时先探测宿主暴露的是 MCP 工具还是 shell 命令，再把第二节的单元翻译成对应调用；**不要写死某一种宿主的工具名**。以 chrome-devtools 为例：

```text
单元 1 打开入口        → MCP: new_page(url) / navigate_page(url)
                         CLI: chrome-devtools new_page "<url>"
单元 3 读标题          → MCP: evaluate_script("(s)=>document.querySelector(s)?.innerText", selector)
                         CLI: chrome-devtools evaluate_script "(s)=>..." --args <uid>
单元 4 写剪贴板 + 粘贴  → MCP: evaluate_script(写 ClipboardItem 的 JS, {html, plain})
                         → MCP: press_key("Control+V")；再 evaluate_script 轮询「继续插入」
                         CLI: chrome-devtools evaluate_script "<JS>" --pageId <id>
                              chrome-devtools press_key <id> "Control+V"
单元 7 设封面上传       → MCP: upload_file(uid, path) / 点击图片库条目
                         CLI: chrome-devtools upload_file <id> <uid> "<path>"
单元 8 核验             → MCP: evaluate_script(读标题/正文长度/真图数/封面背景)
```

computer-use 类工具只有截图 + 键盘 + 坐标点击：登录扫码、按钮点击、文件上传可用它，但**正文注入必须走 JS 写剪贴板**这条单元；若该工具不能执行 JS，就不满足契约条件，应改用 `mp_*.py`。

生成调用时保留契约给定的三个东西：URL / 选择器（或等价的 DOM 定位）、JS 片段、成功判据。自然语言只用来向用户收集选择（主题、封面路径、覆盖还是新建），不用来决定「怎么点公众号后台」。
