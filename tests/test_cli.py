import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class CLITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("NOTEDROP_")}
        self.env.update(
            NOTEDROP_HOME=str(self.root / "mail"), NOTEDROP_STATE_HOME=str(self.root / "state")
        )
        result = self.run_cli("new", "blog", "Compare implementations")
        self.session = result.stdout.strip()
        self.env["NOTEDROP_SESSION"] = self.session

    def run_cli(self, *args, data=None, code=0, env=None, cwd=REPO, launcher=None):
        command = [sys.executable, "-m", "notedrop"] if launcher is None else [str(launcher)]
        result = subprocess.run(
            command + list(args),
            env=env or self.env,
            cwd=cwd,
            input=data,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, code, result.stderr)
        return result

    def test_round_trip_and_export(self):
        sent = json.loads(
            self.run_cli("--as", "alice", "send", "bob", "What worked?", "--json").stdout
        )
        inbox = json.loads(self.run_cli("--as", "bob", "inbox", "--json").stdout)
        self.assertEqual(inbox, [sent])
        response = json.loads(
            self.run_cli(
                "--as",
                "bob",
                "reply",
                sent["id"],
                "Evidence: src/client.py at commit 1234",
                "--json",
            ).stdout
        )
        self.assertEqual(response["in_reply_to"], sent["id"])
        self.run_cli("--as", "bob", "ack", sent["id"])
        self.assertEqual(json.loads(self.run_cli("--as", "bob", "inbox", "--json").stdout), [])
        self.assertEqual(
            json.loads(self.run_cli("--as", "bob", "inbox", "--all", "--json").stdout), [sent]
        )
        exported = self.run_cli("export").stdout
        self.assertIn("Local snapshot", exported)
        self.assertIn(sent["id"], exported)
        self.assertIn(response["body"], exported)
        records = [
            json.loads(line)
            for line in self.run_cli("export", "--format", "jsonl").stdout.splitlines()
        ]
        self.assertEqual({r["id"] for r in records}, {sent["id"], response["id"]})

    def test_configuration_precedence_and_no_global_state(self):
        env = dict(self.env, NOTEDROP_ALIAS="carol")
        result = json.loads(self.run_cli("--as", "alice", "whoami", "--json", env=env).stdout)
        self.assertEqual(result["alias"], {"value": "alice", "source": "option"})
        self.assertEqual(result["session"]["source"], "NOTEDROP_SESSION")
        result = json.loads(self.run_cli("whoami", "--json", env=env).stdout)
        self.assertEqual(result["alias"]["value"], "carol")
        new_session = self.run_cli("new", "other").stdout.strip()
        result = json.loads(self.run_cli("whoami", "--json").stdout)
        self.assertEqual(result["session"]["value"], self.session)
        self.assertNotEqual(new_session, self.session)
        self.assertFalse((self.root / "mail" / "active").exists())
        self.assertFalse((self.root / "state").exists())

    def test_show_reads_any_message_without_identity_or_receipts(self):
        body = "First line\nSecond line\x1b[2J"
        sent = json.loads(
            self.run_cli("--as", "alice", "send", "bob", "--stdin", "--json", data=body).stdout
        )
        messages = self.root / "mail" / "sessions" / self.session / "messages"
        original = messages / f"{sent['id']}.json"
        before = original.read_bytes()
        # Sync providers can rename copies; lookup must use the validated record ID.
        original.rename(messages / "provider-copy.json")
        self.assertEqual(json.loads(self.run_cli("show", sent["id"], "--json").stdout), sent)
        human = self.run_cli("--as", "observer", "show", sent["id"]).stdout
        self.assertNotIn("\x1b", human)
        self.assertIn("\\x1b", human)
        self.assertEqual((messages / "provider-copy.json").read_bytes(), before)
        self.assertFalse((self.root / "state").exists())
        self.assertEqual(json.loads(self.run_cli("--as", "bob", "inbox", "--json").stdout), [sent])

    def test_show_missing_invalid_and_conflicted_ids(self):
        self.run_cli("show", "../escape", code=2)
        missing = self.run_cli("show", "0" * 32, "--json", code=2)
        self.assertEqual(missing.stdout, "")
        self.assertIn("missing, invalid, or conflicted", missing.stderr)
        sent = json.loads(self.run_cli("--as", "alice", "send", "bob", "Original", "--json").stdout)
        messages = self.root / "mail" / "sessions" / self.session / "messages"
        (messages / "conflict.json").write_text(json.dumps(dict(sent, body="Different")))
        result = self.run_cli("show", sent["id"], "--json", code=2)
        self.assertEqual(result.stdout, "")
        self.assertIn("Conflicting contents", result.stderr)

    def test_thread_export_filters_both_directions_and_keeps_order(self):
        root = json.loads(self.run_cli("--as", "alice", "send", "bob", "Question", "--json").stdout)
        response = json.loads(
            self.run_cli("--as", "bob", "reply", root["id"], "Answer", "--json").stdout
        )
        self.run_cli("--as", "carol", "send", "all", "Unrelated")
        self.run_cli("--as", "bob", "ack", root["id"])
        records = [
            json.loads(line)
            for line in self.run_cli(
                "export", "--thread", root["thread"], "--format", "jsonl"
            ).stdout.splitlines()
        ]
        self.assertEqual(records, sorted([root, response], key=lambda m: (m["ts"], m["id"])))
        output = self.run_cli("export", "--thread", root["thread"]).stdout
        self.assertIn(f"Thread: {root['thread']}", output)
        self.assertIn(response["id"], output)
        self.assertNotIn("Unrelated", output)

    def test_thread_export_allows_missing_root_and_empty_results(self):
        thread = "0" * 32
        self.run_cli("export", "--thread", "not-an-id", code=2)
        self.assertEqual(self.run_cli("export", "--thread", thread, "--format", "jsonl").stdout, "")
        self.assertIn(f"Thread: {thread}", self.run_cli("export", "--thread", thread).stdout)
        sent = json.loads(
            self.run_cli(
                "--as", "alice", "send", "bob", "Root not synced", "--thread", thread, "--json"
            ).stdout
        )
        self.assertEqual(
            json.loads(self.run_cli("export", "--thread", thread, "--format", "jsonl").stdout),
            sent,
        )
        self.assertFalse((self.root / "state").exists())

    def test_focused_reads_preserve_scan_warnings(self):
        sent = json.loads(self.run_cli("--as", "alice", "send", "bob", "Good", "--json").stdout)
        (self.root / "mail" / "sessions" / self.session / "messages" / "bad.json").write_text("{")
        result = self.run_cli("show", sent["id"], "--json", code=3)
        self.assertEqual(json.loads(result.stdout), sent)
        self.assertIn("warning", result.stderr)
        result = self.run_cli("export", "--thread", sent["thread"], "--format", "jsonl", code=3)
        self.assertEqual(json.loads(result.stdout), sent)
        self.assertIn("warning", result.stderr)
        result = self.run_cli("export", "--thread", "0" * 32, code=3)
        self.assertIn("could not be read", result.stdout)

    def test_missing_configuration_and_invalid_input(self):
        self.run_cli("send", "bob", "No sender", code=2)
        env = dict(self.env)
        env.pop("NOTEDROP_SESSION")
        self.run_cli("--as", "alice", "inbox", env=env, code=2)
        self.run_cli("--as", "alice", "send", "bob", "body", "--stdin", data="extra", code=2)
        self.run_cli("--as", "alice", "send", "bob", code=2)
        self.run_cli("--as", "alice", "send", "bob", "--stdin", data="x" * 65537, code=2)
        self.run_cli("--as", "all", "inbox", code=2)
        self.run_cli("--session", "../escape", "--as", "alice", "inbox", code=2)
        self.run_cli("--as", "alice", "send", "bob", "text", "--from", "carol", code=2)
        self.run_cli("whoami", env=dict(self.env, NOTEDROP_HOME=""), code=2)

    def test_stdin_is_literal_and_preserves_newlines(self):
        body = "First line\n`touch never-created`\n$(echo not-executed)\nLast line\n"
        result = self.run_cli("--as", "alice", "send", "bob", "--stdin", "--json", data=body)
        self.assertEqual(json.loads(result.stdout)["body"], body)

    def test_partial_reads_have_structured_output_and_nonzero_status(self):
        self.run_cli("--as", "alice", "send", "bob", "Good")
        (self.root / "mail" / "sessions" / self.session / "messages" / "bad.json").write_text("{")
        result = self.run_cli("--as", "bob", "inbox", "--json", code=3)
        self.assertEqual(len(json.loads(result.stdout)), 1)
        self.assertIn("warning", result.stderr)
        self.assertIn("could not be read", self.run_cli("export", code=3).stdout)

    def test_join_is_copyable_and_writes_no_configuration(self):
        result = self.run_cli("--as", "alice", "join", self.session)
        lines = result.stdout.splitlines()
        command = next(
            line for line in lines if line.startswith("notedrop ") and line.endswith("inbox --json")
        )
        parsed = shlex.split(command)[1:]
        self.assertEqual(json.loads(self.run_cli(*parsed).stdout), [])
        self.assertIn("CLAUDE.md is a relative symlink", result.stdout)
        self.assertFalse((self.root / "state").exists())

    def test_source_launcher_works_through_symlink_outside_checkout(self):
        executable = self.root / "notedrop"
        executable.symlink_to(REPO / "bin" / "notedrop")
        self.assertIn(
            "notedrop 0.1.0", self.run_cli("--version", launcher=executable, cwd=self.root).stdout
        )
        self.run_cli("--as", "bob", "inbox", "--json", launcher=executable, cwd=self.root)

    def test_empty_mailbox_is_success(self):
        self.assertEqual(self.run_cli("--as", "bob", "inbox").stdout, "")
        self.assertEqual(json.loads(self.run_cli("--as", "bob", "inbox", "--json").stdout), [])

    def test_human_output_escapes_terminal_controls(self):
        body = "Visible\x1b[2J\x00\rhidden"
        sent = self.run_cli("--as", "alice", "send", "bob", "--stdin", "--json", data=body)
        self.assertEqual(json.loads(sent.stdout)["body"], body)
        human = self.run_cli("--as", "bob", "inbox").stdout
        self.assertNotIn("\x1b", human)
        self.assertIn("\\x1b", human)


if __name__ == "__main__":
    unittest.main()
