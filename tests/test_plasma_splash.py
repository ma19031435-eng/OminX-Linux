"""The Harbor splash uses the vector logo, and the package stays vector-only."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'desktop/plasma/look-and-feel/com.ominx.harbor'
SPLASH = PKG / 'contents/splash/Splash.qml'
LOGO = PKG / 'contents/images/ominx-logo.svg'


class PlasmaSplashTests(unittest.TestCase):
    def test_splash_exists_and_declares_stage(self):
        text = SPLASH.read_text()
        self.assertIn('property int stage', text)

    def test_splash_uses_the_logo_that_ships_in_the_package(self):
        text = SPLASH.read_text()
        match = re.search(r'Qt\.resolvedUrl\("([^"]+)"\)', text)
        self.assertIsNotNone(match)
        self.assertTrue((SPLASH.parent / match.group(1)).resolve().exists(), match.group(1))
        self.assertTrue(LOGO.exists())

    def test_logo_is_vector(self):
        self.assertTrue(LOGO.read_text().lstrip().startswith('<?xml') or LOGO.read_text().lstrip().startswith('<svg'))


if __name__ == '__main__':
    unittest.main()
