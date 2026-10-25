"""Trace vector artwork from a PDF page into an SVG (used for the official icons in js/icons.js).

Usage:
    python tools/pdf_vector_icon.py <file.pdf> <page> <out.svg> --list            # list small drawings with their bbox
    python tools/pdf_vector_icon.py <file.pdf> <page> <out.svg> --ids 172,173,174 [--mono]
    python tools/pdf_vector_icon.py <file.pdf> <page> <out.svg> --bbox x0,y0,x1,y1 [--mono]

--mono replaces every colour with currentColor so the icon can be themed from CSS.
The faction emblem sits at the bottom of every datasheet card (keyword bar), e.g. page 0, bbox 290,300,362,357.
Needs PyMuPDF (pip install pymupdf).
"""
import argparse

import fitz


def path_d(items):
    d, cur = [], None
    for it in items:
        kind = it[0]
        if kind in ('l', 'c'):
            p0 = it[1]
            if cur is None or abs(cur.x - p0.x) > 1e-3 or abs(cur.y - p0.y) > 1e-3:
                d.append(f'M{p0.x:.2f} {p0.y:.2f}')
            if kind == 'l':
                d.append(f'L{it[2].x:.2f} {it[2].y:.2f}')
                cur = it[2]
            else:
                d.append(f'C{it[2].x:.2f} {it[2].y:.2f} {it[3].x:.2f} {it[3].y:.2f} {it[4].x:.2f} {it[4].y:.2f}')
                cur = it[4]
        elif kind == 're':
            r = it[1]
            d.append(f'M{r.x0:.2f} {r.y0:.2f}H{r.x1:.2f}V{r.y1:.2f}H{r.x0:.2f}Z')
            cur = None
        elif kind == 'qu':
            q = it[1]
            d.append(f'M{q.ul.x:.2f} {q.ul.y:.2f}L{q.ur.x:.2f} {q.ur.y:.2f}L{q.lr.x:.2f} {q.lr.y:.2f}L{q.ll.x:.2f} {q.ll.y:.2f}Z')
            cur = None
    return ''.join(d)


def hexc(c):
    return '#%02x%02x%02x' % tuple(round(v * 255) for v in c) if c else 'none'


def to_svg(drawings, mono=False, pad=0.5):
    bb = fitz.Rect(drawings[0]['rect'])
    for dr in drawings[1:]:
        bb |= dr['rect']
    parts = []
    for dr in drawings:
        d = path_d(dr['items'])
        if not d:
            continue
        fill = ('currentColor' if mono else hexc(dr['fill'])) if dr.get('fill') else 'none'
        stroke = ('currentColor' if mono else hexc(dr['color'])) if dr.get('color') and 's' in dr['type'] else 'none'
        extra = f' stroke-width="{dr.get("width") or 1:.2f}"' if stroke != 'none' else ''
        if dr.get('even_odd'):
            extra += ' fill-rule="evenodd"'
        parts.append(f'<path d="{d}" fill="{fill}" stroke="{stroke}"{extra}/>')
    x0, y0, x1, y1 = bb.x0 - pad, bb.y0 - pad, bb.x1 + pad, bb.y1 + pad
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.2f} {y0:.2f} {x1 - x0:.2f} {y1 - y0:.2f}">{"".join(parts)}</svg>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf')
    ap.add_argument('page', type=int)
    ap.add_argument('out')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--ids')
    ap.add_argument('--bbox')
    ap.add_argument('--mono', action='store_true')
    args = ap.parse_args()

    drawings = fitz.open(args.pdf)[args.page].get_drawings()
    if args.list:
        for i, d in enumerate(drawings):
            r = d['rect']
            if r.width < 80 and r.height < 80:
                print(i, [round(v, 1) for v in r], d['type'], 'items', len(d['items']))
        return
    if args.ids:
        sel = [drawings[int(i)] for i in args.ids.split(',')]
    else:
        box = fitz.Rect(*map(float, args.bbox.split(',')))
        sel = [d for d in drawings if box.contains(d['rect'])]
    open(args.out, 'w').write(to_svg(sel, args.mono))
    print(f'{args.out}: {len(sel)} paths')


if __name__ == '__main__':
    main()
