"""Collect unit pictures from the Warhammer webstore into data/factions/<faction>/images.json.

Usage:
    .venv/bin/python tools/store_images.py <faction> <store-category-url> [--overwrite] [--products FILE]

    e.g. .venv/bin/python tools/store_images.py astra-militarum \\
         https://www.warhammer.com/en-GB/shop/warhammer-40000/armies-of-the-imperium/astra-militarum

1. Opens a visible Chrome window (separate profile) on the store page.
2. If the store shows a "Human Verification" page, solve it in that window, then press Enter in the terminal.
3. Clicks "Show more" until every product is listed, and saves the list to <faction>-products.json.
4. Matches products to units by name and writes the confident matches to images.json
   (existing entries are kept unless --overwrite). Unmatched units/products are printed so you can
   add them by hand (in images.json or from the app: datasheet → "Imagen de la tienda").
Use the en-GB store URL: English product names match the datasheet names best.
Needs websocket-client (pip install websocket-client).
"""
import argparse
import itertools
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 9333
CHROME = next((p for p in ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                           shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chrome')) if p and Path(p).exists()), None)
NOISE = {'astra', 'militarum', 'warhammer', '40000', '40k', 'kill', 'team', 'combat', 'patrol', 'the', 'of', 'and', 'eng', 'spa',
         'lead', 'new', 'update', 'imperial', 'guard', 'de', 'la', 'del', 'el'}
SIZE = '?fm=webp&w=480&h=495'


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower().replace('’', '').replace("'", '')).strip('-')


def tokens(s):
    return {t for t in slug(re.sub(r'([a-z])([A-Z])', r'\1 \2', s)).split('-') if t and t not in NOISE and not re.fullmatch(r'(19|20)\d\d|\d+', t)}


def cdp_page(url_part):
    ids = itertools.count(1)
    import websocket
    tabs = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/list'))
    ws = websocket.create_connection(next(t['webSocketDebuggerUrl'] for t in tabs if t['type'] == 'page' and url_part in t['url']), timeout=120)

    def evaluate(expr):
        i = next(ids)
        ws.send(json.dumps({'id': i, 'method': 'Runtime.evaluate', 'params': {'expression': expr, 'returnByValue': True, 'awaitPromise': True}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get('id') == i:
                return msg['result']['result'].get('value')
    return evaluate


def collect(url):
    if not CHROME:
        sys.exit('Chrome not found')
    profile = tempfile.mkdtemp(prefix='army-forge-chrome-')
    proc = subprocess.Popen([CHROME, f'--user-data-dir={profile}', f'--remote-debugging-port={PORT}',
                             f'--remote-allow-origins=http://127.0.0.1:{PORT}', '--no-first-run', '--no-default-browser-check',
                             '--window-size=1300,950', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(4)
        input('If the store shows a verification page, solve it in the Chrome window. Press Enter when the products are visible... ')
        evaluate = cdp_page('warhammer.com')
        prev = -1
        for _ in range(60):
            n = evaluate("document.querySelectorAll('[data-test=product-card]').length")
            clicked = evaluate("""(() => { const b = [...document.querySelectorAll('button')]
              .find(b => /show more|load more|mostrar más|cargar más|mehr anzeigen|voir plus/i.test(b.innerText));
              if (!b) return false; b.scrollIntoView(); b.click(); return true; })()""")
            print(f'  {n} products', file=sys.stderr)
            if not clicked and n == prev:
                break
            prev = n
            time.sleep(2.5)
        return evaluate("""[...document.querySelectorAll('[data-test=product-card]')].map(c => {
          const a = c.querySelector('a#link'), img = c.querySelector('img');
          return { name: c.getAttribute('aria-label'), href: a && a.href,
                   img: img && new URL(img.getAttribute('src'), location.href).href.split('?')[0] };
        })""")
    finally:
        proc.terminate()
        shutil.rmtree(profile, ignore_errors=True)


def match(products, units):
    """unit id → product, when the product's tokens cover the unit's name tokens (best = fewest extra tokens)."""
    prod_tokens = [(p, tokens(p['name'] or '') | tokens(p['href'].split('/shop/')[-1]) | tokens(Path(p['img']).stem.split('_', 1)[-1]))
                   for p in products if p.get('img')]
    out = {}
    for u in units:
        want = tokens(u['name']['en'])
        if not want:
            continue
        best = None
        for p, have in prod_tokens:
            if want <= have:
                extra = len(have - want)
                if best is None or extra < best[0]:
                    best = (extra, p)
        if best:
            out[u['id']] = best[1]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('faction')
    ap.add_argument('url', nargs='?')
    ap.add_argument('--products', help='reuse a product list saved by a previous run')
    ap.add_argument('--overwrite', action='store_true')
    args = ap.parse_args()

    fdir = ROOT / 'data' / 'factions' / args.faction
    if args.products:
        products = json.loads(Path(args.products).read_text())
    else:
        if not args.url:
            ap.error('store URL required (or --products)')
        products = collect(args.url)
        saved = ROOT / f'{args.faction}-products.json'
        saved.write_text(json.dumps(products, ensure_ascii=False, indent=1))
        print(f'{len(products)} products saved to {saved.name}')

    units = json.loads((fdir / 'units.json').read_text())['units']
    images_path = fdir / 'images.json'
    images = json.loads(images_path.read_text()) if images_path.exists() else {'units': {}}
    found = match(products, units)
    added = 0
    for uid, p in found.items():
        if uid not in images['units'] or args.overwrite:
            images['units'][uid] = p['img'] + SIZE
            added += 1
            print(f'  {uid:34} ← {p["name"]}')
    images['units'] = dict(sorted(images['units'].items()))
    images_path.write_text(json.dumps(images, ensure_ascii=False, indent=1) + '\n')
    used = {id(p) for p in found.values()}
    print(f'\n{added} images written to {images_path.relative_to(ROOT)}')
    print('Units still without image:', ', '.join(u['id'] for u in units if u['id'] not in images['units']) or '—')
    print('Products not matched:', ', '.join(p['name'] for p in products if id(p) not in used) or '—')


if __name__ == '__main__':
    main()
