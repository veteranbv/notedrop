import errno
import json
import os
import random
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from notedrop.instructions import AGENT_GUIDE
from notedrop.store import BODY_LIMIT, Error, Store

REPO = Path(__file__).resolve().parents[1]


class MailboxTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "mail", self.root / "state")
        self.session = self.store.new("test-job", "Compare two approaches")
        self.path = self.store.session_path(self.session)
        self.messages = self.path / "messages"

    def send(self, body="Finding", sender="alice", to="bob", **kwargs):
        return self.store.send(self.session, sender, to, body, **kwargs)

    def ids(self, all_messages=False, reader="bob"):
        return {m["id"] for m in self.store.inbox(self.session, reader, all_messages).messages}

    def write_record(self, message, name=None):
        path = self.messages / (name or f"{message['id']}.json")
        path.write_text(json.dumps(message), encoding="utf-8")
        return path

    def test_session_layout_and_symlink(self):
        self.assertRegex(self.session, r"^\d{8}-\d{4}-test-job-[0-9a-f]{8}$")
        self.assertEqual(self.store.metadata(self.session)["goal"], "Compare two approaches")
        self.assertTrue((self.path / "CLAUDE.md").is_symlink())
        self.assertEqual(os.readlink(self.path / "CLAUDE.md"), "AGENTS.md")
        self.assertEqual((self.path / "CLAUDE.md").read_text(), AGENT_GUIDE)
        self.assertFalse((self.store.home / "INDEX.md").exists())
        self.assertIn("(Not supplied.", (self.path / "SESSION.md").read_text())

    def test_session_collision_retries_without_overwriting(self):
        with patch("notedrop.store.secrets.token_hex", return_value="00000000"):
            first = self.store.new("collision")
        suffixes = iter(["00000000", "11111111"])
        token_hex = secrets.token_hex
        with patch(
            "notedrop.store.secrets.token_hex",
            side_effect=lambda size: next(suffixes) if size == 4 else token_hex(size),
        ):
            second = self.store.new("collision")
        self.assertNotEqual(first, second)
        self.assertEqual(self.store.metadata(first)["name"], first)

    def test_invalid_paths_aliases_and_slugs(self):
        for slug in ("", "UPPER", "a b", "../outside", "-a", "a-", "a" * 41):
            with self.subTest(slug=slug), self.assertRaises(Error):
                self.store.new(slug)
        for value in ("../other", str(self.path), "missing", "a/b"):
            with self.subTest(session=value), self.assertRaises(Error):
                self.store.scan(value)
        for value in ("all", "Alice", "../alice", "", "x" * 65):
            with self.subTest(alias=value), self.assertRaises(Error):
                self.send(sender=value)
        with self.assertRaises(Error):
            self.send(to="../recipient")
        with self.assertRaises(Error):
            self.store.ack(self.session, "bob", ["../outside"])

    def test_store_and_state_must_be_separate(self):
        with self.assertRaises(Error):
            Store(self.store.home, self.store.home / "state")
        link = self.root / "linked-state"
        link.symlink_to(self.store.home, target_is_directory=True)
        with self.assertRaises(Error):
            Store(self.store.home, link)

    def test_send_creates_only_new_messages(self):
        before = {p: p.read_bytes() for p in self.path.iterdir() if p.is_file()}
        first = self.send("Same body")
        original = (self.messages / f"{first['id']}.json").read_bytes()
        second = self.send("Same body")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["from"], "alice")
        self.assertEqual(first["thread"], first["id"])
        self.assertEqual((self.messages / f"{first['id']}.json").read_bytes(), original)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertEqual(len(list(self.messages.iterdir())), 2)

    def test_message_collision_never_overwrites(self):
        first = self.send("Original")
        next_id = uuid.uuid4()
        with patch("notedrop.store.uuid.uuid4", side_effect=[uuid.UUID(first["id"]), next_id]):
            second = self.send("New")
        self.assertEqual(second["id"], next_id.hex)
        self.assertEqual(
            json.loads((self.messages / f"{first['id']}.json").read_text())["body"], "Original"
        )

    def test_destination_symlink_never_followed_or_replaced(self):
        outside = self.root / "outside"
        outside.write_text("keep")
        chosen = uuid.uuid4()
        target = self.messages / f"{chosen.hex}.json"
        target.symlink_to(outside)
        with patch("notedrop.store.uuid.uuid4", return_value=chosen), self.assertRaises(Error):
            self.send()
        self.assertTrue(target.is_symlink())
        self.assertEqual(outside.read_text(), "keep")

    def test_failed_publication_never_exposes_partial_message(self):
        with patch("notedrop.fs.os.link", side_effect=OSError(errno.ENOTSUP, "no links")):
            with self.assertRaisesRegex(Error, "safely publish"):
                self.send()
        self.assertEqual(list(self.messages.iterdir()), [])
        with patch("notedrop.fs.os.fsync", side_effect=OSError("write failed")):
            with self.assertRaises(Error):
                self.send()
        self.assertEqual(list(self.messages.iterdir()), [])

    def test_visible_final_file_is_complete(self):
        real_link = os.link
        observed = []

        def observe(src, dst, **kwargs):
            self.assertFalse((self.messages / dst).exists())
            data = json.loads((self.messages / src).read_text())
            self.assertEqual(data["body"], "x" * BODY_LIMIT)
            real_link(src, dst, **kwargs)
            observed.append(json.loads((self.messages / dst).read_text()))

        with patch("notedrop.fs.os.link", side_effect=observe):
            message = self.send("x" * BODY_LIMIT)
        self.assertEqual(observed, [message])

    def test_uncertain_durability_reports_published_id(self):
        real_fsync = os.fsync
        calls = 0

        def fsync(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("directory sync failed")
            real_fsync(fd)

        with patch("notedrop.fs.os.fsync", side_effect=fsync):
            with self.assertRaisesRegex(Error, "Published .*inspect it before retrying"):
                self.send()
        self.assertEqual(len(self.store.scan(self.session).messages), 1)

    def test_concurrent_process_sends_preserve_every_message(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("NOTEDROP_")}
        env["NOTEDROP_STATE_HOME"] = str(self.store.state_home)

        def run(i):
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "notedrop",
                    "--home",
                    str(self.store.home),
                    "--session",
                    self.session,
                    "--as",
                    "alice",
                    "send",
                    "bob",
                    str(i),
                ],
                cwd=REPO,
                env=env,
                text=True,
                capture_output=True,
                timeout=20,
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            runs = list(pool.map(run, range(24)))
        for result in runs:
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len({r.stdout.strip() for r in runs}), 24)
        self.assertEqual(
            {m["body"] for m in self.store.scan(self.session).messages}, {str(i) for i in range(24)}
        )

    def test_read_does_not_acknowledge(self):
        message = self.send()
        self.assertEqual(self.ids(), {message["id"]})
        self.assertEqual(self.ids(), {message["id"]})
        self.assertFalse(self.store.state_home.exists())
        self.store.ack(self.session, "bob", [message["id"]])
        self.store.ack(self.session, "bob", [message["id"]])
        self.assertEqual(self.ids(), set())
        self.assertEqual(self.ids(True), {message["id"]})

    def test_delayed_older_timestamp_is_unread(self):
        recent = self.send("Recent")
        self.store.ack(self.session, "bob", [recent["id"]])
        with patch("notedrop.store.time.time_ns", return_value=1000):
            old = self.send("Arrived late")
        self.assertEqual(self.ids(), {old["id"]})

    def test_broadcast_and_receipt_isolation(self):
        message = self.send(to="all")
        own_broadcast = self.send(sender="bob", to="all")
        other = self.send(to="carol")
        self.assertEqual(self.ids(), {message["id"]})
        self.store.ack(self.session, "bob", [message["id"]])
        self.assertIn(message["id"], self.ids(reader="carol"))
        with self.assertRaises(Error):
            self.store.ack(self.session, "bob", [other["id"]])
        with self.assertRaises(Error):
            self.store.ack(self.session, "bob", [own_broadcast["id"]])
        another_reader = Store(self.store.home, self.root / "other-state")
        self.assertIn(
            message["id"], {m["id"] for m in another_reader.inbox(self.session, "bob").messages}
        )

    def test_concurrent_acknowledgements_do_not_lose_receipts(self):
        messages = [self.send(str(i))["id"] for i in range(16)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda mid: self.store.ack(self.session, "bob", [mid]), messages * 2))
        self.assertEqual(self.ids(), set())

    def test_receipts_are_namespaced_by_root_and_session(self):
        message = self.send()
        self.store.ack(self.session, "bob", [message["id"]])
        peer = Store(self.root / "other-mail", self.store.state_home)
        shutil.copytree(self.store.home, peer.home, symlinks=True)
        self.assertEqual(len(peer.inbox(self.session, "bob").messages), 1)
        another = self.store.new("another")
        copied = dict(message, session=another)
        (self.store.session_path(another) / "messages" / f"{message['id']}.json").write_text(
            json.dumps(copied)
        )
        self.assertEqual(len(self.store.inbox(another, "bob").messages), 1)

    def test_reply_selects_explicit_parent_not_newest(self):
        first = self.send("Question one")
        self.send("Question two", sender="carol")
        reply, warnings = self.store.reply(self.session, "bob", first["id"], "Answer one")
        self.assertEqual(reply["to"], "alice")
        self.assertEqual(reply["thread"], first["thread"])
        self.assertEqual(reply["in_reply_to"], first["id"])
        self.assertEqual(warnings, [])
        self.assertIn(first["id"], self.ids())
        with self.assertRaises(Error):
            self.store.reply(self.session, "bob", uuid.uuid4().hex, "Missing")
        with self.assertRaises(Error):
            self.store.reply(self.session, "carol", first["id"], "Not mine")

    def test_utf8_size_and_blank_body(self):
        self.send("é" * (BODY_LIMIT // 2))
        for body in ("é" * (BODY_LIMIT // 2 + 1), "", " \n", "\ud800"):
            with self.subTest(body=repr(body[:20])), self.assertRaises(Error):
                self.send(body)

    def test_malformed_and_temporary_files_do_not_hide_valid_messages(self):
        good = self.send()
        (self.messages / "unfinished.tmp").write_text("not json")
        (self.messages / ".hidden.json").write_text("not json")
        broken = self.messages / "broken.json"
        broken.write_text("{")
        result = self.store.scan(self.session)
        self.assertEqual(result.messages, [good])
        self.assertEqual(len(result.warnings), 1)
        late = dict(good, id=uuid.uuid4().hex, body="Repaired by source")
        broken.write_text(json.dumps(late))
        self.assertEqual(self.ids(), {good["id"], late["id"]})

    def test_invalid_schemas_and_conflicting_ids(self):
        good = self.send()
        self.write_record(good, "copy (conflicted copy).json")
        self.assertEqual(self.store.scan(self.session).messages, [good])
        self.write_record(dict(good, body="different"), "conflict.json")
        result = self.store.scan(self.session)
        self.assertEqual(result.messages, [])
        self.assertTrue(any("Conflicting contents" in w for w in result.warnings))
        for index, (field, value) in enumerate(
            (
                ("v", True),
                ("ts", True),
                ("ts", -1),
                ("ts", 10**30),
                ("from", "ALICE"),
                ("id", "../x"),
                ("thread", "bad"),
                ("session", "wrong"),
                ("in_reply_to", 123),
            )
        ):
            invalid = dict(good, id=uuid.uuid4().hex)
            invalid[field] = value
            self.write_record(invalid, f"invalid-{index}-{field}.json")
        self.assertGreaterEqual(len(self.store.scan(self.session).warnings), 10)

    def test_unbounded_or_ambiguous_json_is_rejected(self):
        self.send()
        (self.messages / "huge.json").write_bytes(b" " * (512 * 1024 + 1))
        (self.messages / "duplicate.json").write_text('{"v":1,"v":1}')
        (self.messages / "nan.json").write_text('{"ts":NaN}')
        (self.messages / "deep.json").write_text("[" * 2000 + "]" * 2000)
        (self.messages / "encoding.json").write_bytes(b"\xff")
        result = self.store.scan(self.session)
        self.assertEqual(len(result.messages), 1)
        self.assertEqual(len(result.warnings), 5)

    def test_read_symlink_and_fifo_are_not_followed(self):
        original = self.send()
        (self.messages / "link.json").symlink_to(self.messages / f"{original['id']}.json")
        os.mkfifo(self.messages / "pipe.json")
        result = self.store.scan(self.session)
        self.assertEqual(len(result.messages), 1)
        self.assertEqual(len(result.warnings), 2)

    def test_message_directory_symlink_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.messages.rmdir()
        self.messages.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.send()
        with self.assertRaises(OSError):
            self.store.scan(self.session)
        self.assertEqual(list(outside.iterdir()), [])

    def test_session_directory_and_metadata_symlinks_are_rejected(self):
        metadata = self.path / "session.json"
        outside = self.root / "metadata"
        metadata.rename(outside)
        metadata.symlink_to(outside)
        with self.assertRaises(OSError):
            self.store.metadata(self.session)
        metadata.unlink()
        outside.rename(metadata)
        destination = self.root / "moved-session"
        self.path.rename(destination)
        self.path.symlink_to(destination, target_is_directory=True)
        with self.assertRaises(OSError):
            self.store.scan(self.session)

    def test_receipt_symlink_does_not_hide_or_ack_message(self):
        message = self.send()
        receipt = self.store.state_home / self.store.root_id / self.session / "bob" / message["id"]
        receipt.parent.mkdir(parents=True)
        outside = self.root / "outside"
        outside.write_bytes(b"")
        receipt.symlink_to(outside)
        result = self.store.inbox(self.session, "bob")
        self.assertEqual(result.messages, [message])
        self.assertEqual(len(result.warnings), 1)
        with self.assertRaises(OSError):
            self.store.ack(self.session, "bob", [message["id"]])
        self.assertTrue(receipt.is_symlink())

    def test_incomplete_session_is_reported(self):
        (self.path / "session.json").unlink()
        records, warnings = self.store.sessions()
        self.assertEqual(records, [])
        self.assertEqual(len(warnings), 1)
        with self.assertRaises(FileNotFoundError):
            self.store.scan(self.session)

    def test_two_machine_shuffled_replication(self):
        peer = Store(self.root / "peer-mail", self.root / "peer-state")
        shutil.copytree(self.store.home, peer.home, symlinks=True)
        question = self.send("Question")
        peer_messages = peer.session_path(self.session) / "messages"
        shutil.copy2(self.messages / f"{question['id']}.json", peer_messages)
        reply, _ = peer.reply(self.session, "bob", question["id"], "Answer")
        peer.ack(self.session, "bob", [question["id"]])
        # The author's clock goes backwards while its next message is offline.
        with patch("notedrop.store.time.time_ns", return_value=1000):
            late = self.send("Late broadcast", to="all")
        note = peer.send(self.session, "bob", "all", "Peer finding")
        transfers = [(p, peer_messages) for p in self.messages.glob("*.json")]
        transfers += [(p, self.messages) for p in peer_messages.glob("*.json")]
        random.Random(42).shuffle(transfers)
        for source, destination in transfers:
            shutil.copy2(source, destination / source.name)
            shutil.copy2(source, destination / f"duplicate-{source.name}")
        self.assertEqual(self.store.scan(self.session).messages, peer.scan(self.session).messages)
        self.assertEqual(len(self.store.scan(self.session).messages), 4)
        self.assertEqual({m["id"] for m in peer.inbox(self.session, "bob").messages}, {late["id"]})
        self.assertIn(question["id"], self.ids())
        self.assertEqual(self.ids(reader="alice"), {reply["id"], note["id"]})
        # Parent absence on a third reader must not invalidate the reply.
        third = Store(self.root / "third-mail", self.root / "third-state")
        shutil.copytree(
            self.store.home, third.home, symlinks=True, ignore=shutil.ignore_patterns("messages")
        )
        third_messages = third.session_path(self.session) / "messages"
        third_messages.mkdir()
        shutil.copy2(peer_messages / f"{reply['id']}.json", third_messages)
        self.assertEqual(third.inbox(self.session, "alice").messages, [reply])
        self.assertEqual(os.readlink(third.session_path(self.session) / "CLAUDE.md"), "AGENTS.md")


class RepositoryTest(unittest.TestCase):
    def test_root_symlink_and_example(self):
        self.assertTrue((REPO / "CLAUDE.md").is_symlink())
        self.assertEqual(os.readlink(REPO / "CLAUDE.md"), "AGENTS.md")
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            (home / "sessions").mkdir(parents=True)
            examples = list((REPO / "sessions" / "examples").glob("20*"))
            self.assertEqual(len(examples), 1)
            example = examples[0]
            shutil.copytree(example, home / "sessions" / example.name, symlinks=True)
            store = Store(home, Path(temporary) / "state")
            result = store.scan(example.name)
            self.assertGreaterEqual(len(result.messages), 4)
            self.assertEqual(result.warnings, [])
            self.assertEqual(
                (store.session_path(example.name) / "CLAUDE.md").read_text(), AGENT_GUIDE
            )

    def test_gitignore_keeps_examples_and_ignores_real_traffic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copy2(REPO / ".gitignore", root / ".gitignore")
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            paths = [
                "sessions/private-job/messages/a.json",
                "sessions/README.md",
                "sessions/examples/demo/messages/a.json",
                "sessions/examples/demo/CLAUDE.md",
                ".active-session",
                ".notedrop-alias",
                ".notedrop/sessions/job/message.json",
                ".notedrop-state/ack.json",
                "exports/conversation.md",
                "conversation.md",
                ".env",
                ".env.local",
                ".envrc",
                ".env.example",
                "docs/protocol.md",
            ]
            result = subprocess.run(
                ["git", "-C", str(root), "check-ignore", "--stdin"],
                input="\n".join(paths) + "\n",
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(set(result.stdout.splitlines()), {paths[0], *paths[4:13]})


if __name__ == "__main__":
    unittest.main()
