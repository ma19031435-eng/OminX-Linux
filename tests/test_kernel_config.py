import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('graphics_config', Path(__file__).resolve().parents[1] / 'scripts/check-kernel-graphics.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class KernelGraphicsConfigTests(unittest.TestCase):
    def config(self):
        return '\n'.join(f'CONFIG_{key}=y' for key in m.REQUIRED)

    def test_builtins(self):
        m.check(self.config())

    def test_missing_fb_device_rejected(self):
        with self.assertRaisesRegex(ValueError, 'FB_DEVICE'):
            m.check(self.config().replace('CONFIG_FB_DEVICE=y', '# CONFIG_FB_DEVICE is not set'))

    def test_modules_are_not_packaged(self):
        with self.assertRaisesRegex(ValueError, 'DRM_BOCHS'):
            m.check(self.config().replace('CONFIG_DRM_BOCHS=y', 'CONFIG_DRM_BOCHS=m'))
