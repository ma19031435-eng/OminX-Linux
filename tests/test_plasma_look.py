"""Static checks for the OminX Harbor Plasma look.

These run in the sandbox. They do not start Plasma: that needs a running
desktop, and the README records that as unverified. The checks catch broken
JSON, INI, SVG and JavaScript, and they keep Microsoft names, icons and sounds
out of the package."""
import configparser
import json
import re
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLASMA = ROOT / 'desktop/plasma'
PACKAGE = PLASMA / 'look-and-feel/com.ominx.harbor'
SOUND_SUFFIXES = {'.wav', '.ogg', '.oga', '.mp3', '.flac', '.opus', '.m4a'}
RASTER_SUFFIXES = {'.png', '.jpg', '.jpeg', '.xpm', '.ico', '.bmp'}


def read_groups(path):
    """Parses KConfig files: [group] or nested [a][b] headers, key=value lines."""
    groups, current = {}, None
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith('[') and line.endswith(']'):
            header = ''.join(f'[{part}]' for part in re.findall(r'\[([^\]]*)\]', line))
            if header != line or not header:
                raise AssertionError(f'{path.name}:{number}: bad group header {line!r}')
            current = line
            groups.setdefault(current, {})
            continue
        if '=' not in line or current is None:
            raise AssertionError(f'{path.name}:{number}: not key=value: {line!r}')
        key, value = line.split('=', 1)
        groups[current][key.strip()] = value
    return groups


class MetadataTests(unittest.TestCase):
    def test_look_and_feel_metadata_is_valid(self):
        meta = json.loads((PACKAGE / 'metadata.json').read_text())
        self.assertEqual(meta['KPackageStructure'], 'Plasma/LookAndFeel')
        self.assertEqual(meta['KPlugin']['Id'], PACKAGE.name)
        self.assertEqual(meta['X-Plasma-APIVersion'], '2')
        self.assertTrue(meta['KPlugin']['License'])

    def test_defaults_point_at_this_package_and_its_colours(self):
        groups = read_groups(PACKAGE / 'contents/defaults')
        self.assertEqual(groups['[kdeglobals][KDE]']['LookAndFeelPackage'], PACKAGE.name)
        self.assertEqual(groups['[kdeglobals][General]']['ColorScheme'], 'OminXHarbor')
        self.assertEqual(groups['[kwinrc][org.kde.kdecoration2]']['ButtonsOnRight'], 'IAX')
        self.assertEqual(groups['[kwinrc][org.kde.kdecoration2]']['TitleAlignment'], '1')

    def test_defaults_wallpaper_exists_in_package(self):
        groups = read_groups(PACKAGE / 'contents/defaults')
        image = groups['[Wallpaper]']['Image']
        self.assertTrue(image.endswith('/contents/images/harbor-wallpaper.svg'), image)
        self.assertTrue((PACKAGE / 'contents/images/harbor-wallpaper.svg').is_file())


class ConfigFileTests(unittest.TestCase):
    def test_colour_scheme_has_the_sections_plasma_reads(self):
        groups = read_groups(PLASMA / 'color-schemes/OminXHarbor.colors')
        for name in ['[Colors:Window]', '[Colors:View]', '[Colors:Selection]', '[Colors:Button]',
                     '[Colors:Tooltip]', '[WM]', '[General]']:
            self.assertIn(name, groups)
        for name in ['[Colors:Window]', '[Colors:View]', '[Colors:Selection]']:
            for key in ['BackgroundNormal', 'ForegroundNormal']:
                parts = groups[name][key].split(',')
                self.assertEqual(len(parts), 3, f'{name} {key}')
                self.assertTrue(all(0 <= int(part) <= 255 for part in parts), f'{name} {key}')

    def test_xdg_defaults_parse_and_agree_with_the_look(self):
        for name in ['kwinrc', 'plasmarc', 'kdeglobals']:
            path = PLASMA / 'xdg' / name
            if name == 'plasmarc':
                configparser.ConfigParser(strict=True).read(path)
            else:
                read_groups(path)
        kwin = read_groups(PLASMA / 'xdg/kwinrc')['[org.kde.kdecoration2]']
        self.assertEqual(kwin['ButtonsOnRight'], 'IAX')
        self.assertEqual(kwin['TitleAlignment'], '1')
        self.assertEqual(read_groups(PLASMA / 'xdg/kdeglobals')['[KDE]']['LookAndFeelPackage'], PACKAGE.name)

    def test_wallpaper_svg_parses(self):
        root = ET.parse(PACKAGE / 'contents/images/harbor-wallpaper.svg').getroot()
        self.assertTrue(root.tag.endswith('svg'))


@unittest.skipUnless(shutil.which('node'), 'node is needed for the layout syntax check')
class LayoutScriptTests(unittest.TestCase):
    def test_bottom_bar_layout_parses(self):
        script = PACKAGE / 'contents/layouts/org.kde.plasma.desktop-layout.js'
        result = subprocess.run(['node', '--check', str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_layout_pins_the_bar_and_the_centred_row(self):
        text = (PACKAGE / 'contents/layouts/org.kde.plasma.desktop-layout.js').read_text()
        self.assertIn('panel.location = "bottom"', text)
        self.assertIn('panel.lengthMode = "fill"', text)
        self.assertEqual(text.count('addSpacer(panel)'), 2)
        self.assertIn('spacer.writeConfig("expanding", true)', text)
        self.assertIn('org.kde.plasma.icontasks', text)


class PackagePolicyTests(unittest.TestCase):
    def test_no_sounds_or_raster_images(self):
        files = [p for p in PLASMA.rglob('*') if p.is_file()]
        self.assertFalse([p for p in files if p.suffix.lower() in SOUND_SUFFIXES])
        self.assertFalse([p for p in files if p.suffix.lower() in RASTER_SUFFIXES])

    def test_no_microsoft_names_or_branding_in_the_package(self):
        # README.md documents what is avoided, so only installed files are checked.
        for path in PLASMA.rglob('*'):
            if not path.is_file() or path.name == 'README.md':
                continue
            # KConfig group headers such as [Windows] are KWin's own key names, not branding.
            lines = [line for line in path.read_text(errors='ignore').splitlines()
                     if not line.lstrip().startswith('[')]
            text = '\n'.join(lines).lower()
            self.assertNotIn('microsoft', text, path)
            self.assertNotIn('windows', text, path)


if __name__ == '__main__':
    unittest.main()
