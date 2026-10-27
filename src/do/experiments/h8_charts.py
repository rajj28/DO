"""SVG figures for H8, written by hand so the seed stays dependency-free.

Static images for a README, so there is no hover layer; every mark carries a <title>
(a native tooltip when the file is opened directly) and every plotted number is also
in the RESULTS.md table. Colors are the validated three-slot categorical set, light
and dark, switched by prefers-color-scheme and applied through classes (not var() in
attributes, which some image renderers ignore). Identity is never color alone: there
is a legend, and lines are labelled at their ends.
"""
from __future__ import annotations

from html import escape

# Entity -> categorical slot. Fixed, so an agent wears the same color in every figure.
SLOT = {"td(0.9)": 1, "td(0)": 2, "planner+cal always": 3}
NAMES = {"planner+cal always": "one-step planner, calibrated",
         "td(0)": "td, gamma 0 (next cycle)", "td(0.9)": "td, gamma 0.9 (long run)"}

STYLE = """<style>
  svg { --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
        --grid:#e1e0d9; --axis:#c3c2b7; --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; }
  @media (prefers-color-scheme: dark) {
    svg { --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781;
          --grid:#2c2c2a; --axis:#383835; --s1:#3987e5; --s2:#d95926; --s3:#199e70; }
  }
  text { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; fill: var(--ink2); }
  .title { font-size:15px; font-weight:600; fill: var(--ink); }
  .sub { font-size:12px; }
  .tick { font-size:11px; fill: var(--muted); font-variant-numeric: tabular-nums; }
  .label { font-size:12px; fill: var(--ink); }
  .strong { font-weight:600; }
  .note { font-size:11px; }
  .surface { fill: var(--surface); }
  .grid { stroke: var(--grid); stroke-width:1; }
  .axis { stroke: var(--axis); stroke-width:1; }
  .ref { stroke: var(--muted); stroke-width:1; }
  .leader { stroke: var(--muted); stroke-width:1; fill:none; }
  .f1 { fill: var(--s1); } .f2 { fill: var(--s2); } .f3 { fill: var(--s3); }
  .l1 { stroke: var(--s1); } .l2 { stroke: var(--s2); } .l3 { stroke: var(--s3); }
  .w1 { fill: var(--s1); fill-opacity:.1; } .w2 { fill: var(--s2); fill-opacity:.1; }
  .line { fill:none; stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }
  .dot { stroke: var(--surface); stroke-width:2; }
  .hit { fill: transparent; }
</style>"""


def _nice_max(v: float) -> float:
    for top in (0.004, 0.008, 0.01, 0.012, 0.016, 0.02, 0.024, 0.03, 0.04, 0.06, 0.08, 0.1):
        if v <= top:
            return top
    return v * 1.1


def _ticks(top: float, n: int = 4) -> list[float]:
    return [top * i / n for i in range(n + 1)]


def _fmt(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") if v else "0"


def _place(labels: list[tuple[float, str]], gap: float, lo: float, hi: float):
    """Spread end-labels at least `gap` apart inside [lo, hi]. Returns
    (wanted_y, placed_y, text); a moved label gets a leader line, never a silent shift."""
    items = sorted(labels)
    placed: list[float] = []
    for y, _ in items:
        placed.append(max(y, placed[-1] + gap) if placed else max(y, lo))
    overflow = placed[-1] - hi if placed else 0
    if overflow > 0:
        placed = [p - overflow for p in placed]
        for i in range(len(placed) - 2, -1, -1):
            placed[i] = min(placed[i], placed[i + 1] - gap)
    return [(y, p, t) for (y, t), p in zip(items, placed)]


def _open(W: int, H: int, label: str, title: str, sub: str) -> list[str]:
    return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'width="{W}" height="{H}" role="img" aria-label="{escape(label)}">', STYLE,
            f'<rect class="surface" width="{W}" height="{H}" rx="8"/>',
            f'<text class="title" x="20" y="28">{escape(title)}</text>',
            f'<text class="sub" x="20" y="47">{escape(sub)}</text>']


def learning_curve(curves: dict[str, list[tuple[int, float, float, float]]],
                   refs: dict[str, float], *, worlds: int, seeds: int,
                   before: float) -> str:
    """Held-out error over training. `curves`: agent -> [(runs, mean, lo, hi)];
    `refs`: label -> constant level of a non-learning comparator; `before`: the
    learner's error with no experience, which is stated rather than plotted."""
    W, H, L, R, T, B = 760, 390, 60, 250, 100, 46
    pw, ph = W - L - R, H - T - B
    xmax = max(p[0] for c in curves.values() for p in c)
    top = _nice_max(max([p[3] for c in curves.values() for p in c] + list(refs.values())))

    def x(v): return L + pw * v / xmax
    def y(v): return T + ph * (1 - v / top)

    out = _open(W, H, "Held-out drive error over training",
                "Held-out drive error while learning (lower is better)",
                f"Mean frugality error per cycle on {worlds} unseen worlds · {seeds} seeds"
                f" · band = 95% CI · before any experience: {before:.4f}, off this scale")
    lx = 20
    for name in ("td(0.9)", "td(0)"):
        out.append(f'<line class="line l{SLOT[name]}" x1="{lx}" y1="70" x2="{lx + 18}" y2="70"/>')
        out.append(f'<text class="note" x="{lx + 24}" y="74">{escape(NAMES[name])}</text>')
        lx += 220
    out.append(f'<line class="ref" x1="{lx}" y1="70" x2="{lx + 18}" y2="70"/>')
    out.append(f'<text class="note" x="{lx + 24}" y="74">planners (no value learning)</text>')
    for t in _ticks(top):
        out.append(f'<line class="grid" x1="{L}" x2="{L + pw}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>')
        out.append(f'<text class="tick" x="{L - 8}" y="{y(t) + 4:.1f}" '
                   f'text-anchor="end">{_fmt(t)}</text>')
    for v in range(1000, xmax + 1, 1000):
        out.append(f'<text class="tick" x="{x(v):.1f}" y="{T + ph + 18}" '
                   f'text-anchor="middle">{v:,}</text>')
    out.append(f'<line class="axis" x1="{L}" x2="{L + pw}" y1="{T + ph}" y2="{T + ph}"/>')
    out.append(f'<text class="tick" x="{L + pw / 2:.1f}" y="{H - 8}" '
               f'text-anchor="middle">training runs (16 cycles each)</text>')

    labels: list[tuple[float, str]] = []
    for name, level in refs.items():
        out.append(f'<line class="ref" x1="{L}" x2="{L + pw}" y1="{y(level):.1f}" '
                   f'y2="{y(level):.1f}"><title>{escape(name)}: {level:.4f}</title></line>')
        labels.append((y(level), f"{name} {level:.4f}"))
    for name, pts in curves.items():
        k = SLOT[name]
        band = ([f"{x(p[0]):.1f},{y(p[3]):.1f}" for p in pts]
                + [f"{x(p[0]):.1f},{y(p[2]):.1f}" for p in reversed(pts)])
        out.append(f'<polygon class="w{k}" points="{" ".join(band)}"/>')
        line = " ".join(f"{x(p[0]):.1f},{y(p[1]):.1f}" for p in pts)
        out.append(f'<polyline class="line l{k}" points="{line}"/>')
        for p in pts:
            out.append(f'<circle class="hit" cx="{x(p[0]):.1f}" cy="{y(p[1]):.1f}" r="8">'
                       f'<title>{escape(NAMES[name])} after {p[0]:,} runs: {p[1]:.4f} '
                       f'(95% CI {p[2]:.4f}-{p[3]:.4f})</title></circle>')
        end = pts[-1]
        out.append(f'<circle class="f{k} dot" cx="{x(end[0]):.1f}" cy="{y(end[1]):.1f}" r="4"/>')
        labels.append((y(end[1]), f"{name} {end[1]:.4f}"))
    for want, at, text in _place(labels, 15, T + 6, T + ph):
        if abs(at - want) > 1:
            out.append(f'<path class="leader" d="M{L + pw + 6},{want:.1f} '
                       f'L{L + pw + 14},{at:.1f}"/>')
        out.append(f'<text class="label" x="{L + pw + 18}" y="{at + 4:.1f}">'
                   f'{escape(text)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def ablation(groups: list[tuple[str, dict[str, tuple[float, float, float]]]], *,
             worlds: int, seeds: int) -> str:
    """Grouped horizontal bars, so every value fits at its bar's tip.
    `groups`: [(group label, {agent: (mean, lo, hi)})]."""
    agents = list(groups[0][1])
    bar, gap, head, between = 22, 2, 26, 22
    W, L, R, T = 760, 250, 96, 84
    block = head + len(agents) * bar + (len(agents) - 1) * gap
    H = T + len(groups) * block + (len(groups) - 1) * between + 44
    pw, bottom = W - L - R, H - 44
    top = _nice_max(max(v[2] for _, g in groups for v in g.values()))

    def x(v): return L + pw * v / top

    out = _open(W, H, "Mechanism ablation",
                "Remove the flow action and lookahead stops paying",
                f"Mean frugality error per cycle (lower is better) · {worlds} unseen worlds"
                f" · {seeds} seeds · whiskers = 95% CI across seeds")
    lx = 20
    for a in agents:
        out.append(f'<rect class="f{SLOT[a]}" x="{lx}" y="58" width="12" height="12" rx="2"/>')
        out.append(f'<text class="note" x="{lx + 18}" y="68">{escape(NAMES.get(a, a))}</text>')
        lx += 232
    for t in _ticks(top):
        out.append(f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{T}" '
                   f'y2="{bottom}"/>')
        out.append(f'<text class="tick" x="{x(t):.1f}" y="{bottom + 16}" '
                   f'text-anchor="middle">{_fmt(t)}</text>')
    out.append(f'<line class="axis" x1="{L}" x2="{L}" y1="{T}" y2="{bottom}"/>')
    gy = T
    for glabel, vals in groups:
        out.append(f'<text class="label strong" x="20" y="{gy + 16}">{escape(glabel)}</text>')
        by = gy + head
        for a in agents:
            m, lo, hi = vals[a]
            x1, r = x(m), min(4.0, (x(m) - L) / 2)
            d = (f"M{L},{by:.1f} H{x1 - r:.1f} Q{x1:.1f},{by:.1f} {x1:.1f},{by + r:.1f} "
                 f"V{by + bar - r:.1f} Q{x1:.1f},{by + bar:.1f} {x1 - r:.1f},{by + bar:.1f} "
                 f"H{L} Z")
            out.append(f'<text class="note" x="{L - 10}" y="{by + bar / 2 + 4:.1f}" '
                       f'text-anchor="end">{escape(NAMES.get(a, a))}</text>')
            out.append(f'<path class="f{SLOT[a]}" d="{d}"><title>{escape(glabel)} · '
                       f'{escape(NAMES.get(a, a))}: {m:.4f} (95% CI {lo:.4f}-{hi:.4f})'
                       f'</title></path>')
            cy = by + bar / 2
            out.append(f'<path class="leader" d="M{x(lo):.1f},{cy:.1f} H{x(hi):.1f} '
                       f'M{x(lo):.1f},{cy - 4:.1f} V{cy + 4:.1f} M{x(hi):.1f},{cy - 4:.1f} '
                       f'V{cy + 4:.1f}"/>')
            out.append(f'<text class="label" x="{max(x1, x(hi)) + 8:.1f}" y="{cy + 4:.1f}">'
                       f'{m:.4f}</text>')
            by += bar + gap
        gy += block + between
    out.append("</svg>")
    return "\n".join(out)
