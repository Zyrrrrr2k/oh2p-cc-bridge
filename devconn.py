#!/usr/bin/env python3
"""持久 telnet 连接执行器 —— 避免每次重连的 1.5 秒开销。
用法:
    from devconn import DevConn
    c = DevConn()
    out = c.run("echo hi")      # ~0.15s
    c.close()
"""
import subprocess, re, time, os, sys

HOST = os.environ.get("OH2P_HOST", "192.168.31.89")
PORT = "2323"


class DevConn:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.proc = None
        self.buf = b""

    def _start(self):
        self.proc = subprocess.Popen(
            ["nc", self.host, self.port],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0)
        time.sleep(1.2)          # 等 banner
        self._drain()

    def _drain(self):
        """把当前缓冲区读空"""
        try:
            os.set_blocking(self.proc.stdout.fileno(), False)
            while True:
                chunk = self.proc.stdout.read(65536)
                if not chunk:
                    break
                self.buf += chunk
        except (BlockingIOError, TypeError, AttributeError):
            pass

    def run(self, cmd, timeout=3.0):
        if self.proc is None or self.proc.poll() is not None:
            self._start()

        marker = "MK%d" % int(time.time() * 1000)
        payload = ("%s; echo %s\n" % (cmd, marker)).encode()
        try:
            self.proc.stdin.write(payload)
            self.proc.stdin.flush()
        except Exception:
            self._start()
            self.proc.stdin.write(payload)
            self.proc.stdin.flush()

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.05)
            self._drain()
            if marker.encode() in self.buf:
                break

        text = self.buf.decode("utf-8", errors="replace")
        self.buf = b""

        # 去掉 telnet 控制字符
        text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)

        # 截取 marker 之前、命令回显之后的部分
        idx = text.rfind(marker)
        if idx >= 0:
            text = text[:idx]

        # 去掉第一行（命令回显）
        lines = text.split("\n")
        if lines and cmd.split()[0] in lines[0]:
            lines = lines[1:]
        # 去掉末尾的空提示符
        while lines and lines[-1].strip() in ("", "/ #", "/ # "):
            lines.pop()
        return "\n".join(lines).strip()

    def close(self):
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None


if __name__ == "__main__":
    c = DevConn()
    t0 = time.time()
    for i in range(5):
        r = c.run("wc -c < /tmp/mico_aivs_lab/instruction.log")
        print("  [%d] %.2fs -> %r" % (i + 1, time.time() - t0, r))
    c.close()
