from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path

from dataforge.config import Settings
from dataforge.parser_capabilities import ParserCapabilities


class ParserCapabilitiesTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def _settings(self, **overrides):
        values = {
            "project_root": self.root,
            "state_dir": self.root / ".dataforge",
            "dataflow_path": None,
        }
        values.update(overrides)
        return Settings(**values)

    def test_missing_mineru_keeps_optional_parser_reserved(self):
        capability = ParserCapabilities(
            self._settings(mineru_command=str(self.root / "missing-mineru"))
        ).mineru()

        self.assertFalse(capability["available"])
        self.assertFalse(capability["in_use"])
        self.assertEqual(capability["integration_state"], "reserved")
        self.assertIn("原生解析器", capability["reason"])

    def test_responsive_mineru_cli_is_detected_but_not_activated(self):
        executable = self.root / "mineru"
        executable.write_text("#!/bin/sh\nprintf 'mineru 2.7.0\\n'\n", encoding="utf-8")
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

        capability = ParserCapabilities(
            self._settings(mineru_command=str(executable))
        ).mineru()

        self.assertTrue(capability["available"])
        self.assertTrue(capability["ready_for_activation"])
        self.assertFalse(capability["in_use"])
        self.assertEqual(capability["version"], "mineru 2.7.0")
        self.assertEqual(capability["backend"], "hybrid-auto-engine")

    def test_disabled_mode_does_not_probe_command(self):
        capability = ParserCapabilities(
            self._settings(mineru_mode="disabled", mineru_command=str(self.root / "mineru"))
        ).mineru()

        self.assertFalse(capability["available"])
        self.assertEqual(capability["integration_state"], "disabled")


if __name__ == "__main__":
    unittest.main()
