#!/usr/bin/env python3
"""Renders the preview images in docs/previews/.

Two kinds of preview, and each is labelled in the image:

* scheduling-terminal.png: a capture of real output. The host binaries are run
  against a fake sysroot, so the text is what the code prints.
* harbor-desktop-mockup.png: a mockup, not a screenshot. Plasma cannot run in
  the sandbox. Colours, bar height, pinned apps and window-button order are read
  from desktop/plasma config files, so the mockup follows the config.

Requires Pillow (pip install pillow). It is a documentation tool and is not
needed by the build or the tests."""
import configparser
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/previews'
MONO = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
MONO_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'
SANS = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
SANS_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def font(path, size):
    return ImageFont.truetype(path, size)


def read_groups(path):
    """KConfig-style reader: [group] and nested [a][b] headers, key=value lines."""
    groups, current = {}, None
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('[') and line.endswith(']'):
            current = line
            groups.setdefault(current, {})
        elif '=' in line and current:
            key, value = line.split('=', 1)
            groups[current][key.strip()] = value
    return groups


def hex_colour(rgb_text):
    r, g, b = (int(part) for part in rgb_text.split(','))
    return (r, g, b)


# ---------------------------------------------------------------- terminal

def capture_scheduling():
    """Runs the host binaries and returns the transcript lines."""
    win = ROOT / 'build/host/ominx-win'
    gs = ROOT / 'build/host/ominx-gamesched-test'
    for binary in (win, gs):
        if not binary.exists():
            raise SystemExit(f'missing {binary}: run make build/host/ominx-win build/host/ominx-gamesched-test')
    temp = Path(tempfile.mkdtemp(prefix='ominx-preview-'))
    try:
        games = temp / 'games'
        shutil.copytree(ROOT / 'compat/games', games, ignore=shutil.ignore_patterns('README.md'))
        (games / 'boostdemo.game').write_text(
            'id = boostdemo\nname = Boost Demo\nappid = boostdemo\nrunner = wine\n'
            'dir = Games/boostdemo\nexe = Demo/demo.exe\nanticheat = eac\n'
            'anticheat_status = vendor-opt-in\n')
        sysroot = temp / 'sysroot'
        ominx = sysroot / 'sys/fs/cgroup/ominx'
        user = ominx / f'user-{os.getuid()}'
        for path in [sysroot / 'sys/fs/cgroup', ominx, user, user / 'service', user / 'game-boostdemo']:
            path.mkdir(parents=True, exist_ok=True)
        for path in [sysroot / 'sys/fs/cgroup/cgroup.subtree_control', ominx / 'cgroup.subtree_control',
                     user / 'cgroup.subtree_control', user / 'service/cgroup.procs',
                     user / 'game-boostdemo/cgroup.procs', user / 'game-boostdemo/cpu.weight',
                     user / 'game-boostdemo/io.weight']:
            path.touch()
        gpu = sysroot / 'sys/class/drm/card0/device/power_dpm_force_performance_level'
        gpu.parent.mkdir(parents=True)
        gpu.write_text('auto\n')
        env = dict(os.environ, OMINX_GAMES_DIR=str(games), OMINX_SYSROOT=str(sysroot),
                   XDG_RUNTIME_DIR=str(temp), HOME=str(temp / 'home'))

        def run(args):
            result = subprocess.run(args, env=env, capture_output=True, text=True)
            return result.stdout.rstrip('\n').splitlines() + result.stderr.rstrip('\n').splitlines()

        lines = []
        lines += ['$ ominx-win game info valorant'] + run([str(win), 'game', 'info', 'valorant'])[:12]
        lines += ['', '$ ominx-win game check fortnite'] + run([str(win), 'game', 'check', 'fortnite'])[:3]
        lines += ['', '$ ominx-gamesched-test boostdemo boost 4242']
        lines += run([str(gs), str(sysroot), str(games), 'boostdemo', 'boost', '4242'])
        lines += ['', '$ ominx-gamesched-test boostdemo release 4242']
        lines += run([str(gs), str(sysroot), str(games), 'boostdemo', 'release', '4242'])
        lines += ['', '$ cat game-boostdemo/cpu.weight game-boostdemo/io.weight']
        lines += [(user / 'game-boostdemo/cpu.weight').read_text().strip(),
                  (user / 'game-boostdemo/io.weight').read_text().strip()]
        return lines
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def render_terminal(lines, path):
    fnt = font(MONO, 17)
    bold = font(MONO_BOLD, 17)
    pad, line_h = 28, 24
    # Size the image to the longest line instead of wrapping real output.
    width = max(1180, int(max(len(line) for line in lines) * 10.4) + 2 * pad + 20)
    height = pad * 2 + 46 + line_h * len(lines)
    img = Image.new('RGB', (width, height), (12, 18, 26))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width, 40], fill=(26, 38, 52))
    for i, colour in enumerate([(232, 113, 113), (232, 190, 96), (95, 211, 193)]):
        draw.ellipse([16 + i * 22, 13, 28 + i * 22, 25], fill=colour)
    draw.text((100, 11), 'OminX terminal: real output, captured from the host build', font=font(SANS, 15),
              fill=(160, 178, 190))
    y = 40 + pad
    for line in lines:
        if line.startswith('$ '):
            draw.text((pad, y), line, font=bold, fill=(95, 211, 193))
        elif line.startswith('Compatibility:') or line.startswith('status:'):
            draw.text((pad, y), line, font=fnt, fill=(226, 236, 242))
        elif 'refused' in line or 'not boosted' in line or 'skipped' in line or 'denied' in line:
            draw.text((pad, y), line, font=fnt, fill=(232, 190, 96))
        else:
            draw.text((pad, y), line, font=fnt, fill=(170, 186, 198))
        y += line_h
    img.save(path)


# ----------------------------------------------------------------- desktop

def harbor_config():
    package = ROOT / 'desktop/plasma/look-and-feel/com.ominx.harbor'
    layout = (package / 'contents/layouts/org.kde.plasma.desktop-layout.js').read_text()
    height = int(re.search(r'panel\.height = (\d+);', layout).group(1))
    launchers = re.findall(r'"applications:([^"]+)"', layout)
    colours = read_groups(ROOT / 'desktop/plasma/color-schemes/OminXHarbor.colors')
    kwin = read_groups(ROOT / 'desktop/plasma/xdg/kwinrc')['[org.kde.kdecoration2]']
    return {
        'height': height,
        'launchers': launchers,
        'window': colours['[Colors:Window]'],
        'wm': colours['[WM]'],
        'selection': colours['[Colors:Selection]'],
        'buttons_right': kwin['ButtonsOnRight'],
        'buttons_left': kwin['ButtonsOnLeft'],
        'title_alignment': int(kwin['TitleAlignment']),
    }


def draw_wallpaper(img):
    """Matches contents/images/harbor-wallpaper.svg: vertical gradient and wave lines."""
    width, height = img.size
    top, mid, bottom = (12, 24, 38), (18, 48, 74), (11, 43, 51)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / height
        if t < 0.6:
            a, b, k = top, mid, t / 0.6
        else:
            a, b, k = mid, bottom, (t - 0.6) / 0.4
        colour = tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))
        draw.line([(0, y), (width, y)], fill=colour)
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for n, base in enumerate([0.59, 0.65, 0.71, 0.76]):
        y0 = int(height * base)
        points = []
        for x in range(0, width + 1, 8):
            points.append((x, y0 + 18 * (1 if (x // 240) % 2 == 0 else -1) * (0.6 + 0.4 * n / 3)))
        od.line(points, fill=(95, 211, 193, 30), width=2)
    band = int(height * 0.593)
    for x in range(width):
        alpha = int(115 * (1 - abs(x - width / 2) / (width / 2)))
        od.line([(x, band), (x, band + 1)], fill=(95, 211, 193, alpha))
    img.paste(Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB'))


def render_desktop(cfg, path):
    width, height = 1920, 1080
    img = Image.new('RGB', (width, height))
    draw_wallpaper(img)
    draw = ImageDraw.Draw(img)

    # A window, to show the title and button order from kwinrc.
    wx, wy, ww, wh = 300, 150, 1000, 560
    title_h = 40
    frame = hex_colour(cfg['wm']['activeBackground'])
    draw.rounded_rectangle([wx, wy, wx + ww, wy + wh], radius=0, fill=(14, 26, 40),
                           outline=hex_colour(cfg['selection']['BackgroundNormal']), width=2)
    draw.rectangle([wx, wy, wx + ww, wy + title_h], fill=frame)
    title = 'Harbor sample window'
    tf = font(SANS_BOLD, 16)
    tw = draw.textlength(title, font=tf)
    title_x = wx + (ww - tw) / 2 if cfg['title_alignment'] == 1 else wx + 16
    draw.text((title_x, wy + 11), title, font=tf, fill=hex_colour(cfg['wm']['activeForeground']))
    # Button order from ButtonsOnRight, read left to right: I minimise, A maximise, X close.
    glyphs = {'I': '–', 'A': '□', 'X': '×'}
    bx = wx + ww - 3 * 46
    for letter in cfg['buttons_right']:
        if letter in glyphs:
            draw.text((bx + 16, wy + 8), glyphs[letter], font=font(SANS, 20),
                      fill=hex_colour(cfg['wm']['activeForeground']))
            bx += 46
    body = font(SANS, 18)
    draw.text((wx + 30, wy + 80), 'The title sits in the centre and the buttons sit at the right.', font=body,
              fill=(226, 236, 242))
    draw.text((wx + 30, wy + 110), 'Bottom bar: full width, pinned apps centred, tray and clock at the right.',
              font=body, fill=(160, 178, 190))

    # The bottom bar, read from the layout: height, pinned launchers and colours.
    bar_y = height - cfg['height']
    bar = hex_colour(cfg['wm']['activeBackground'])
    draw.rectangle([0, bar_y, width, height], fill=bar)
    draw.line([(0, bar_y), (width, bar_y)], fill=hex_colour(cfg['selection']['BackgroundNormal']), width=2)
    menu_w = 130
    draw.rounded_rectangle([12, bar_y + 6, 12 + menu_w, height - 6], radius=6,
                           fill=hex_colour(cfg['selection']['BackgroundNormal']))
    draw.text((34, bar_y + 12), 'OminX', font=font(SANS_BOLD, 18), fill=(255, 255, 255))

    slot = 44
    n = len(cfg['launchers'])
    row_w = n * slot + (n - 1) * 8
    x0 = (width - row_w) // 2
    for i, app in enumerate(cfg['launchers']):
        x = x0 + i * (slot + 8)
        draw.rounded_rectangle([x, bar_y + 7, x + slot, height - 7], radius=8, fill=(30, 52, 68))
        label = app.replace('.desktop', '').split('.')[-1][:2].upper()
        lf = font(SANS_BOLD, 15)
        lw = draw.textlength(label, font=lf)
        draw.text((x + (slot - lw) / 2, bar_y + 13), label, font=lf, fill=(95, 211, 193))
    # Tray and clock at the right.
    for i in range(3):
        tx = width - 330 + i * 34
        draw.ellipse([tx, bar_y + 17, tx + 18, bar_y + 35], fill=(120, 140, 155))
    draw.text((width - 210, bar_y + 6), '12:27', font=font(SANS_BOLD, 16), fill=(226, 236, 242))
    draw.text((width - 214, bar_y + 24), '10/25/26', font=font(SANS, 13), fill=(160, 178, 190))
    draw.rectangle([width - 6, bar_y, width, height], fill=(60, 110, 120))

    # Honest label, so the mockup is never taken for a real screenshot.
    tag = 'MOCKUP: rendered from desktop/plasma config, not a Plasma screenshot'
    tf2 = font(SANS_BOLD, 17)
    tagw = draw.textlength(tag, font=tf2)
    draw.rounded_rectangle([20, 20, 40 + tagw, 58], radius=6, fill=(232, 190, 96))
    draw.text((30, 27), tag, font=tf2, fill=(12, 18, 26))
    img.save(path)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lines = capture_scheduling()
    render_terminal(lines, OUT / 'scheduling-terminal.png')
    render_desktop(harbor_config(), OUT / 'harbor-desktop-mockup.png')
    print(f'wrote {OUT / "scheduling-terminal.png"}')
    print(f'wrote {OUT / "harbor-desktop-mockup.png"}')


if __name__ == '__main__':
    sys.exit(main())
