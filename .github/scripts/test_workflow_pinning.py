"""Exercise the policy with valid pins and realistic accidental regressions."""

import tempfile
import unittest
from pathlib import Path

from check_workflow_pinning import scan_workflows

WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"


class WorkflowPolicyTest(unittest.TestCase):
    def test_rejects_tags_branches_and_missing_refs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ci.yml").write_text(
                "steps:\n"
                "  - uses: actions/checkout@v4\n"
                "  - uses: actions/setup-python@main\n"
                "  - uses: owner/action\n"
                f"  - uses: 'owner/action@{'a' * 40}' # release\n"
                "  - uses: ./local-action\n"
                "# - uses: ignored/comment@main\n",
                encoding="utf-8",
            )
            self.assertEqual([v.line for v in scan_workflows(root)], [2, 3, 4])

    def test_pull_request_target_only_in_trusted_gate(self):
        files = {
            "review-gate-trusted.yml": "on:\n  pull_request_target:\n    types: [opened]\n",
            "block.yml": "name: x\non:\n  push:\n  pull_request_target:\njobs: {}\n",
            "inline.yml": "on: [push, pull_request_target]\n",
            "quoted.yml": "'on':\n  - 'pull_request_target'\n",
            "mention.yml": (
                "# pull_request_target is not used here\n"
                "on:\n"
                "  pull_request:  # not pull_request_target\n"
                "jobs:\n"
                "  a:\n"
                "    if: github.event_name != 'pull_request_target'\n"
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in files.items():
                (root / name).write_text(text, encoding="utf-8")
            found = sorted((v.path.name, v.line) for v in scan_workflows(root))
        self.assertEqual(found, [("block.yml", 4), ("inline.yml", 1), ("quoted.yml", 2)])

    def test_repository_workflows_pass(self):
        self.assertEqual(scan_workflows(WORKFLOWS), [])

    def test_review_gate_runs_only_trusted_default_branch_code(self):
        workflow = (WORKFLOWS / "review-gate-trusted.yml").read_text(encoding="utf-8")
        self.assertFalse((WORKFLOWS / "review-gate.yml").exists())
        self.assertIn("pull_request_target:", workflow)
        # One check suite per head: reopen/ready reruns reuse the existing job.
        self.assertIn("types: [opened, synchronize]", workflow)
        # The evaluator comes from the default-branch tip, never the PR head
        # or the base branch the PR chose.
        self.assertIn("ref: ${{ github.sha }}", workflow)
        self.assertNotIn("ref: ${{ github.event.pull_request.head", workflow)
        self.assertNotIn("ref: ${{ github.event.pull_request.base.sha }}", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("python3 -I", workflow)
        self.assertIn("permissions: {}", workflow)
        self.assertNotIn(": write", workflow)

    def test_review_gate_retrigger_admits_only_codex_bot(self):
        workflow = (WORKFLOWS / "review-gate-retrigger.yml").read_text(encoding="utf-8")
        triggers = workflow.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        # issue_comment only: a pull_request_review trigger would run the PR's copy.
        self.assertIn("issue_comment:", triggers)
        self.assertNotIn("pull_request_review", triggers)
        self.assertEqual(workflow.count("user.login == 'chatgpt-codex-connector[bot]'"), 1)
        self.assertNotIn("github.repository_owner", workflow)
        self.assertNotIn("actions/checkout", workflow)
        for body in ("comment.body", "review.body"):
            self.assertNotIn(f"${{{{ github.event.{body} }}}}", workflow)


if __name__ == "__main__":
    unittest.main()
