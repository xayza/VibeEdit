"""Round 6: plugin options (read/set) for real.

Original semantics (CommandCatalog+Plugins.swift):
- plugins.options (read): "Read a plugin's options (schema, scope
  and current values)."
- plugins.option (edit): "Set one plugin option like the Plugins
  sheet: project-scope values are an undoable project edit,
  user-scope values are saved for this Mac. Omit value to reset
  it to the default."

This build: user-scope values live in plugins.json (runtime state,
never pushed); project-scope values live in the open project's
data under "plugin_options" and are saved with the project. A
plugin that declares no options has an empty schema — options are
never invented for it. All state in these tests lives in temp
dirs; the real windows/plugins.json is never touched.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), ".."))

from vibeedit_core.mcp import MCPServer  # noqa: E402
from vibeedit_core.plugins import (  # noqa: E402
    coerce_plugin_option_value, get_plugin_options,
    get_plugin_option_values, set_plugin_option)
from vibeedit_core.project import (  # noqa: E402
    Project, new_project, save_project)

OPT_DEMO = '''
def register():
    def transform_text(project, item_id):
        _, item = project.item(item_id)
        item["text"] = str(item["text"]).upper()
        return item

    return {"name": "opt_demo",
            "description": "Demo plugin with options.",
            "transform_text": transform_text,
            "options": [
                {"id": "strength", "type": "number", "default": 0.5,
                 "scope": "user", "description": "Effect strength."},
                {"id": "mode", "type": "choice",
                 "choices": ["fast", "slow"], "default": "fast",
                 "scope": "project", "description": "Run mode."},
                {"id": "flag", "type": "bool", "default": True,
                 "scope": "user"},
            ]}
'''

BAD_SCHEMA = '''
def register():
    return {"name": "bad_demo",
            "options": [{"id": "pick", "type": "choice",
                         "default": "a"}]}
'''


def _write_plugin(folder, filename, source):
    with open(os.path.join(folder, filename), "w",
              encoding="utf-8") as fh:
        fh.write(source)


class TestPluginOptionsModule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pdir = os.path.join(self.tmp, "plugins")
        os.makedirs(self.pdir)
        _write_plugin(self.pdir, "opt_demo.py", OPT_DEMO)
        _write_plugin(self.pdir, "bad_demo.py", BAD_SCHEMA)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_schema_and_defaults(self):
        schema = get_plugin_options("opt_demo", self.pdir)
        self.assertEqual([o["id"] for o in schema],
                         ["strength", "mode", "flag"])
        self.assertEqual([o["scope"] for o in schema],
                         ["user", "project", "user"])
        values = get_plugin_option_values("opt_demo", self.pdir)
        self.assertEqual(values, {"strength": 0.5, "mode": "fast",
                                  "flag": True})

    def test_user_scope_persists_in_plugins_json(self):
        res = set_plugin_option("opt_demo", "strength", "0.9", self.pdir)
        self.assertEqual(res, {"plugin": "opt_demo", "option": "strength",
                               "scope": "user", "value": 0.9,
                               "reset": False})
        state_path = os.path.join(self.tmp, "plugins.json")
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
        self.assertEqual(state["options"]["opt_demo"]["strength"], 0.9)
        self.assertEqual(
            get_plugin_option_values("opt_demo", self.pdir)["strength"],
            0.9)

    def test_project_scope_lives_in_project_data(self):
        data = {}
        res = set_plugin_option("opt_demo", "mode", "slow", self.pdir,
                                project_data=data)
        self.assertEqual(res["scope"], "project")
        self.assertEqual(data["plugin_options"]["opt_demo"]["mode"],
                         "slow")
        self.assertEqual(
            get_plugin_option_values("opt_demo", self.pdir,
                                     project_data=data)["mode"], "slow")

    def test_project_scope_without_project_errors(self):
        with self.assertRaises(ValueError):
            set_plugin_option("opt_demo", "mode", "slow", self.pdir,
                              project_data=None)

    def test_reset_restores_default_and_drops_override(self):
        set_plugin_option("opt_demo", "strength", "0.9", self.pdir)
        res = set_plugin_option("opt_demo", "strength", None, self.pdir)
        self.assertTrue(res["reset"])
        self.assertEqual(res["value"], 0.5)
        with open(os.path.join(self.tmp, "plugins.json"),
                  encoding="utf-8") as fh:
            state = json.load(fh)
        self.assertNotIn("strength", state["options"]["opt_demo"])

    def test_validation_rejects_bad_values(self):
        with self.assertRaises(ValueError):
            set_plugin_option("opt_demo", "mode", "warp", self.pdir)
        with self.assertRaises(ValueError):
            set_plugin_option("opt_demo", "strength", "loud", self.pdir)
        with self.assertRaises(ValueError):
            set_plugin_option("opt_demo", "flag", "maybe", self.pdir)
        with self.assertRaises(ValueError):
            set_plugin_option("opt_demo", "nope", "1", self.pdir)
        with self.assertRaises(KeyError):
            get_plugin_options("ghost_plugin", self.pdir)

    def test_bad_schema_errors_on_read(self):
        with self.assertRaises(ValueError):
            get_plugin_options("bad_demo", self.pdir)

    def test_coercion_words(self):
        opt = {"id": "flag", "type": "bool"}
        self.assertIs(coerce_plugin_option_value(opt, "on"), True)
        self.assertIs(coerce_plugin_option_value(opt, "OFF"), False)
        self.assertIs(coerce_plugin_option_value(opt, True), True)
        self.assertEqual(
            coerce_plugin_option_value({"id": "n", "type": "integer"},
                                       "3"),
            3)
        with self.assertRaises(ValueError):
            coerce_plugin_option_value({"id": "n", "type": "integer"},
                                       "3.5")

    def test_manifest_options_readable(self):
        sub = os.path.join(self.pdir, "manifest_demo")
        os.makedirs(sub)
        with open(os.path.join(sub, "plugin.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"id": "manifest_demo", "name": "Manifest demo",
                       "hooks": [],
                       "options": [{"id": "level", "type": "integer",
                                    "default": 2, "scope": "user"}]},
                      fh)
        schema = get_plugin_options("manifest_demo", self.pdir)
        self.assertEqual(schema[0]["id"], "level")
        res = set_plugin_option("manifest_demo", "level", "5", self.pdir)
        self.assertEqual(res["value"], 5)


class TestPluginOptionsTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pdir = os.path.join(self.tmp, "plugins")
        os.makedirs(self.pdir)
        _write_plugin(self.pdir, "opt_demo.py", OPT_DEMO)
        proj = Project(new_project("r6opts", width=320, height=180,
                                   fps=(30, 1)), self.tmp)
        save_project(proj.data,
                     os.path.join(self.tmp, "project.vibeedit.json"))
        self.server = MCPServer(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _opts(self, **kw):
        args = {"plugin": "opt_demo", "plugins_dir": self.pdir}
        args.update(kw)
        return args

    def test_options_tool_reads_schema_and_values(self):
        res = self.server.call("vibeedit_plugins_options",
                               self._opts())
        self.assertTrue(res["project_open"])
        by_id = {o["id"]: o for o in res["options"]}
        self.assertEqual(by_id["strength"]["value"], 0.5)
        self.assertEqual(by_id["mode"]["value"], "fast")

    def test_option_tool_sets_both_scopes_and_persists(self):
        self.server.call("vibeedit_plugins_option",
                         self._opts(option="strength", value="0.75"))
        self.server.call("vibeedit_plugins_option",
                         self._opts(option="mode", value="slow"))
        reopened = MCPServer(self.tmp)
        res = reopened.call("vibeedit_plugins_options", self._opts())
        by_id = {o["id"]: o for o in res["options"]}
        self.assertEqual(by_id["strength"]["value"], 0.75)
        self.assertEqual(by_id["mode"]["value"], "slow")
        # Reset restores the default.
        reopened.call("vibeedit_plugins_option",
                      self._opts(option="mode"))
        res = reopened.call("vibeedit_plugins_options", self._opts())
        by_id = {o["id"]: o for o in res["options"]}
        self.assertEqual(by_id["mode"]["value"], "fast")

    def test_option_tool_rejects_unknown_and_invalid(self):
        with self.assertRaises(ValueError):
            self.server.call("vibeedit_plugins_option",
                             self._opts(option="nope", value="1"))
        with self.assertRaises(ValueError):
            self.server.call("vibeedit_plugins_option",
                             self._opts(option="mode", value="warp"))

    def test_set_tool_toggles_and_refuses_hooks(self):
        res = self.server.call("vibeedit_plugins_set",
                               self._opts(enabled=False))
        self.assertFalse(res["enabled"])
        res = self.server.call("vibeedit_plugins_set",
                               self._opts(enabled=True))
        self.assertTrue(res["enabled"])
        with self.assertRaises(ValueError):
            self.server.call("vibeedit_plugins_set",
                             self._opts(enabled=False, hooks=True))
        with self.assertRaises(ValueError):
            self.server.call("vibeedit_plugins_set",
                             {"plugin": "opt_demo",
                              "plugins_dir": self.pdir})


if __name__ == "__main__":
    unittest.main()
