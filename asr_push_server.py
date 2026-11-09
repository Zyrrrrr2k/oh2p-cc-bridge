import http.server, socketserver, json, os, re, time

QUEUE = "/tmp/cc_asr_queue.txt"

class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(n).decode('utf-8', errors='replace')
        # 提取 text / origin_text
        m = re.search(r'"origin_text":"([^"]*)"', raw) or re.search(r'"text":"([^"]*)"', raw)
        ts = time.strftime('%H:%M:%S')
        with open(QUEUE, 'a') as f:
            if m:
                f.write("%s\t%s\n" % (ts, m.group(1)))
                print("ASR %s: %s" % (ts, m.group(1)), flush=True)
            else:
                f.write("%s\t%s\n" % (ts, raw[:200]))
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self, *a): pass

class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    S(("0.0.0.0", 8897), H).serve_forever()
