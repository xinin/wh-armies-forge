"""Import full detachment rules, enhancement texts and stratagems from Wahapedia (11th edition).

Usage:
    python3 tools/import_wahapedia_rules.py astra-militarum [--faction-html FILE] [--core-html FILE]

Without --*-html the pages are downloaded from wahapedia.ru. Writes:
    data/factions/<faction>/rules.json       full detachment rule + enhancement texts (keyed by our ids)
    data/factions/<faction>/stratagems.json  stratagems per detachment id
    data/editions/11th-stratagems.json       core stratagems
Hand-written faction.json is not modified; the app merges these files at load time.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wahapedia_fetch import fetch  # noqa: E402
from page_scope import scope_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BASE = 'https://wahapedia.ru/wh40k11ed'

PHASES = {'str11Any': 'any', 'str11Command': 'command', 'str11Movement': 'movement', 'str11Shooting': 'shooting',
          'str11Charge': 'charge', 'str11Fight': 'fight'}
TURNS = {'str11Either': 'either', 'str11Your': 'your', 'str11Enemy': 'enemy'}


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower().replace('’', '').replace("'", '')).strip('-')



def section_at(sec, pos):
    """One part of a detachment section (rule, enhancements or stratagems): from its heading (`pos`, inside the <h2>)
    to the next heading. Pages do not always list them in the same order (Chaos Daemons: stratagems first)."""
    if pos is None:
        return ''
    nxt = sec.find('<h2', pos)
    return sec[pos:nxt if nxt >= 0 else len(sec)]


def rule_lines(rule_html):
    """Detachment rule lines without the "Detachment Rule" heading and the "If your Army Faction is X, you can use
    this … Detachment rule." preamble: the first line is the rule's name."""
    lines = clean(strip_fluff(rule_html)).split('\n')[1:]
    return lines[1:] if lines and re.match(r'^If your Army Faction is .*Detachment rule\.?$', lines[0]) else lines


def enhancements_pos(sec):
    """Position of the enhancements heading's id in a detachment section: "Enhancements", or the detachment's own
    name for them (Pantheon of Woe: "Necrodermal Binding Abilities"). None if there is none."""
    m = re.search(r'id="Enhancements(-\d+)?"', sec)
    if m:
        return m.start()
    for h in re.finditer(r'<h2[^>]*?(id="[^"]+")', sec):
        nxt = sec.find('<h2', h.end())
        if 'EnhancementsPts' in sec[h.end():nxt if nxt > 0 else len(sec)]:
            return h.start(1)
    return None

# Cyrillic letters that look like Latin ones; Wahapedia sometimes mixes them in ("Kauyоn" with a Cyrillic о)
LATIN = str.maketrans('АВЕКМНОРСТХаеорсухі', 'ABEKMHOPCTXaeopcyxi')


def latin(s):
    return s.translate(LATIN)


def key(s):
    """Loose comparison key: Wahapedia anchors turn "Emperor’s Chosen" into "Emperor-s-Chosen"."""
    return re.sub(r'[^a-z0-9]', '', latin(s).lower())


def clean(x):
    x = re.sub(r'<script.*?</script>', '', x, flags=re.S)  # ad snippets inside rule sections
    # dice icons next to a rule picked by a D6 roll (Chaos Knights Dread abilities): "DESPAIR (AURA) (D6: 1)";
    # "N/A" marks the one that is always active
    x = re.sub(r'<div class="cruD(\d)"></div>', r'\1', x)
    x = re.sub(r'<div class="cruD6wrap2?">\s*(\d+|N/A)\s*</div>',
               lambda m: '' if m.group(1) == 'N/A' else f' (D6: {"-".join(sorted({m.group(1)[0], m.group(1)[-1]}))})', x)
    x = re.sub(r'<br\s*/?>', '\n', x)
    x = re.sub(r'</(p|div|h\d|li|tr)>', '\n', x)
    x = re.sub(r'</t[dh]>', ' ', x)
    x = re.sub(r'<[^>]+>', '', x)
    x = latin(html.unescape(x)).replace('‑', '-')
    x = re.sub(r'[ \t]+', ' ', x)
    return re.sub(r'\s*\n\s*', '\n', x).strip()


def strip_errata(x):
    return re.split(r'\n(?:Errata|FAQ)\n', x)[0].strip()


def strip_fluff(x):
    return re.sub(r'<(p|div) class="ShowFluff[^"]*"[^>]*>.*?</\1>', '', x, flags=re.S)


def parse_stratagems(block_html):
    out = []
    for block in re.split(r'<div class="str11Wrap">', block_html)[1:]:
        name = re.search(r'class="str11HeadBlock str11Name"[^>]*>(.*?)</div>', block, re.S)
        cp = re.search(r'class="str11CP">(.*?)</div>', block, re.S)
        typ = re.search(r'class="str11Type[^"]*">(.*?)</div>', block, re.S)
        legend = re.search(r'class="str11Legend[^"]*">(.*?)</div>', block, re.S)
        text = re.search(r'class="str11Text">(.*?)</div>\s*</div>', block, re.S)
        if not (name and text and cp and clean(cp.group(1))):
            continue  # core-rule actions use the same markup but have no CP cost
        t = clean(text.group(1).replace('<br>', '\n'))
        fields = {}
        for key in ('WHEN', 'TARGET', 'EFFECT', 'RESTRICTIONS'):
            m = re.search(rf'{key}:\s*(.*?)(?=\n(?:WHEN|TARGET|EFFECT|RESTRICTIONS):|\Z)', t, re.S)
            if m:
                fields[key.lower()] = {'en': re.sub(r'\s*\n\s*', ' ', m.group(1)).strip()}
        src, _, kind = clean(typ.group(1)).partition(' – ') if typ else ('', '', '')
        icons = re.findall(r'class="str11Icon (str11\w+)"', block)
        nm = re.sub(r'\d+\.\d+$', '', clean(name.group(1))).strip()
        out.append({
            'id': slug(nm),
            'name': {'en': nm.title() if nm.isupper() else nm},
            'cp': int(re.sub(r'\D', '', clean(cp.group(1))) or 0),
            'source': re.sub(r' Stratagem$', '', src.strip()),
            'kind': kind.replace(' Stratagem', '').strip() or None,
            'phase': next((PHASES[i] for i in icons if i in PHASES), None),
            'turn': next((TURNS[i] for i in icons if i in TURNS), None),
            **({'legend': {'en': clean(legend.group(1))}} if legend and clean(legend.group(1)) else {}),
            **fields,
        })
    return out


def dedupe(items):
    seen, out = set(), []
    for x in items:
        if x['id'] not in seen:
            seen.add(x['id'])
            out.append(x)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('faction')
    ap.add_argument('--faction-html')
    ap.add_argument('--core-html')
    args = ap.parse_args()

    fdir = ROOT / 'data' / 'factions' / args.faction
    faction = json.loads((fdir / 'faction.json').read_text())
    source = scope_of(args.faction).page  # a Chapter lives in another faction page
    page = Path(args.faction_html).read_text() if args.faction_html else fetch(f'{BASE}/factions/{source}/')
    core = Path(args.core_html).read_text() if args.core_html else fetch(f'{BASE}/the-rules/core-rules/')

    by_name = {key(d['name']['en']): d for d in faction['detachments']}
    on_page = set(by_name) | {key(n) for n in re.findall(r'data-det-name="([^"]+)"', page)}
    heads = [(m.start(), m.group(1)) for m in re.finditer(r'<h2[^>]*id="([^"]+)"', page)]
    rules, strats = {'detachments': {}}, {}
    for i, (pos, hid) in enumerate(heads):
        det = by_name.get(key(hid))
        if not det:
            continue
        # the section ends at the next detachment of the page (also those of other Chapters, not in faction.json)
        end = next((p for p, h in heads[i + 1:] if key(h) in on_page or h in ('Crusade-Rules', 'Boarding-Actions')), len(page))
        sec = page[pos:end]
        e_pos = enhancements_pos(sec)
        s_pos = re.search(r'id="Stratagems(-\d+)?"', sec)
        r_pos = re.search(r'id="Detachment-Rules?(-\d+)?"', sec)
        lines = rule_lines(section_at(sec, r_pos.start() if r_pos else None))
        rule = {'name': {'en': lines[0]} if lines else det['rule']['name'], 'text': {'en': strip_errata('\n'.join(lines[1:]))}}

        enh = {}
        ens_html = section_at(sec, e_pos)
        for m in re.finditer(r'<ul class="EnhancementsPts"><li><span>(.*?)</span>\s*<span>(\d+ pts)</span></li></ul>(.*?)(?=<ul class="EnhancementsPts"|\Z)', ens_html, re.S):
            ename = re.sub(r'\(Aura\)|UPGRADE', '', clean(re.sub(r'<span class="EnhUpgrade">.*?</span>', '', m.group(1)))).strip()
            # also the abilities a detachment gives to named datasheets (unitAbilities), listed the same way
            ours = next((e for e in det['enhancements'] + det.get('unitAbilities', []) if key(e['name']['en']) == key(ename)), None)
            if ours:
                body = strip_errata(clean(strip_fluff(m.group(3))))
                enh[ours['id']] = {'text': {'en': body}, 'points': int(re.sub(r'\D', '', m.group(2)) or 0)}
        rules['detachments'][det['id']] = {'rule': rule, 'enhancements': enh}
        strats[det['id']] = dedupe(parse_stratagems(section_at(sec, s_pos.start() if s_pos else None)))
        print(f"{det['id']:24} rule={len(rule['text']['en']):4} chars  enhancements={len(enh)}  stratagems={len(strats[det['id']])}")

    core_strats = dedupe([s for s in parse_stratagems(core) if s['source'].startswith('Core')])
    print(f'core stratagems: {len(core_strats)}')

    (fdir / 'rules.json').write_text(json.dumps({'source': f'{BASE}/factions/{source}/', **rules}, ensure_ascii=False, indent=1) + '\n')
    (fdir / 'stratagems.json').write_text(json.dumps({'source': f'{BASE}/factions/{source}/', 'detachments': strats}, ensure_ascii=False, indent=1) + '\n')
    (ROOT / 'data' / 'editions' / '11th-stratagems.json').write_text(
        json.dumps({'source': f'{BASE}/the-rules/core-rules/', 'stratagems': core_strats}, ensure_ascii=False, indent=1) + '\n')


if __name__ == '__main__':
    sys.exit(main())
