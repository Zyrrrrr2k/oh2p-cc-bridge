#!/usr/bin/env python3
"""CC 说话：edge-tts 生成 + 音箱播放（复用 alarm.sh 的缓存目录）。
用法: speak.py "要说的话" [音色]
音色: xiaoxiao(默认) / xiaoyi / yunxi / yunjian / xiaobei / xiaoni
环境变量: CC_TARGET=speaker(默认)|mac  想播到 Mac 扬声器就设 mac
"""
import sys, os, subprocess, hashlib, time, urllib.request

VOICE_MAP = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    "xiaoyi":   "zh-CN-XiaoyiNeural",
    "yunxi":    "zh-CN-YunxiNeural",
    "yunjian":  "zh-CN-YunjianNeural",
    "yunyang":  "zh-CN-YunyangNeural",
    "xiaobei":  "zh-CN-liaoning-XiaobeiNeural",
    "xiaoni":   "zh-CN-shaanxi-XiaoniNeural",
}
DEFAULT_VOICE = os.environ.get("CC_VOICE", "xiaoxiao")

# 复用 alarm.sh 的缓存目录
CACHE_DIR = os.path.expanduser("~/.dsh/scripts/alarm-voices")
MAC_IP    = os.environ.get("MAC_IP", "192.168.31.217")
HTTP_PORT = os.environ.get("CC_HTTP_PORT", "8899")
WEBROOT   = "/tmp/cc_speak"
DEV_PY    = os.path.expanduser("~/dsh-voice/venv/bin/python")
DEVTEL    = os.path.expanduser("~/dsh-voice/devtel.py")
DNC      = os.path.expanduser("~/dsh-voice/dnc.py")
TARGET    = os.environ.get("CC_TARGET", "speaker")


def ensure_http():
    """确保 8899 在跑，且服务的根目录是 WEBROOT（不是别的目录）。
    之前踩过坑：旧的 http.server 占着端口但根目录是 /tmp，
    导致所有播报 URL 404，音箱一声不出。"""
    os.makedirs(WEBROOT, exist_ok=True)

    # 放一个探针文件，用它验证服务目录是否正确
    probe = os.path.join(WEBROOT, "__probe.mp3")
    if not os.path.exists(probe):
        with open(probe, "wb") as f:
            f.write(b"probe")

    def correct_server():
        try:
            r = urllib.request.urlopen(
                "http://127.0.0.1:%s/__probe.mp3" % HTTP_PORT, timeout=3)
            return r.status == 200
        except Exception:
            return False

    if correct_server():
        return

    # 端口被别的目录占着（或者没起）→ 杀掉重来
    try:
        out = subprocess.run(["lsof", "-ti:%s" % HTTP_PORT],
                             capture_output=True, text=True, timeout=5).stdout
        for pid in out.split():
            subprocess.run(["kill", "-9", pid], check=False)
        time.sleep(1.5)
    except Exception:
        pass

    subprocess.Popen(["python3", "-m", "http.server", HTTP_PORT,
                      "--directory", WEBROOT],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)

    if not correct_server():
        print("  ⚠ 警告：HTTP 服务目录可能不对，播报会失败")


def tts(text, voice_key, out_path):
    """生成 mp3，缓存优先（和 alarm.sh 共用缓存）"""
    voice = VOICE_MAP.get(voice_key, VOICE_MAP[DEFAULT_VOICE])
    h = hashlib.md5(text.encode()).hexdigest()
    cached = os.path.join(CACHE_DIR, "%s.mp3" % h)
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.exists(cached) and os.path.getsize(cached) > 500:
        # 缓存命中，直接复制
        subprocess.run(["cp", cached, out_path], check=False)
        return True, True
    env = dict(os.environ,
               https_proxy=os.environ.get("https_proxy", "http://127.0.0.1:7897"),
               http_proxy=os.environ.get("http_proxy", "http://127.0.0.1:7897"))
    r = subprocess.run([os.path.expanduser("~/dsh-voice/venv/bin/python"), "-m", "edge_tts",
                        "--voice", voice, "--text", text, "--write-media", out_path],
                       capture_output=True, text=True, timeout=60, env=env)
    if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
        subprocess.run(["cp", out_path, cached], check=False)
        return True, False
    return False, False


def play_speaker(filename):
    """播放。验证只查 URL 可达 + 文件非空（status 查询不稳定，不依赖它）。"""
    url = "http://%s:%s/%s" % (MAC_IP, HTTP_PORT, filename)

    # 1) 确认 URL 可达
    try:
        r = urllib.request.urlopen(url, timeout=4)
        size = int(r.headers.get("Content-Length", 0) or 0)
        if r.status != 200 or size <= 0:
            return False, "URL 不可达 (%s, %s bytes)" % (r.status, size)
    except Exception as e:
        return False, "URL 请求失败: %s" % type(e).__name__

    # 2) 提交播放
    cmd = "ubus call mediaplayer player_play_url '%s'" % ('{"url":"%s","type":1}' % url)
    out = subprocess.run([DEV_PY, DNC, cmd], capture_output=True, text=True, timeout=40).stdout
    if '"code": 0' not in out:
        return False, "player_play_url 未返回 code 0"

    return True, "已播放 (%d 字节)" % size


def play_mac(path):
    subprocess.run(["/usr/bin/afplay", path], check=False)


def main():
    if len(sys.argv) < 2:
        print("用法: speak.py \"要说的话\" [音色]")
        return 1
    text = sys.argv[1]
    voice = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_VOICE

    os.makedirs(WEBROOT, exist_ok=True)
    ensure_http()

    h = hashlib.md5(text.encode()).hexdigest()[:12]
    name = "s%s.mp3" % h
    path = os.path.join(WEBROOT, name)

    ok, cached = tts(text, voice, path)
    if not ok:
        print("✗ TTS 生成失败")
        return 1

    tag = "缓存" if cached else "新生成"
    print("  ✓ %s %d 字节，音色 %s" % (tag, os.path.getsize(path), VOICE_MAP.get(voice, voice)))

    if TARGET == "mac":
        play_mac(path)
        print("  ✓ 已从 Mac 扬声器播放")
    else:
        ok2, detail = play_speaker(name)
        if ok2:
            print("  ✓ 音箱播放中（已验证）")
        else:
            print("  ✗ 播报失败: %s" % detail)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
