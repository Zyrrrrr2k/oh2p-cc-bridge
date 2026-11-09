#!/usr/bin/env python3
"""CC 定时提醒：到点让音箱说话 + 可选微信推送。
用法:
  remind.py add "23:30" "该睡觉了"      # 每天 23:30
  remind.py add "7:30" "起床" --once     # 只一次
  remind.py list
  remind.py del <id>
  remind.py run                          # 前台跑（cron 或 launchd 调）
"""
import sys, os, json, time, datetime, subprocess, hashlib

STORE = os.path.expanduser("~/.dsh-voice/reminders.json")
VENV = os.path.expanduser("~/dsh-voice/venv/bin/python")
SPEAK = os.path.expanduser("~/dsh-voice/speak.py")


def load():
    if os.path.exists(STORE):
        try:
            return json.load(open(STORE))
        except Exception:
            pass
    return {"items": []}


def save(d):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    json.dump(d, open(STORE, "w"), ensure_ascii=False, indent=2)


def add(hhmm, text, once=False):
    d = load()
    rid = hashlib.md5(("%s|%s" % (hhmm, text)).encode()).hexdigest()[:8]
    if any(x["id"] == rid for x in d["items"]):
        print("  已存在:", rid)
        return rid
    d["items"].append({
        "id": rid, "time": hhmm, "text": text, "once": once,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "last_fired": None, "enabled": True,
    })
    save(d)
    print("  ✓ 已添加 %s 每天 %s: %s" % (rid, hhmm, text) if not once
          else "  ✓ 已添加 %s %s: %s（仅一次）" % (rid, hhmm, text))
    return rid


def fire(text):
    subprocess.run([VENV, SPEAK, text, "xiaoxiao"], capture_output=True, timeout=180)


def run_loop():
    print("  remind 守护启动，检查间隔 20 秒")
    last_min = None
    while True:
        now = datetime.datetime.now()
        hm = now.strftime("%H:%M")
        # 每分钟只检查一次
        if hm != last_min:
            last_min = hm
            d = load()
            changed = False
            for it in d["items"]:
                if not it.get("enabled"):
                    continue
                if it["time"] != hm:
                    continue
                if it.get("last_fired") == now.strftime("%Y-%m-%d %H:%M"):
                    continue
                print("  → 触发 %s: %s" % (it["id"], it["text"]), flush=True)
                fire(it["text"])
                it["last_fired"] = now.strftime("%Y-%m-%d %H:%M")
                if it.get("once"):
                    it["enabled"] = False
                changed = True
            if changed:
                save(d)
        time.sleep(20)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "add":
        if len(sys.argv) < 4:
            print("用法: remind.py add \"23:30\" \"该睡觉了\" [--once]")
            return 1
        once = "--once" in sys.argv
        add(sys.argv[2], sys.argv[3], once)
    elif cmd == "list":
        d = load()
        if not d["items"]:
            print("  （无提醒）")
        for it in d["items"]:
            st = "启用" if it.get("enabled") else "已停"
            once = " [一次性]" if it.get("once") else ""
            print("  %s  %s  %s%s  %s" % (it["id"], it["time"], it["text"], once, st))
    elif cmd == "del":
        if len(sys.argv) < 3:
            print("用法: remind.py del <id>")
            return 1
        d = load()
        n = len(d["items"])
        d["items"] = [x for x in d["items"] if x["id"] != sys.argv[2]]
        save(d)
        print("  ✓ 删除 %d 条" % (n - len(d["items"])))
    elif cmd == "run":
        run_loop()
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
