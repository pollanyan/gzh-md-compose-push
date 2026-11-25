# 公众号排版 / 推送生态盘点（2026-11-24 取证）

本技能是下列方案对比后的产物。记录结论供后续判断「是否要改用别的通道」。

## 本机已装组件

| 组件 | 类型 | 认证方式 | 排版能力 | 限制 | 满足本次需求 |
|---|---|---|---|---|---|
| 本技能 gzh-md-compose-push | Skill | **个人微信扫码**（独立 profile） | 6 主题 + 代码高亮 + 预览 | 首次需扫码；需 patchright+chromium | ✅ 全部 |
| gzh-layout-pro 公众号排版设计专家 | Expert | 无（只排版） | 6 主题组件库、校验器、主题预览生成、章节编号 | 不推送；需人工复制粘贴 | 仅排版 |
| wechat-draft-publisher | Skill | AppID/AppSecret + IP 白名单 | 无（只推送现成 HTML） | 个人未认证号报 48001；作者名默认写死 | 仅推送 |
| wxmp-draft-publisher 公众号发布·斑马 | Connector | OAuth 一次填 AppID/Secret（云端固定 IP） | 无 | 仍依赖 AppID；IP 白名单 | 否 |
| gzh-content-ops 公众号发布管家 | Connector | 环境变量 GZH_APPID/SECRET + 本机出口 IP 白名单 | draft_from_markdown 一步到草稿 | 仍依赖 AppID；IP 白名单 | 否 |
| yanxu 言序 | Connector | 平台账号绑定公众号 | list_theme_styles + create_article → publish_article | 需先绑定；块类型仅 4 种，不支持 HTML 代码高亮；发布前停下确认 | 部分 |

## 市场参考技能（无本地源码，从技能包取证）

### Wechat Publisher（skill_2054902455876030464, v0.1.0）
- **实现**：封装 `wenyan-cli`（`@wenyan-md/cli`），`wenyan publish -f article.md -t lapis -h solarized-light`。
- **代码高亮**：CLI 的 `-h` 参数走 highlightjs 主题（solarized-light/github/dracula 等），Mac 风格代码块；**不是自己实现的高亮**。
- **主题**：wenyan-core 内置 default/lapis/phycat + 自定义 CSS 主题。
- **限制**：仍需 `WECHAT_APP_ID/SECRET` + IP 白名单；frontmatter 强制 title+cover；个人未认证号不可用。
- **可复用思路**：主题 + 代码高亮主题**分离**的参数设计；封面必填的实测经验。

### 公众号草稿箱推送（skill_2115386847996645376, v1.3.2, 森智道）
- **实现**：patchright + 独立 Chromium profile 扫码登录，DOM 操作公众号后台，剪贴板粘贴 HTML 到 ProseMirror。
- **认证**：个人微信扫码一次，cookie 存本机 profile，长期复用；**无 AppID/Secret**。
- **能力**：正文 HTML 注入、图片上传、封面设置、`--appmsgid` 覆盖草稿、回读核验；只存草稿不发表。
- **可复用思路**：①扫码登录 + 本机登录态持久化；②剪贴板 text/html + Control+V 是 HTML 注入 ProseMirror 的唯一可靠路径；③覆盖草稿避免垃圾堆积；④发布权留给用户的安全边界。
- **已直接复用**：本技能的 `scripts/mp_*.py` 即源自该技能（源码已下载取证）。

## 结论

现成方案没有同时满足「扫码认证 + Markdown 多主题排版 + 代码高亮 + 三段式确认 + 覆盖草稿」的：
- 两个市场技能各满足一半（一个强在排版高亮但要 AppID，一个强在扫码推送但排版弱）；
- 三个连接器全部依赖 AppID/Secret；
- Expert 只排版不推送。

本技能把两者合并：复用排版专家的主题体系与校验器 + 复用扫码技能的浏览器推送底座 + 新增修正过 leaf 粒度的 Markdown 转换器，并加入三段式确认与覆盖/新建选择。
