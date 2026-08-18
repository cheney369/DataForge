from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from dataforge.cli import main
from dataforge.deployment import smoke_server


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.body).encode()


class DeploymentSmokeTest(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_smoke_checks_live_ready_and_health_surfaces(self, urlopen):
        urlopen.side_effect = [
            FakeResponse({"status": "alive"}),
            FakeResponse({"status": "degraded", "ready": True}),
            FakeResponse({"status": "ok"}),
        ]

        result = smoke_server("http://127.0.0.1:8000/")

        self.assertEqual(result["status"], "ready")
        self.assertEqual(
            [item["path"] for item in result["checks"]],
            ["/api/liveness", "/api/readiness", "/api/health"],
        )

    @patch("dataforge.cli.dispatch")
    def test_doctor_returns_nonzero_when_core_is_blocked(self, dispatch):
        dispatch.return_value = {"status": "blocked", "ready": False}

        self.assertEqual(main(["doctor"]), 1)

    @patch("dataforge.cli.dispatch")
    def test_deep_doctor_returns_nonzero_when_dependency_probe_fails(self, dispatch):
        dispatch.return_value = {
            "status": "degraded",
            "ready": True,
            "dependency_probes": {"status": "degraded"},
        }

        self.assertEqual(main(["doctor", "--deep"]), 1)


if __name__ == "__main__":
    unittest.main()
