# -*- coding: utf-8 -*-
"""公众号草稿推送 —— 官方 API 通道（可选通道，非默认）。

仅当用户明确要求「用 API / 接口方式」并提供 AppID/AppSecret 时使用；
默认通道是 mp_full.py 的浏览器扫码方案（无需凭证）。

凭证从环境变量读取，不写入脚本、不落盘：
  export WX_APPID=wx...
  export WX_APPSECRET=...

用法：
  python wx_api_publish.py config-check          # 检查凭证与出口 IP 是否就绪
  python wx_api_publish.py list                  # 列出草稿
  python wx_api_publish.py push <排版.html> --title "标题" [--digest "摘要"] [--author ""] [--cover 图.png]
  python wx_api_publish.py del <media_id>        # 删除草稿
  python wx_api_publish.py clear-token           # 清除 token 缓存（换 IP/换凭证后）

设计要点：
  * 纯标准库实现（urllib），本通道零第三方依赖；
  * 只创建草稿，绝不调用 freepublish / masssend（发布权在用户）；
  * 错误码给人话提示：40164=到后台配 IP 白名单，48001=个人未认证号无接口权限。
"""
import json
import mimetypes
import os
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from pathlib import Path

API = "https://api.weixin.qq.com/cgi-bin"
BASE = Path(__file__).resolve().parent
CACHE = BASE / ".wx_api_cache"
TOKEN_FILE = CACHE / "token.json"
THUMB_FILE = CACHE / "thumb_media_id.txt"

# 常见失败的 actionable 提示，避免用户对着 errcode 干瞪眼
ERR_HINT = {
    40001: "AppSecret 不正确或已被重置，请到公众号后台「开发设置」核对。",
    40013: "AppID 不正确，请到公众号后台「开发设置」核对。",
    40164: ("当前请求的公网出口 IP 不在公众号后台白名单。请登录 mp.weixin.qq.com → "
            "「设置与开发 / 开发设置 / IP 白名单」，把本机出口 IP 加进去；"
            "可用 `curl ifconfig.me` 查询当前出口 IP。微信按 TCP 源 IP 校验，"
            "改请求头或客户端配置无法绕过。"),
    48001: ("接口未授权：个人未认证号通常没有草稿/素材接口权限。"
            "请改用默认的浏览器扫码通道（mp_full.py），或先完成微信认证。"),
    45009: "接口调用超过频率限制，稍后重试。",
}


class WXApiError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        hint = ERR_HINT.get(code, "")
        super().__init__("微信 API 错误 %s: %s%s" % (code, message, ("\n→ " + hint) if hint else ""))


def _credentials():
    appid = os.environ.get("WX_APPID", "").strip()
    secret = os.environ.get("WX_APPSECRET", "").strip()
    if not appid or not secret:
        raise SystemExit(
            "缺少凭证。API 为可选通道，默认请用浏览器扫码通道（mp_full.py）。\n"
            "如确需 API：\n"
            "  export WX_APPID=wx...\n"
            "  export WX_APPSECRET=...\n"
            "并在公众号后台「开发设置 / IP 白名单」加入本机公网出口 IP。"
        )
    return appid, secret


def _request(url, data=None, headers=None, timeout=30):
    """标准库 HTTP 请求；返回解析后的 JSON。"""
    if headers is None:
        headers = {}
    if data is not None and not isinstance(data, bytes):
        data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers.setdefault("Content-Type", "application/json; charset=utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        raise RuntimeError("微信接口返回的不是 JSON：%s" % raw[:200])
    if isinstance(obj, dict) and obj.get("errcode") not in (None, 0):
        raise WXApiError(obj["errcode"], obj.get("errmsg", ""))
    return obj


def _token(force=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    if not force and TOKEN_FILE.exists():
        try:
            cached = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            if cached.get("token") and cached.get("expires_at", 0) - 300 > time.time():
                return cached["token"]
        except Exception:
            pass
    appid, secret = _credentials()
    obj = _request(API + "/token?" + urllib.parse.urlencode({
        "grant_type": "client_credential", "appid": appid, "secret": secret,
    }), timeout=15)
    token = obj["access_token"]
    TOKEN_FILE.write_text(json.dumps({
        "token": token, "expires_at": time.time() + int(obj.get("expires_in", 7200)),
    }), encoding="utf-8")
    print("[token] 已刷新")
    return token


def _upload_media(token, path, media_type):
    """上传永久素材 / 图文内图片，返回 (media_id 或 url)。"""
    path = Path(path)
    if not path.exists():
        raise SystemExit("找不到图片: %s" % path)
    boundary = "wx" + uuid.uuid4().hex
    ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    body = b""
    body += ("--%s\r\nContent-Disposition: form-data; name=\"media\"; "
             "filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
             % (boundary, path.name, ctype)).encode("utf-8")
    body += path.read_bytes()
    body += ("\r\n--%s--\r\n" % boundary).encode("utf-8")
    endpoint = "material/add_material" if media_type == "thumb" else "media/uploadimg"
    url = "%s/%s?access_token=%s&type=thumb" % (API, endpoint, token) \
        if media_type == "thumb" else "%s/%s?access_token=%s" % (API, endpoint, token)
    obj = _request(url, data=body, headers={
        "Content-Type": "multipart/form-data; boundary=%s" % boundary,
    }, timeout=60)
    return obj.get("media_id") or obj.get("url")


def _solid_png(width=900, height=500, rgb=(24, 119, 212)):
    """无第三方依赖生成纯色 PNG，用作默认封面。"""
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    raw = b""
    row = b"\x00" + b"".join(struct.pack("BBB", *rgb) for _ in range(width))
    for _ in range(height):
        raw += row
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def _cover_media_id(token, cover=None):
    if THUMB_FILE.exists() and THUMB_FILE.read_text(encoding="utf-8").strip():
        return THUMB_FILE.read_text(encoding="utf-8").strip()
    if cover:
        mid = _upload_media(token, cover, "thumb")
    else:
        CACHE.mkdir(parents=True, exist_ok=True)
        auto = CACHE / "_auto_cover.png"
        auto.write_bytes(_solid_png())
        mid = _upload_media(token, auto, "thumb")
    THUMB_FILE.write_text(mid, encoding="utf-8")
    print("[封面] media_id=%s" % mid)
    return mid


def cmd_config_check():
    appid, _ = _credentials()
    print("凭证: 已提供 (AppID=%s...)" % appid[:6])
    print("IP 白名单: 需填本机公网出口 IP（微信按 TCP 源 IP 校验）")
    try:
        token = _token()
        print("接口连通: 正常（token 有效）")
        return 0
    except WXApiError as exc:
        print("接口连通: 失败 —— %s" % exc)
        return 1


def cmd_list():
    token = _token()
    obj = _request(API + "/draft/batchget?access_token=" + token,
                   {"offset": 0, "count": 20, "no_content": 1}, timeout=30)
    items = obj.get("item", [])
    if not items:
        print("草稿箱为空。")
    for it in items:
        title = it.get("content", {}).get("news_item", [{}])[0].get("title", "?")
        print("  %s  %s" % (it.get("media_id", "?"), title))
    return 0


def cmd_push(args):
    html_path = Path(args[0])
    if not html_path.exists():
        raise SystemExit("找不到 HTML: %s" % html_path)
    title = args.title or html_path.stem
    if len(title) > 64:
        raise SystemExit("标题超过 64 字符，请传 --title 缩短。")
    content = html_path.read_text(encoding="utf-8")
    token = _token()
    # 正文图片必须是 mmbiz URL：本地路径无效，图片请先用 mp_imglib_upload.py 上传并替换
    if "src=\"file:" in content or "src=\"data:" in content:
        raise SystemExit("正文含本地/内嵌图片，微信不认。请先把图上传到微信图床并替换为 mmbiz URL。")
    article = {
        "title": title,
        "author": args.author or "",
        "digest": args.digest or "",
        "content": content,
        "content_source_url": "",
        "thumb_media_id": _cover_media_id(token, args.cover),
        "show_cover_pic": 1,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    obj = _request(API + "/draft/add?access_token=" + token,
                   {"articles": [article]}, timeout=60)
    print("[草稿] 已创建 media_id=%s —— 请到公众号后台草稿箱手动发布" % obj.get("media_id"))
    return 0


def cmd_del(media_id):
    token = _token()
    _request(API + "/draft/delete?access_token=" + token,
             {"media_id": media_id}, timeout=15)
    print("[删除] 成功")
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    if cmd == "config-check":
        return cmd_config_check()
    if cmd == "list":
        return cmd_list()
    if cmd == "del":
        if not rest:
            raise SystemExit("用法: wx_api_publish.py del <media_id>")
        return cmd_del(rest[0])
    if cmd == "clear-token":
        for f in (TOKEN_FILE, THUMB_FILE):
            if f.exists():
                f.unlink()
        print("已清除 token / 封面缓存。")
        return 0
    if cmd == "push":
        if not rest:
            raise SystemExit("用法: wx_api_publish.py push <排版.html> --title '标题' [--digest '摘要']")
        # 轻量参数解析（不引第三方库）
        title = digest = author = cover = None
        paths = []
        i = 0
        while i < len(rest):
            v = rest[i]
            if v in ("--title", "--digest", "--author", "--cover") and i + 1 < len(rest):
                key = v[2:]
                val = rest[i + 1]
                if key == "title": title = val
                elif key == "digest": digest = val
                elif key == "author": author = val
                elif key == "cover": cover = val
                i += 2
            elif v.startswith("--"):
                raise SystemExit("未知参数: %s" % v)
            else:
                paths.append(v)
                i += 1
        if not paths:
            raise SystemExit("缺少 HTML 文件路径。")
        opts = type("Opts", (), {"title": title, "digest": digest,
                                 "author": author, "cover": cover})()
        return cmd_push([paths[0]], opts)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
    sys.exit(main() or 0)
