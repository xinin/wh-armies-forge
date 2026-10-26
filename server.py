"""Local server for Army Forge: serves the app and stores each army list as a JSON file.

    python3 server.py [port] [--armies DIR]        → http://localhost:8000

--armies saves the lists in another folder (tools/check_app.py uses a temporary one).

API (JSON):
    GET    /api/lists        all saved lists (each with "file": its path, which is not stored in the file)
    PUT    /api/lists/<id>   create/replace a list   → armies/<name>-<id>.json
    DELETE /api/lists/<id>   delete a list
    PUT    /api/images/<faction>/<unit-id>   {"url": "https://..."} → data/factions/<faction>/images.json
                                             (an empty url removes the entry)
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARMIES = ROOT / 'armies'
ID_RE = re.compile(r'^[a-z0-9]{4,32}$')
SLUG_RE = re.compile(r'^[a-z0-9-]{2,64}$')


def slug(s):
    """File name part of a list name: 'Tiránidos 2000' → 'tiranidos-2000', 'Imperio T’au' → 'imperio-tau'."""
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().replace("'", '')
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:60] or 'army'


def files_for(list_id):
    return [p for p in ARMIES.glob('*.json') if p.stem == list_id or p.stem.endswith(f'-{list_id}')]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        # the browser revalidates every file (fresh data after an import), and unchanged ones come back as 304
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _list_id(self):
        m = re.match(r'^/api/lists/([^/?]+)$', self.path)
        return m.group(1) if m and ID_RE.match(m.group(1)) else None

    def do_GET(self):
        if self.path.split('?')[0] == '/api/lists':
            lists = []
            for p in sorted(ARMIES.glob('*.json')):
                try:
                    lists.append({**json.loads(p.read_text(encoding='utf-8')), 'file': f'armies/{p.name}'})
                except (OSError, ValueError):
                    print(f'warning: could not read {p.name}', file=sys.stderr)
            return self._json(200, lists)
        if self.path.startswith('/api/'):
            return self._json(404, {'error': 'not found'})
        return super().do_GET()

    def do_PUT(self):
        m = re.match(r'^/api/images/([^/]+)/([^/?]+)$', self.path)
        if m:
            return self._put_image(*m.groups())
        list_id = self._list_id()
        if not list_id:
            return self._json(400, {'error': 'bad id'})
        try:
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        except ValueError:
            return self._json(400, {'error': 'bad json'})
        if not isinstance(data, dict) or data.get('id') != list_id or not isinstance(data.get('units'), list):
            return self._json(400, {'error': 'bad list'})
        data.pop('file', None)  # derived from the name, see GET
        ARMIES.mkdir(exist_ok=True)
        target = ARMIES / f"{slug(str(data.get('name', '')))}-{list_id}.json"
        tmp = target.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tmp, target)
        for old in files_for(list_id):  # the list was renamed
            if old != target:
                old.unlink()
        return self._json(200, {'ok': True, 'file': f'armies/{target.name}'})

    def _put_image(self, faction, unit_id):
        path = ROOT / 'data' / 'factions' / faction / 'images.json'
        if not SLUG_RE.match(faction) or not SLUG_RE.match(unit_id) or not path.parent.is_dir():
            return self._json(400, {'error': 'bad faction or unit'})
        try:
            url = str(json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0)))).get('url', '')).strip()
        except (ValueError, AttributeError):
            return self._json(400, {'error': 'bad json'})
        if url and not re.match(r'^https?://\S+$', url):
            return self._json(400, {'error': 'bad url'})
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'units': {}}
        if url:
            data['units'][unit_id] = url
        else:
            data['units'].pop(unit_id, None)
        data['units'] = dict(sorted(data['units'].items()))
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        os.replace(tmp, path)
        return self._json(200, {'ok': True})

    def do_DELETE(self):
        list_id = self._list_id()
        if not list_id:
            return self._json(400, {'error': 'bad id'})
        for p in files_for(list_id):
            p.unlink()
        return self._json(200, {'ok': True})

    def log_message(self, fmt, *args):
        if self.command != 'GET' or self.path.startswith('/api/'):
            super().log_message(fmt, *args)


class Server(ThreadingHTTPServer):
    # the home loads the factions of the saved lists at once (~10 files each, in parallel): the default backlog
    # of 5 refuses connections
    request_queue_size = 128
    daemon_threads = True


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('port', nargs='?', type=int, default=8000)
    ap.add_argument('--armies', type=Path, default=ARMIES)
    args = ap.parse_args()
    port, ARMIES = args.port, args.armies.resolve()
    ARMIES.mkdir(exist_ok=True)
    print(f'→ http://localhost:{port}   (armies saved in {ARMIES})')
    Server(('127.0.0.1', port), Handler).serve_forever()
