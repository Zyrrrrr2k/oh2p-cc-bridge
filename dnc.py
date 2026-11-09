#!/usr/bin/env python3
"""设备命令执行（nc 直连，绕开 telnet 协商解析问题）。
用法: dnc.py "命令" [等待秒数]
"""
import sys, subprocess, re, time

HOST = "192.168.31.89"
PORT = "2323"


def run(cmd, wait=2.5):
    # 用 subshell 定时喂命令，再关闭 stdin
    script = '(echo %s; sleep %.1f) | nc %s %s' % (
        "'" + cmd.replace("'", "'\\''") + "'", wait, HOST, PORT)
    r = subprocess.run(["bash", "-c", script], capture_output=True,
                       timeout=wait + 20)
    out = r.stdout.decode("utf-8", errors="replace")

    # 去掉 telnet 协商字节
    out = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", out)

    # 找到命令回显之后的内容
    lines = out.split("\n")
    keep = []
    started = False
    for ln in lines:
        if not started:
            # 命令回显行（包含我们发的命令）
            if cmd.split()[0] in ln and "/ #" in ln:
                started = True
            elif "/ #" in ln and cmd[:20] in ln:
                started = True
            continue
        # 遇到下一个提示符就停
        if re.match(r"^/ #\s*$", ln) or ln.strip() == "/ #":
            break
        keep.append(ln)
    if not keep:
        # 兜底：取最后一个提示符之后的所有行
        idx = out.rfind("/ #")
        if idx >= 0:
            keep = out[idx + 3:].split("\n")
    return "\n".join(keep).strip()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: dnc.py \"命令\" [等待秒数]")
        sys.exit(1)
    w = float(sys.argv[2]) if len(sys.argv) > 2 else 2.5
    print(run(sys.argv[1], w))
