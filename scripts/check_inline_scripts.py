"""Parse executable inline scripts as the browser does, then check JS syntax.

This catches literal </script> terminators and accidental HTML injection inside
JavaScript strings. Inert JSON/JSX blocks are excluded; external scripts retain
their existing checks. No application code or network requests are executed.
"""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.blocks = []
    def handle_starttag(self, tag, attrs):
        if tag != 'script': return
        a = dict(attrs)
        self.kind = a.get('type', '').lower()
        self.active = not a.get('src') and self.kind in {'', 'text/javascript', 'application/javascript', 'module'}
        self.start = self.getpos()[0]
    def handle_data(self, data):
        if self.active: self.blocks.append((self.start, self.kind, data))
    def handle_endtag(self, tag):
        if tag == 'script': self.active = False

def main():
    files = subprocess.check_output(['git', 'ls-files', '*.html'], cwd=ROOT, text=True).splitlines()
    failures, total = [], 0
    with tempfile.TemporaryDirectory(prefix='broquer-js-') as directory:
        for name in files:
            if Path(name).name.startswith('_'): continue
            page = Scripts()
            page.feed((ROOT / name).read_text())
            for line, kind, source in page.blocks:
                total += 1
                script = Path(directory) / ('inline.mjs' if kind == 'module' else 'inline.js')
                script.write_text(source)
                result = subprocess.run(['node', '--check', str(script)], capture_output=True, text=True)
                if result.returncode: failures.append(f'{name}, script starting at line {line}:\n{result.stderr}')
    for failure in failures: print(failure)
    print(f'Checked {total} executable inline scripts; failures: {len(failures)}')
    return bool(failures)

if __name__ == '__main__': raise SystemExit(main())
