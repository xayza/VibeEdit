"""Round 5: frozen-app skills path (follow-up to the installer work).

vibeedit_core/skills.py must resolve skills/ under sys._MEIPASS
when frozen (PyInstaller one-folder build ships skills/ as data),
exactly like plugins._plugins_dir() already does. Without this
branch a frozen app would resolve skills/ relative to the bundled
module path and silently list zero skills. The test fakes a frozen
app by setting sys.frozen / sys._MEIPASS and reloading the module;
no real frozen build is made here (a Windows .exe cannot be built
from this Linux VM).
"""

import importlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core import skills  # noqa: E402


class TestFrozenSkillsDir(unittest.TestCase):
    def test_source_checkout_dir_unchanged(self):
        self.assertTrue(os.path.isdir(skills.DEFAULT_SKILLS_DIR))
        self.assertTrue(skills.DEFAULT_SKILLS_DIR.endswith("skills"))
        self.assertEqual(len(skills.list_skills()), 4)

    def test_frozen_dir_uses_meipass(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "skills"))
            sys.frozen = True  # type: ignore[attr-defined]
            sys._MEIPASS = tmp  # type: ignore[attr-defined]
            try:
                importlib.reload(skills)
                self.assertEqual(skills.DEFAULT_SKILLS_DIR,
                                 os.path.join(tmp, "skills"))
            finally:
                del sys.frozen  # type: ignore[attr-defined]
                del sys._MEIPASS  # type: ignore[attr-defined]
                importlib.reload(skills)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertTrue(os.path.isdir(skills.DEFAULT_SKILLS_DIR))


if __name__ == "__main__":
    unittest.main()
