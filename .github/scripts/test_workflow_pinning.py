"""Exercise the policy with valid pins and realistic accidental regressions."""

import tempfile
import unittest
from pathlib import Path

from check_workflow_pinning import scan_workflows


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

    def test_review_gate_executes_base_script_without_checkout_credentials(self):
        workflow = (Path(__file__).parents[1] / "workflows/review-gate.yml").read_text()
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertNotIn("pull_request.head.sha }}\n          persist", workflow)


if __name__ == "__main__":
    unittest.main()
