"""Download Wahapedia pages with a local cache (.cache/wahapedia/…), so audits and re-imports don't hit the site again.

Set REFRESH = True (the importers' --refresh flag) to ignore the cache, e.g. after an errata.
"""
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / '.cache' / 'wahapedia'
REFRESH = False


def fetch(url):
    rel = re.sub(r'^https?://[^/]+/', '', url).strip('/') or 'index'
    path = CACHE / f'{rel}.html'
    if path.exists() and not REFRESH:
        return path.read_text(encoding='utf-8')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (army-forge importer)'})
    for attempt in range(4):  # the site sometimes stops answering for a while: wait and try again
        try:
            html = urllib.request.urlopen(req, timeout=60).read().decode('utf-8')
            break
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 3 or getattr(e, 'code', None) == 404:
                raise
            time.sleep(15 * (attempt + 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding='utf-8')
    time.sleep(0.5)  # be gentle with Wahapedia
    return html
