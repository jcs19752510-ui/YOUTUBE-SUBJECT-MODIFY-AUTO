from http.server import *
class H(BaseHTTPRequestHandler):
    def do_GET(s): s.send_response(200); s.send_header("Content-Type","application/json"); s.end_headers(); s.wfile.write(b'{"status":"ok"}')
    def log_message(*a): pass
HTTPServer(('127.0.0.1',8080),H).serve_forever()
