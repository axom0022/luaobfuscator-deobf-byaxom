import html
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deobf import pipeline as deobfuscate
from deobf import clean

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>luaobfuscator deobfuscator</title>
<style>
body{background:#101418;color:#d8dee9;font-family:ui-monospace,Menlo,Consolas,monospace;margin:0;padding:24px}
h1{font-size:18px;font-weight:600;margin:0 0 16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
textarea{width:100%%;height:70vh;background:#161b22;color:#d8dee9;border:1px solid #2b3440;border-radius:8px;padding:12px;font:inherit;resize:vertical}
button{background:#2f81f7;color:#fff;border:0;border-radius:8px;padding:10px 18px;font:inherit;cursor:pointer;margin:12px 0}
button:hover{background:#4c94f8}
label{display:block;font-size:12px;color:#8b949e;margin-bottom:6px}
.modes{font-size:12px;color:#8b949e;margin:0 0 12px}.modes label{display:inline;margin-right:16px}
</style></head><body>
<h1>luaobfuscator &rarr; readable Lua</h1>
<form method="post">
<div class="grid">
<div><label>obfuscated input</label><textarea name="src" placeholder="paste obfuscated script">%s</textarea></div>
<div><label>deobfuscated output</label><textarea readonly>%s</textarea></div>
</div>
<div class="modes"><label><input type="radio" name="names" value="descriptive" %s> descriptive names</label><label><input type="radio" name="names" value="flat" %s> flat names</label></div>
<button type="submit">deobfuscate</button>
</form></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length).decode('utf-8', 'replace')
        fields = parse_qs(raw)
        src = (fields.get('src') or [''])[0]
        names = (fields.get('names') or ['descriptive'])[0]
        if names not in deobfuscate.names2:
            names = 'descriptive'
        out = ''
        if src.strip():
            try:
                result, _ = deobfuscate.withreport(src, names=names)
                out = clean.tidy(result) if result else 'unsupported input'
            except Exception as err:
                out = 'error: %s' % err
        self.reply(html.escape(src), html.escape(out), names)

    def do_GET(self):
        self.reply('', '', 'descriptive')

    def reply(self, src, out, names='descriptive'):
        body = (PAGE % (src, out,
                        'checked' if names == 'descriptive' else '',
                        'checked' if names == 'flat' else '')).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def launchweb(port=8000):
    server = HTTPServer(('0.0.0.0', port), Handler)
    print('serving on http://127.0.0.1:%d' % port)
    server.serve_forever()


if __name__ == '__main__':
    launchweb(int(os.environ.get('PORT', '8000')))
