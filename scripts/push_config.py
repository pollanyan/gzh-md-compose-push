#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公众号推送技能的用户配置项管理（署名等）。

配置项：
  author   署名（公众号文章作者栏）。默认值：空字符串（= 署名留空，
           草稿作者栏为空，之后可在后台补）。

存储位置（按优先级）：
  1. 环境变量 GZH_PUSH_CONFIG 指定的文件
  2. ~/.config/gzh-md-compose-push/config.json（默认）

读取方：templates/article_template.py 的 AUTHOR 自动从此文件读取；
mp_check.py 核验署名时以此为预期值。写入方：本脚本 `set` 子命令。

用法：
  python push_config.py path                  # 打印配置文件路径
  python push_config.py get [key]             # 打印全部配置或某一项
  python push_config.py set author <署名>     # 持久化署名（空串=回退默认留空）
"""
import json
import os
import sys

DEFAULTS = {"author": ""}

# 配置项说明（文档口径的唯一出处）
KEY_DOC = {
    "author": "署名（公众号文章作者栏）；默认空字符串 = 留空",
}


def config_path():
    p = os.environ.get("GZH_PUSH_CONFIG",
                       os.path.expanduser("~/.config/gzh-md-compose-push/config.json"))
    return os.path.abspath(p)


def load():
    """读配置，缺的键回退默认值；文件不存在/损坏时返回默认值。"""
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = json.load(f)
        for k in DEFAULTS:
            if data.get(k) is not None:
                cfg[k] = str(data[k])
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg):
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return path


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd = args[0]
    if cmd == "path":
        print(config_path())
    elif cmd == "get":
        cfg = load()
        if len(args) > 1:
            if args[1] not in DEFAULTS:
                sys.exit("✗ 未知配置项 %s（可用：%s）" % (args[1], ", ".join(DEFAULTS)))
            print(cfg[args[1]])
        else:
            print(json.dumps(cfg, ensure_ascii=False, indent=2))
    elif cmd == "set":
        if len(args) < 2 or args[1] not in DEFAULTS or len(args) < 3:
            sys.exit("用法: push_config.py set <key> <value>（key 可用：%s）" % ", ".join(DEFAULTS))
        cfg = load()
        cfg[args[1]] = args[2].strip()
        path = save(cfg)
        print("✓ 已保存 %s=%r → %s" % (args[1], cfg[args[1]], path))
    else:
        sys.exit("未知子命令 %s（可用：path / get / set）" % cmd)


if __name__ == "__main__":
    main()
