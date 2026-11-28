"""Serve the compiled demo locally with the same isolation headers as Pages."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
ROOT=Path(__file__).resolve().parents[1]
class DemoHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Content-Security-Policy',"connect-src 'self'; object-src 'none'; base-uri 'self'")
        self.send_header('X-Robots-Tag','noindex, nofollow')
        self.send_header('Cache-Control','no-store')
        super().end_headers()
    def log_message(self,*args):pass
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8084);args=parser.parse_args()
    ThreadingHTTPServer(('127.0.0.1',args.port),partial(DemoHandler,directory=str(ROOT/'dist'))).serve_forever()
