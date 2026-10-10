from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orchestrator.adapters.process import ProcessOutput
from orchestrator.adapters.results import InvocationError
from orchestrator.runloop import SandboxedQualityRunner


class RecordingRunner:
    def __init__(self) -> None:
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append((tuple(argv), kwargs))
        log_dir = kwargs["log_dir"]
        return ProcessOutput(
            argv=tuple(argv),
            cwd=kwargs["cwd"],
            exit_code=0,
            timed_out=False,
            stdout="",
            stderr="",
            stdout_path=log_dir / "stdout.log",
            stderr_path=log_dir / "stderr.log",
            stdout_truncated=False,
            stderr_truncated=False,
            duration_seconds=0.01,
        )


class QualityRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.worktree = self.base / "worktree"
        self.worktree.mkdir()
        self.bwrap = self.base / "bwrap"
        self.bwrap.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.bwrap.chmod(0o700)
        self.recording = RecordingRunner()
        self.runner = SandboxedQualityRunner(
            sandbox_executable=str(self.bwrap), runner=self.recording
        )

    def test_allowlisted_check_has_filesystem_isolation_and_clean_environment(self) -> None:
        evidence = self.runner.run(
            ["orchestrator-help"],
            worktree=self.worktree,
            timeout_seconds=2,
            log_dir=self.base / "evidence",
        )
        self.assertTrue(evidence[0].passed)
        argv = self.recording.calls[0][0]
        self.assertIn("--unshare-pid", argv)
        self.assertIn("--clearenv", argv)
        self.assertIn("--bind", argv)
        self.assertNotIn("--ro-bind", argv[:4])
        self.assertEqual("/usr/bin/python3", argv[argv.index("--") + 1])

    def test_unknown_check_is_rejected_without_process_launch(self) -> None:
        with self.assertRaisesRegex(InvocationError, "not allowlisted"):
            self.runner.run(
                ["agent-supplied-command"],
                worktree=self.worktree,
                timeout_seconds=2,
                log_dir=self.base / "evidence",
            )
        self.assertEqual([], self.recording.calls)


if __name__ == "__main__":
    unittest.main()
