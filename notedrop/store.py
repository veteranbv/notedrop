"""Immutable messages, session metadata, and local acknowledgement markers."""

import hashlib
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .fs import Error, directory, json_bytes, publish, read_bytes, read_json
from .instructions import AGENT_GUIDE

BODY_LIMIT = 64 * 1024
SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?\Z")
ALIAS = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
SESSION = re.compile(r"\d{8}-\d{4}-[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?-[0-9a-f]{8}\Z")
ID = re.compile(r"[0-9a-f]{32}\Z")
FIELDS = {"v", "id", "session", "ts", "from", "to", "thread", "in_reply_to", "body"}


def checked(value, pattern, label):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise Error(f"Invalid {label}: {value!r}")
    return value


def alias(value, recipient=False):
    checked(value, ALIAS, "alias")
    if value == "all" and not recipient:
        raise Error("'all' is reserved for broadcast recipients")
    return value


def body_text(body):
    if not isinstance(body, str):
        raise Error("Message body must be text")
    try:
        size = len(body.encode("utf-8"))
    except UnicodeError as exc:
        raise Error("Message body must be valid UTF-8 text") from exc
    if not body.strip() or size > BODY_LIMIT:
        raise Error("Message body must be nonblank and at most 65536 UTF-8 bytes")
    return body


def validate_message(message, session):
    if not isinstance(message, dict) or set(message) != FIELDS:
        raise Error("Message fields do not match schema v1")
    if type(message["v"]) is not int or message["v"] != 1:
        raise Error("Unsupported message schema version")
    checked(message["id"], ID, "message ID")
    if message["session"] != session:
        raise Error("Message belongs to another session")
    if type(message["ts"]) is not int or not 0 <= message["ts"] <= 253402300799999:
        raise Error("Timestamp must be Unix milliseconds in the years 1970-9999")
    alias(message["from"])
    alias(message["to"], recipient=True)
    checked(message["thread"], ID, "thread ID")
    if message["in_reply_to"] is not None:
        checked(message["in_reply_to"], ID, "parent message ID")
    body_text(message["body"])
    return message


@dataclass
class Snapshot:
    messages: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Store:
    def __init__(self, home, state_home):
        if os.name != "posix":
            raise Error("notedrop v1 requires macOS or Linux POSIX file operations")
        self.home = Path(home).expanduser().resolve()
        self.state_home = Path(state_home).expanduser().resolve()
        if self.state_home.is_relative_to(self.home):
            raise Error("NOTEDROP_STATE_HOME must be outside NOTEDROP_HOME and outside sync")
        self.root_id = hashlib.sha256(os.fsencode(self.home)).hexdigest()

    def session_path(self, session):
        checked(session, SESSION, "session name")
        return self.home / "sessions" / session

    def new(self, slug, goal=""):
        checked(slug, SLUG, "slug (1-40 lowercase letters, digits, or hyphens)")
        if not isinstance(goal, str) or len(goal.encode("utf-8")) > BODY_LIMIT:
            raise Error("Goal must be text of at most 65536 UTF-8 bytes")
        with directory(self.home, "sessions", create=True) as sessions_fd:
            for _ in range(10):
                name = f"{datetime.now():%Y%m%d-%H%M}-{slug}-{secrets.token_hex(4)}"
                try:
                    os.mkdir(name, 0o700, dir_fd=sessions_fd)
                    break
                except FileExistsError:
                    continue
            else:
                raise Error("Could not allocate a unique session name; retry")
        record = {"v": 1, "name": name, "created": time.time_ns() // 1_000_000, "goal": goal}
        summary = (
            f"# {name}\n\n## Goal\n\n{goal or '(Not supplied.)'}\n\n"
            "## Expected deliverable\n\n(Not supplied. Clarify in a message.)\n\n"
            "## Success criteria\n\n(Not supplied. Clarify in a message.)\n\n"
            "## Participation\n\nRead AGENTS.md and choose a distinct alias. "
            "Record later decisions in messages.\n"
        )
        with directory(self.home, "sessions", name) as fd:
            os.mkdir("messages", 0o700, dir_fd=fd)
            publish(fd, "SESSION.md", summary.encode("utf-8"))
            publish(fd, "AGENTS.md", AGENT_GUIDE.encode("utf-8"))
            os.symlink("AGENTS.md", "CLAUDE.md", dir_fd=fd)
            # Metadata is published last. Sync may still deliver these out of order.
            publish(fd, "session.json", json_bytes(record))
        return name

    def metadata(self, session):
        self.session_path(session)
        with directory(self.home, "sessions", session) as fd:
            record = read_json(fd, "session.json")
        if (
            not isinstance(record, dict)
            or set(record) != {"v", "name", "created", "goal"}
            or type(record["v"]) is not int
            or record["v"] != 1
            or record["name"] != session
            or type(record["created"]) is not int
            or not 0 <= record["created"] <= 253402300799999
            or not isinstance(record["goal"], str)
        ):
            raise Error(f"Invalid or unsupported session metadata: {session}")
        try:
            if len(record["goal"].encode("utf-8")) > BODY_LIMIT:
                raise Error("Session goal exceeds 65536 UTF-8 bytes")
        except UnicodeError as exc:
            raise Error("Session goal is not valid UTF-8") from exc
        return record

    def sessions(self):
        try:
            with directory(self.home, "sessions") as fd:
                names = sorted(os.listdir(fd))
        except FileNotFoundError:
            return [], []
        records, warnings = [], []
        for name in names:
            if not SESSION.fullmatch(name):
                continue
            try:
                records.append(self.metadata(name))
            except (Error, OSError) as exc:
                warnings.append(f"{name}: {exc}")
        return records, warnings

    def scan(self, session):
        self.metadata(session)
        by_id, conflicts = {}, set()
        result = Snapshot()
        with directory(self.home, "sessions", session, "messages") as fd:
            for name in sorted(os.listdir(fd)):
                if name.startswith(".") or not name.endswith(".json"):
                    continue
                try:
                    message = validate_message(read_json(fd, name), session)
                except (Error, OSError) as exc:
                    result.warnings.append(f"{name!r}: {exc}")
                    continue
                message_id = message["id"]
                if message_id in by_id and by_id[message_id] != message:
                    conflicts.add(message_id)
                else:
                    by_id[message_id] = message
        for message_id in sorted(conflicts):
            result.warnings.append(f"Conflicting contents for message {message_id}; excluded")
        result.messages = sorted(
            (m for key, m in by_id.items() if key not in conflicts),
            key=lambda m: (m["ts"], m["id"]),
        )
        return result

    def send(self, session, sender, recipient, body, thread=None, parent=None):
        self.metadata(session)
        alias(sender)
        alias(recipient, recipient=True)
        body_text(body)
        if thread is not None:
            checked(thread, ID, "thread ID")
        if parent is not None:
            checked(parent, ID, "parent message ID")
            if thread is None:
                raise Error("A reply must specify its thread")
        with directory(self.home, "sessions", session, "messages") as fd:
            for _ in range(10):
                message_id = uuid.uuid4().hex
                message = {
                    "v": 1,
                    "id": message_id,
                    "session": session,
                    "ts": time.time_ns() // 1_000_000,
                    "from": sender,
                    "to": recipient,
                    "thread": thread or message_id,
                    "in_reply_to": parent,
                    "body": body,
                }
                try:
                    publish(fd, f"{message_id}.json", json_bytes(message))
                    return message
                except FileExistsError:
                    continue
        raise Error("Could not allocate a message ID without overwriting a file; retry")

    @staticmethod
    def addressed(message, reader):
        return message["to"] == reader or (message["to"] == "all" and message["from"] != reader)

    def _receipt_parts(self, session, reader):
        self.session_path(session)
        alias(reader)
        return self.root_id, session, reader

    def inbox(self, session, reader, all_messages=False):
        parts = self._receipt_parts(session, reader)
        result = self.scan(session)
        addressed = [m for m in result.messages if self.addressed(m, reader)]
        if all_messages:
            result.messages = addressed
            return result
        seen = set()
        try:
            with directory(self.state_home, *parts) as fd:
                for message in addressed:
                    try:
                        content = read_bytes(fd, message["id"], 0)
                        if content == b"":
                            seen.add(message["id"])
                    except FileNotFoundError:
                        pass
                    except (Error, OSError) as exc:
                        result.warnings.append(f"Invalid receipt {message['id']}: {exc}")
        except FileNotFoundError:
            pass
        result.messages = [m for m in addressed if m["id"] not in seen]
        return result

    def ack(self, session, reader, message_ids):
        parts = self._receipt_parts(session, reader)
        for message_id in message_ids:
            checked(message_id, ID, "message ID")
        result = self.scan(session)
        eligible = {m["id"] for m in result.messages if self.addressed(m, reader)}
        missing = set(message_ids) - eligible
        if missing:
            raise Error(f"Not valid inbox messages for {reader}: {', '.join(sorted(missing))}")
        with directory(self.state_home, *parts, create=True) as fd:
            for message_id in dict.fromkeys(message_ids):
                try:
                    # An empty, exclusively created marker is already a complete receipt.
                    handle = os.open(
                        message_id,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=fd,
                    )
                except FileExistsError:
                    read_bytes(fd, message_id, 0)
                else:
                    os.close(handle)
            os.fsync(fd)
        return result.warnings

    def reply(self, session, sender, message_id, body):
        checked(message_id, ID, "message ID")
        result = self.scan(session)
        original = next((m for m in result.messages if m["id"] == message_id), None)
        if original is None:
            raise Error(
                f"Message {message_id} is missing, invalid, or conflicted; "
                "run inbox --all and check sync before replying"
            )
        if not self.addressed(original, sender):
            raise Error("Reply requires a message addressed to your alias or all")
        return self.send(
            session, sender, original["from"], body, thread=original["thread"], parent=message_id
        ), result.warnings
