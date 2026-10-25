"""Translations of the game texts (imported in English) into Spanish.

    python3 tools/translations.py pending [--out DIR]     list untranslated texts, one numbered file per target:
                                                          DIR/_shared.tsv  → data/editions/11th.i18n.es.json (core
                                                                             stratagems + texts used by 2+ factions)
                                                          DIR/<faction>.tsv → data/factions/<faction>/i18n.es.json
    python3 tools/translations.py apply DIR/<name>.tsv DIR/<name>.es.txt
                                                          merge a translation file: one line per text,
                                                          "<number><TAB><translation>" (line breaks written as \\n)

Rule terms with a value ("Rapid Fire 2", "Feel No Pain 5+") are translated through the "terms" glossary of the
edition file, not listed here. Keywords in capitals (INFANTRY, OFFICER…) stay in English inside the texts.
After a re-import, new or changed texts appear in English until they are translated (run `pending` again).
"""
import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EDITION = ROOT / 'data' / 'editions' / '11th.i18n.es.json'
TERM_RE = re.compile(r'^(.+?)\s+((?:\d|D\d|\d\+)[^\s]*)$')


def esc(s):
    return s.replace('\\', '\\\\').replace('\n', '\\n')  # one text per line in the .tsv / .txt files


def unesc(s):
    return re.sub(r'\\(.)', lambda m: '\n' if m.group(1) == 'n' else m.group(1), s)


def target_path(name):
    return EDITION if name == '_shared' else ROOT / 'data' / 'factions' / name / 'i18n.es.json'


def collect():
    """{target: OrderedDict(text → category)} for every game text shown by the app."""
    texts = {}

    def need(o):
        return isinstance(o, dict) and o.get('en') and (not o.get('es') or o['es'] == o['en'])

    def add(f, cat, s):
        if isinstance(s, dict):
            if not need(s):
                return
            s = s['en']
        if s and s.strip():
            texts.setdefault(f, collections.OrderedDict()).setdefault(s.strip(), cat)

    for fdir in sorted((ROOT / 'data' / 'factions').iterdir()):
        if not fdir.is_dir():
            continue
        f = fdir.name
        for u in json.loads((fdir / 'units.json').read_text())['units']:
            add(f, 'unit-name', u['name'])
            for a in u.get('abilities', []) + u.get('wargearAbilities', []):
                add(f, 'ability-name', a['name'])
                add(f, 'ability-text', a['text'])
            if u.get('damaged'):
                add(f, 'damaged', u['damaged']['name'])
                add(f, 'damaged', u['damaged']['text'])
            for k in ('ordersText', 'transport'):
                if u.get(k):
                    add(f, k, u[k])
            for w in u['weapons']:
                add(f, 'weapon-name', w['name'])
                for p in w['profiles']:
                    if p.get('mode'):
                        add(f, 'weapon-mode', p['mode'])
            for c in u.get('factionAbilities', []):
                add(f, 'faction-ability', c)
            for o in u.get('wargearOptions', []):
                add(f, 'wargear-option', o['text'])
                for c in o['choices']:
                    add(f, 'wargear-choice', c)
            for n in u.get('wargearNotes', []):
                add(f, 'wargear-note', n)
            for o in u.get('wargear', []):
                if o.get('owner'):
                    add(f, 'model-type', o['owner'])
            for c in u.get('composition', []) + u.get('equipped', []):
                add(f, 'composition', c)
            if u.get('attachRule'):
                add(f, 'attach-rule', u['attachRule'])
        fa = json.loads((fdir / 'faction.json').read_text())
        full = json.loads((fdir / 'rules.json').read_text())['detachments'] if (fdir / 'rules.json').exists() else {}
        add(f, 'army-rule', fa['armyRule']['name'])
        add(f, 'army-rule', fa['armyRule']['text'])
        for d in fa['detachments']:
            fd = full.get(d['id'], {})
            add(f, 'detachment', d['name'])
            add(f, 'detachment-rule', d['rule']['name'])
            # the app shows the full rules.json texts; faction.json summaries only when there is none
            add(f, 'detachment-rule', fd.get('rule', {}).get('text') or d['rule']['text'])
            for e in d['enhancements']:
                add(f, 'enhancement-name', e['name'])
                add(f, 'enhancement-text', fd.get('enhancements', {}).get(e['id'], {}).get('text') or e['text'])
        if (fdir / 'stratagems.json').exists():
            for lst in json.loads((fdir / 'stratagems.json').read_text())['detachments'].values():
                for s in lst:
                    add(f, 'stratagem-name', s['name'])
                    add(f, 'detachment', s['source'])
                    for k in ('legend', 'when', 'target', 'effect', 'restrictions'):
                        if s.get(k):
                            add(f, 'stratagem-' + k, s[k])
    for s in json.loads((ROOT / 'data' / 'editions' / '11th-stratagems.json').read_text())['stratagems']:
        add('_shared', 'stratagem-name', s['name'])
        for k in ('legend', 'when', 'target', 'effect', 'restrictions'):
            if s.get(k):
                add('_shared', 'stratagem-' + k, s[k])

    # texts used by 2+ factions go to the edition file
    count = collections.Counter(t for f, d in texts.items() if f != '_shared' for t in d)
    shared = texts.setdefault('_shared', collections.OrderedDict())
    for f, d in list(texts.items()):
        if f == '_shared':
            continue
        for t, c in list(d.items()):
            if count[t] > 1:
                shared.setdefault(t, c)
                del d[t]
    return texts


def load(path):
    return json.loads(path.read_text()) if path.exists() else {'texts': {}}


def known():
    out = dict(load(EDITION).get('texts', {}))
    for p in (ROOT / 'data' / 'factions').glob('*/i18n.es.json'):
        out.update(load(p).get('texts', {}))
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    pp = sub.add_parser('pending')
    pp.add_argument('--out', default=str(ROOT / '.cache' / 'translations'))
    pa = sub.add_parser('apply')
    pa.add_argument('pending_tsv')
    pa.add_argument('translated_txt')
    args = ap.parse_args()

    if args.cmd == 'pending':
        done = known()
        os.makedirs(args.out, exist_ok=True)
        for target, d in collect().items():
            rows = [(t, c) for t, c in d.items() if t not in done]
            path = Path(args.out) / f'{target}.tsv'
            path.write_text(''.join(f'{i}\t{c}\t{esc(t)}\n' for i, (t, c) in enumerate(rows, 1)))
            print(f'{target:20} {len(rows):5} pending  {sum(len(t) for t, _ in rows):7} chars  → {path}')
        return

    rows = {}
    for line in Path(args.pending_tsv).read_text().splitlines():
        n, cat, text = line.split('\t', 2)
        rows[n] = unesc(text)
    trans = {}
    for line in Path(args.translated_txt).read_text().splitlines():
        if not line.strip():
            continue
        n, _, es = line.partition('\t')
        if n.strip() not in rows:
            sys.exit(f'unknown number {n!r}')
        trans[rows[n.strip()]] = unesc(es.strip())
    missing = [n for n, t in rows.items() if t not in trans]
    dest = target_path(Path(args.pending_tsv).stem)
    data = load(dest)
    data.setdefault('_note', 'Spanish translations of the English game texts (tools/translations.py). Unofficial.')
    data.setdefault('texts', {}).update(trans)
    data['texts'] = dict(sorted(data['texts'].items()))
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n')
    print(f'{len(trans)} translations merged into {dest.relative_to(ROOT)}; {len(missing)} still missing: {missing[:20]}')


if __name__ == '__main__':
    main()
