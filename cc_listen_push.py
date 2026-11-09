#!/usr/bin/env python3
"""CC 的耳朵（推送版）—— 设备主动 POST 识别结果，本脚本只读本地队列。
延迟从 5-8 秒降到 ~3 秒（主要是 TTS 生成时间）。
"""
import sys, os, time, re, subprocess, json

QUEUE = "/tmp/cc_asr_queue.txt"
POSFILE = "/tmp/cc_asr_pos.txt"
SPEAK = os.path.expanduser("~/dsh-voice/speak.py")
DNC = os.path.expanduser("~/dsh-voice/dnc.py")
VENV = os.path.expanduser("~/dsh-voice/venv/bin/python")

WAKEWORDS = ["cc", "CC", "小雀"]
INTENT_WORDS = ["天气", "下雨", "气温", "几点", "时间", "声音", "音量",
                "别说了", "提醒", "晚安", "你好", "讲个", "笑话"]

CN_NUM = {"零":0,"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}


def cn2int(s):
    if not s: return None
    if s.isdigit(): return int(s)
    if s == "十": return 10
    if "十" in s:
        a, _, b = s.partition("十")
        tens = CN_NUM.get(a) if a else 1
        ones = CN_NUM.get(b) if b else 0
        if tens is None or ones is None: return None
        return tens * 10 + ones
    if len(s) == 1: return CN_NUM.get(s)
    return None


def parse_time_cn(q):
    m = re.search(r"([零一二两三四五六七八九十\d]{1,3})[点:：]([零一二两三四五六七八九十\d]{0,3})分?", q)
    if not m: return None, None
    hh = cn2int(m.group(1)); mm = cn2int(m.group(2)) if m.group(2) else 0
    if hh is None or mm is None or not (0 <= hh <= 23) or not (0 <= mm <= 59): return None, None
    if any(k in q for k in ["下午", "晚上", "傍晚"]) and hh < 12: hh += 12
    return hh, mm


def dev(cmd, wait=3.0):
    try:
        r = subprocess.run([VENV, DNC, cmd, str(wait)], capture_output=True, timeout=wait + 12)
        return r.stdout.decode("utf-8", errors="replace")
    except Exception:
        return ""


def interrupt_xiaoai():
    """掐断小爱正在说的话。小爱的 TTS 绕过了 notifyvol/softvol，
    只能靠停播放器 + 杀 qplayer/miplayer 来切断。"""
    dev("ubus call mediaplayer player_play_operation '{\"action\":\"stop\"}' 2>&1", 2.0)
    dev("ubus call qplayer stop 2>&1 || killall qplayer 2>/dev/null", 2.0)
    dev("killall miplayer 2>/dev/null", 2.0)


def speak(text):
    try:
        r = subprocess.run([VENV, SPEAK, text, "xiaoxiao"], capture_output=True, text=True, timeout=150)
        return r.returncode == 0
    except Exception:
        return False


def brain(q):
    q2 = q.strip()
    for w in WAKEWORDS:
        q2 = q2.replace(w, "").strip("，,。. 　")
    q2 = q2.replace("小爱同学", "").strip("，,。. 　")
    if not q2:
        return None   # 只说唤醒词，不回应（让小爱自己答）

    if any(k in q2 for k in ["天气", "下雨", "气温", "冷不冷", "热不热"]):
        r = subprocess.run([VENV, os.path.expanduser("~/dsh-voice/brief.py"), "weather"],
                           capture_output=True, text=True, timeout=60)
        m = re.search(r"播报内容:\s*(.+)", r.stdout)
        return m.group(1) if m else "天气查不到。"

    if any(k in q2 for k in ["几点", "时间"]):
        import datetime
        n = datetime.datetime.now()
        return "现在是%s%d点%d分。" % ("上午" if n.hour < 12 else ("下午" if n.hour < 18 else "晚上"),
                                      n.hour % 12 or 12, n.minute)

    if "声音" in q2 or "音量" in q2:
        if any(k in q2 for k in ["大", "响"]):
            dev("ubus call mediaplayer player_set_volume '{\"volume\":80}' 2>&1", 2.5)
            return "音量调到八十了。"
        if any(k in q2 for k in ["小", "轻"]):
            dev("ubus call mediaplayer player_set_volume '{\"volume\":30}' 2>&1", 2.5)
            return "音量调到三十了。"
        return "音量是八十。"

    if any(k in q2 for k in ["别说了", "停", "闭嘴", "安静"]):
        dev("ubus call mediaplayer player_play_operation '{\"action\":\"stop\"}' 2>&1", 2.5)
        return "好。"

    if "提醒" in q2:
        hh, mm = parse_time_cn(q2)
        if hh is not None:
            what = re.sub(r"提醒我?", "", q2)
            what = re.sub(r"[零一二两三四五六七八九十\d]+[点:：][零一二两三四五六七八九十\d]*分?", "", what)
            what = what.strip("，,。. 　？?") or "时间到了"
            subprocess.run([VENV, os.path.expanduser("~/dsh-voice/remind.py"),
                            "add", "%02d:%02d" % (hh, mm), what],
                           capture_output=True, text=True, timeout=30)
            return "%d点%d分提醒你%s。" % (hh, mm, what)
        return "提醒要说得具体点。"

    if any(k in q2 for k in ["晚安", "睡觉"]):
        return "晚安，早点睡。"
    if any(k in q2 for k in ["你好", "在吗", "听见"]):
        return "我在。"
    if any(k in q2 for k in ["笑话", "讲个"]):
        return "我不太会讲笑话，但可以提醒你别熬夜。"

    return None   # 不认识 → 不回应，让小爱自己答


def main():
    print("  ══════════════════════════════════════════")
    print("   CC（推送版）—— 读本地队列，零轮询延迟")
    print("  ══════════════════════════════════════════")

    # 记录上次读到的位置
    pos = 0
    if os.path.exists(POSFILE):
        try: pos = int(open(POSFILE).read().strip())
        except Exception: pos = 0
    # 首次启动：跳到末尾（忽略历史）
    if not os.path.exists(POSFILE):
        pos = os.path.getsize(QUEUE) if os.path.exists(QUEUE) else 0
        open(POSFILE, 'w').write(str(pos))
    print("  队列起点: %d 字节，等待语音…\n" % pos)

    seen = set()
    last_t = 0
    while True:
        time.sleep(0.3)          # 本地文件，0.3 秒足够
        if not os.path.exists(QUEUE):
            continue
        size = os.path.getsize(QUEUE)
        if size <= pos:
            if size < pos:       # 文件被截断
                pos = 0
            continue
        with open(QUEUE, 'r', errors='replace') as f:
            f.seek(pos)
            new = f.read()
            pos = f.tell()
        open(POSFILE, 'w').write(str(pos))

        for line in new.split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            text = parts[1].strip() if len(parts) > 1 else parts[0].strip()
            if not text or text in seen:
                continue
            # 3 秒内的重复丢弃
            now = time.time()
            if now - last_t < 2.0 and text in seen:
                continue
            seen.add(text)
            if len(seen) > 100:
                seen = set(list(seen)[-50:])

            has_wake = any(w in text for w in WAKEWORDS)
            has_intent = any(k in text for k in INTENT_WORDS)
            if not (has_wake or has_intent):
                print("  [跳过] %r" % text)
                continue

            print("\n  ┌─ 听到: %r" % text)
            interrupt_xiaoai()
            ans = brain(text)
            if ans is None:
                print("  └─ 无匹配回复，让小爱自己答")
                continue
            print("  ├─ 回答: %s" % ans)
            ok = speak(ans)
            print("  └─ 播报: %s" % ("✓" if ok else "✗"))
            last_t = time.time()


if __name__ == "__main__":
    main()
