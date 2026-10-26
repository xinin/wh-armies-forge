"""Check the app in a real browser, for every faction and language, without touching your saved lists.

Usage:
    python3 tools/check_app.py                      every faction, ES and EN
    python3 tools/check_app.py necrons tyranids     only those factions
    python3 tools/check_app.py --lang es --keep     one language; keep the temporary folder (lists, page dumps)

It writes one test list per faction to a temporary folder (every datasheet, every detachment, Onslaught; each
wargear option set to its first choice; every Leader/Support character attached to the first unit it can join),
starts server.py with that folder (--armies) and opens tools/check_app.html in headless Chrome. The page goes
through the home, the faction picker, and for each list the builder, every datasheet and every overview tab.
Fails (exit code 1) on:
  - JavaScript errors or console messages (read from Chrome's log)
  - a view that does not render, or lists, units, datasheets or factions missing from it
  - "undefined", "NaN" or "[object Object]" in the rendered text
  - text in the other language: English sentences in the ES views, Spanish ones in the EN views
    (UPPERCASE keywords, which stay in English, are ignored)
Needs Google Chrome (or Chromium). No Python dependencies.
"""
import argparse
import html
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROME = next((p for p in ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                           shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chrome')) if p and Path(p).exists()), None)

BAD_VALUES = re.compile(r'\bundefined\b|\bNaN\b|\[object Object\]')
# a line in the wrong language has at least two of these words (after removing UPPERCASE keywords)
OTHER_LANGUAGE = {
    'es': re.compile(r'\b(the|each|this|that|your|with|within|model|models|unit|units|attack|until|equipped|can be|replaced|roll)\b'),
    'en': re.compile(r'\b(el|los|las|unidad|unidades|modelo|modelos|tirada|hasta|cada|equipado|puede|sustituir|tu|del)\b'),
}
KEYWORDS = re.compile(r"\b[A-Z][A-Z’'\-]+(?:\s+[A-Z][A-Z’'\-]+)*\b")


def test_list(n, faction):
    """Every datasheet and detachment of the faction, with wargear choices and attached characters."""
    fdir = ROOT / 'data' / 'factions' / faction
    units = json.loads((fdir / 'units.json').read_text())['units']
    detachments = [d['id'] for d in json.loads((fdir / 'faction.json').read_text())['detachments']]
    roster = []
    for i, u in enumerate(units):
        wargear = {}
        for o in u.get('wargear', []):
            if o['type'] == 'swap' and len(o['choices']) > 1:
                wargear[o['id']] = o['choices'][1]
            elif o['type'] == 'pool' and o['choices']:
                wargear[o['id']] = {o['choices'][0]: 1}
            elif o['type'] == 'toggle':
                wargear[o['id']] = 1
        roster.append({'uid': f'u{i}', 'unitId': u['id'], 'sizeIdx': 0, 'enhancement': None, 'warlord': False,
                       'attachedTo': None, 'wargear': wargear})
    by_id = {u['id']: u for u in units}
    bodyguards = {r['unitId']: r for r in roster if not by_id[r['unitId']].get('leader')}
    taken = set()  # (bodyguard uid, leader kind)
    for r in roster:
        leader = by_id[r['unitId']].get('leader')
        if not leader:
            continue
        kind = 'support' if leader.get('support') else 'leader'
        target = next((bodyguards[t] for t in leader.get('canLead', []) if t in bodyguards and (bodyguards[t]['uid'], kind) not in taken), None)
        if target:
            r['attachedTo'] = target['uid']
            taken.add((target['uid'], kind))
    if roster:
        roster[0]['warlord'] = True
    return {'id': f'chk{n:04d}', 'name': f'CHK {faction}', 'factionId': faction, 'edition': '11th', 'battleSize': 'onslaught',
            'detachments': detachments, 'units': roster, 'created': 0, 'updated': 0}


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def run_browser(port, lang, ids, tmp):
    url = f'http://127.0.0.1:{port}/tools/check_app.html#lang={lang}&lists={",".join(ids)}'
    proc = subprocess.run([CHROME, '--headless=new', '--disable-gpu', f'--user-data-dir={tmp / f"chrome-{lang}"}',
                           '--enable-logging=stderr', '--v=0', '--window-size=1440,1000',
                           '--virtual-time-budget=3600000', '--dump-dom', url],
                          capture_output=True, text=True, timeout=1800)
    errors = list(dict.fromkeys(re.sub(r'^\[[^\]]*\] ', '', line) for line in proc.stderr.splitlines()
                                if ':CONSOLE' in line and f'127.0.0.1:{port}' in line))
    m = re.search(r'<pre id="out">(.*?)</pre>', proc.stdout, re.S)
    return (json.loads(html.unescape(m.group(1))) if m else {'error': 'the check page did not finish'}), errors


def text_problems(text, lang):
    bad, other = [], []
    for line in text.splitlines():
        line = line.strip()
        if BAD_VALUES.search(line):
            bad.append(line)
        if len(OTHER_LANGUAGE[lang].findall(KEYWORDS.sub('', line))) >= 2:
            other.append(line)
    return list(dict.fromkeys(bad)), list(dict.fromkeys(other))


def main():
    ap = argparse.ArgumentParser(description='Check every view of the app in headless Chrome.')
    ap.add_argument('factions', nargs='*')
    ap.add_argument('--lang', default='es,en', help='languages to check, comma separated (default: es,en)')
    ap.add_argument('--keep', action='store_true', help='keep the temporary folder with the lists and page dumps')
    args = ap.parse_args()
    if not CHROME:
        sys.exit('Google Chrome or Chromium not found')
    index = json.loads((ROOT / 'data' / 'factions' / 'index.json').read_text())['factions']
    factions = args.factions or [f['id'] for f in index]
    unknown = set(factions) - {f['id'] for f in index}
    if unknown:
        sys.exit(f'unknown faction: {", ".join(sorted(unknown))}')

    tmp = Path(tempfile.mkdtemp(prefix='check-app-'))
    armies = tmp / 'armies'
    armies.mkdir()
    lists = {}
    for n, faction in enumerate(factions):
        lst = test_list(n, faction)
        lists[lst['id']] = lst
        (armies / f'{lst["id"]}.json').write_text(json.dumps(lst))

    port = free_port()
    server = subprocess.Popen([sys.executable, str(ROOT / 'server.py'), str(port), '--armies', str(armies)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    failures = 0

    def fail(msg, lines=()):
        nonlocal failures
        failures += 1
        print(f'  FAIL {msg}')
        for line in list(lines)[:8]:
            print(f'       {line[:160]}')
        if len(lines) > 8:
            print(f'       … {len(lines) - 8} more')

    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{port}/api/lists', timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        for lang in args.lang.split(','):
            started = time.time()
            out, console = run_browser(port, lang, list(lists), tmp)
            (tmp / f'dump-{lang}.json').write_text(json.dumps(out, ensure_ascii=False))
            print(f'== {lang.upper()} ({time.time() - started:.0f}s)')
            if console:
                fail('JavaScript errors', console)
            if out.get('error'):
                fail(f'the check stopped: {out["error"]}')
            home = out.get('home', {})
            if home:
                print(f'  home: {home["cards"]} lists, {home["requests"]} data files, {home["kb"]} KB')
            if home and home['cards'] != len(lists):
                fail(f'the home shows {home["cards"]} lists of {len(lists)}')
            if 'homeAgain' in out and out['homeAgain'] != len(lists):
                fail(f'back on the home, {out["homeAgain"]} lists of {len(lists)}')
            picker = out.get('picker')
            if picker and (picker['tiles'], picker['emblems']) != (len(index), len(index)):
                fail(f'faction picker: {picker["tiles"]} factions and {picker["emblems"]} emblems of {len(index)}')
            texts = {'home': home.get('text', ''), 'faction picker': (picker or {}).get('text', '')}
            for lid, res in out.get('lists', {}).items():
                lst = lists[lid]
                name = lst['factionId']
                if 'rosterUnits' in res and res['rosterUnits'] != len(lst['units']):
                    fail(f'{name}: the builder shows {res["rosterUnits"]} units of {len(lst["units"])}')
                if 'datasheets' in res and res['datasheets'] != len({u['unitId'] for u in lst['units']}):
                    fail(f'{name}: {res["datasheets"]} datasheets opened of {len({u["unitId"] for u in lst["units"]})}')
                for part in ('builder', 'modals', 'overview'):
                    texts[f'{name} {part}'] = res.get(part, '')
            for where, text in texts.items():
                bad, other = text_problems(text, lang)
                if bad:
                    fail(f'{where}: undefined/NaN in the text', bad)
                if other:
                    fail(f'{where}: text in the other language', other)
            print(f'  {sum("overview" in r for r in out.get("lists", {}).values())}/{len(lists)} factions checked')
    finally:
        server.terminate()
        server.wait()
        if args.keep:
            print(f'kept {tmp}')
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f'\n{failures} failures')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
