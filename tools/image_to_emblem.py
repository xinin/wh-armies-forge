"""Turn a one-colour logo picture (PNG/JPG, dark on light or light on dark) into a faction emblem: the logo traced as
vector paths inside the diamond frame of the other emblems, drawn with currentColor (the app tints it).

    .venv/bin/python tools/image_to_emblem.py logo.png data/factions/salamanders/emblem.svg [--size 0.62] [--detail 1.2]

For logos that are not in the datasheet PDFs (tools/pdf_vector_icon.py traces those). The outline is traced pixel
by pixel (marching squares) on the picture scaled to ~400 px and simplified (--detail: tolerance in pixels; lower
keeps more detail). --size: how much of the frame the logo fills.
"""
import argparse
import sys

from PIL import Image

FRAME = '<path d="M50 3L97 50L50 97L3 50Z" fill="none" stroke="currentColor" stroke-width="2.6"/>'


def mask(path, work=400):
    img = Image.open(path).convert('L')
    img.thumbnail((work, work))
    w, h = img.size
    px = img.load()
    border = [px[x, y] for x in range(w) for y in (0, h - 1)] + [px[x, y] for y in range(h) for x in (0, w - 1)]
    light_bg = sum(border) / len(border) > 127  # the logo is whatever differs from the background
    return [[(px[x, y] < 128) == light_bg for x in range(w)] for y in range(h)], w, h


def contours(m, w, h):
    """Closed outlines between logo and background pixels, as lists of corner points."""
    edges = {}
    for y in range(h):
        for x in range(w):
            if not m[y][x]:
                continue
            # each pixel side that faces the background, oriented so the logo is on the left
            if y == 0 or not m[y - 1][x]:
                edges[(x + 1, y)] = (x, y)
            if y == h - 1 or not m[y + 1][x]:
                edges[(x, y + 1)] = (x + 1, y + 1)
            if x == 0 or not m[y][x - 1]:
                edges[(x, y)] = (x, y + 1)
            if x == w - 1 or not m[y][x + 1]:
                edges[(x + 1, y + 1)] = (x + 1, y)
    loops = []
    while edges:
        start, nxt = edges.popitem()
        loop = [start]
        while nxt != start and nxt in edges:
            loop.append(nxt)
            nxt = edges.pop(nxt)
        if len(loop) > 8:
            loops.append(loop)
    return loops


def simplify(points, tol):
    """Ramer-Douglas-Peucker on a closed loop."""
    def rdp(pts):
        if len(pts) < 3:
            return pts
        (x1, y1), (x2, y2) = pts[0], pts[-1]
        dx, dy = x2 - x1, y2 - y1
        norm = (dx * dx + dy * dy) ** 0.5 or 1
        dists = [abs(dy * (x - x1) - dx * (y - y1)) / norm for x, y in pts[1:-1]]
        i = max(range(len(dists)), key=dists.__getitem__)
        if dists[i] <= tol:
            return [pts[0], pts[-1]]
        return rdp(pts[:i + 2])[:-1] + rdp(pts[i + 1:])
    far = max(range(len(points)), key=lambda i: (points[i][0] - points[0][0]) ** 2 + (points[i][1] - points[0][1]) ** 2)
    return rdp(points[:far + 1])[:-1] + rdp(points[far:] + [points[0]])[:-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image')
    ap.add_argument('out')
    ap.add_argument('--size', type=float, default=0.62, help='share of the frame the logo fills (default 0.62)')
    ap.add_argument('--detail', type=float, default=1.2, help='simplification tolerance in pixels (default 1.2)')
    args = ap.parse_args()
    m, w, h = mask(args.image)
    loops = [simplify(lp, args.detail) for lp in contours(m, w, h)]
    if not loops:
        sys.exit('no logo found in the picture')
    xs = [x for lp in loops for x, _ in lp]
    ys = [y for lp in loops for _, y in lp]
    x0, y0, bw, bh = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    scale = 100 * args.size / max(bw, bh)
    ox, oy = 50 - bw * scale / 2, 50 - bh * scale / 2
    d = ''.join('M' + 'L'.join(f'{ox + (x - x0) * scale:.2f} {oy + (y - y0) * scale:.2f}' for x, y in lp) + 'Z' for lp in loops)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">{FRAME}'
           f'<path d="{d}" fill="currentColor" fill-rule="evenodd"/></svg>')
    with open(args.out, 'w') as f:
        f.write(svg)
    print(f'{args.out}: {len(loops)} outlines, {sum(len(lp) for lp in loops)} points')


if __name__ == '__main__':
    main()
