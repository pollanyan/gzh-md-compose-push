# -*- coding: utf-8 -*-
"""推送前环境检查：专用 profile 有没有被别的浏览器进程占住。

为什么单独做：2026-11-27 踩过一次——chrome-devtools CLI 的常驻 daemon
用同一个 mp_profile 连过公众号后台且没退，脚本路径 launch_persistent_context
直接报 ProcessSingleton / SingletonLock，推送根本起不来。所以推送前必须先查，
查到占用就停掉占用者、清掉锁，再推送，别等撞上异常才处理。

用法：
  python mp_preflight.py              # 只检查：干净退出 0，占用退出 1
  python mp_preflight.py --fix        # 检查并清理占用者 + 陈旧 Singleton 锁，再复查

安全边界：
  - 只处理命令行里带 --user-data-dir=<本技能 mp_profile> 的进程；
    绝不碰用户日常 Chrome（它的 profile 是别的路径）。
  - daemon 用 SIGTERM，给它正常退出的机会；不 kill -9。
  - 只删本技能 profile 下的 3 个 Singleton 锁文件，不碰其它任何文件。
  - 本脚本不导航、不登录、不写草稿，只做环境检查与占用清理。
"""
import os
import re
import signal
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import mp_full as M  # noqa: E402  复用 PROFILE / RUNTIME 定义，避免两处漂移

PROFILE = M.PROFILE
LOCKS = [os.path.join(PROFILE, "SingletonLock"),
         os.path.join(PROFILE, "SingletonCookie"),
         os.path.join(PROFILE, "SingletonSocket")]


def _ps_rows():
    """返回 (pid, cmdline)。优先 ps；沙箱里 ps 可能被禁，退回 pgrep -f。"""
    rows = []
    try:
        out = subprocess.run(["ps", "-ax", "-o", "pid=,command="],
                             capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            for line in out.stdout.splitlines():
                m = re.match(r"\s*(\d+)\s+(.*)$", line)
                if m:
                    rows.append((int(m.group(1)), m.group(2)))
            return rows
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        out = subprocess.run(["pgrep", "-fl", PROFILE],
                             capture_output=True, text=True, timeout=15)
        for line in out.stdout.splitlines():
            m = re.match(r"\s*(\d+)\s+(.*)$", line)
            if m:
                rows.append((int(m.group(1)), m.group(2)))
    except (OSError, subprocess.SubprocessError):
        pass
    return rows


def occupants():
    """找出命令行里明确带本技能 profile 的进程，按 daemon / 浏览器分类。"""
    found = []
    for pid, cmd in _ps_rows():
        if PROFILE not in cmd:
            continue
        if "mp_preflight.py" in cmd:      # 别把自己算进去
            continue
        if "daemon.js" in cmd and "chrome-devtools" in cmd:
            kind = "chrome-devtools daemon"
        elif "Google Chrome" in cmd or "Chromium" in cmd or "chrome" in cmd.lower():
            kind = "浏览器进程"
        else:
            kind = "其它进程"
        found.append({"pid": pid, "kind": kind, "cmd": cmd[:160]})
    return found


def stale_locks():
    return [p for p in LOCKS if os.path.lexists(p)]


def report():
    occ = occupants()
    locks = stale_locks()
    print("专用 profile: %s" % PROFILE)
    if occ:
        print("!! 检测到 %d 个占用进程:" % len(occ))
        for o in occ:
            print("   - PID %s [%s] %s" % (o["pid"], o["kind"], o["cmd"]))
    else:
        print("✓ 无占用进程")
    if locks:
        print("!! 检测到 %d 个 Singleton 锁文件: %s"
              % (len(locks), ", ".join(os.path.basename(p) for p in locks)))
    else:
        print("✓ 无 Singleton 锁文件")
    return occ, locks


def fix(occ, locks):
    for o in occ:
        try:
            os.kill(o["pid"], signal.SIGTERM)
            print("   已发 SIGTERM -> PID %s [%s]" % (o["pid"], o["kind"]))
        except ProcessLookupError:
            print("   PID %s 已退出" % o["pid"])
        except OSError as e:
            print("   !! 无法结束 PID %s: %s（请手动处理）" % (o["pid"], e))
    # 给进程一点退出时间，锁可能随之自动释放
    import time
    time.sleep(2)
    remain = [o for o in occ if _alive(o["pid"])]
    if remain:
        print("!! 仍有 %d 个进程存活，请手动结束后重跑：kill -TERM <PID>"
              % len(remain))
        for o in remain:
            print("   - PID %s [%s]" % (o["pid"], o["kind"]))
        return False
    for p in locks:
        try:
            os.unlink(p)
            print("   已删除陈旧锁: %s" % os.path.basename(p))
        except FileNotFoundError:
            pass
        except OSError as e:
            print("   !! 无法删除 %s: %s" % (p, e))
            return False
    return True


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False


def main():
    do_fix = "--fix" in sys.argv[1:]
    occ, locks = report()
    if do_fix and (occ or locks):
        print("--- 清理 ---")
        if not fix(occ, locks):
            print("RESULT: FAIL 清理未完成，不要推送")
            return 2
        print("--- 复查 ---")
        occ2, locks2 = report()
        if occ2 or locks2:
            print("RESULT: FAIL 复查仍有占用，不要推送")
            return 2
    clean = not occ and not locks
    print("RESULT: %s" % ("PASS 可以推送" if clean else
                          "FAIL 有占用，先跑 `python mp_preflight.py --fix`（或停掉工具 daemon）"))
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
