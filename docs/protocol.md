# File protocol v1

Notedrop stores messages as immutable UTF-8 JSON files. Any tool can read the
documented format. The CLI creates files; it does not migrate or repair them.

## Session

```text
<NOTEDROP_HOME>/sessions/YYYYMMDD-HHMM-slug-8hex/
  session.json
  SESSION.md
  AGENTS.md
  CLAUDE.md -> AGENTS.md
  messages/
    <32-hex-message-id>.json
```

The prefix uses local time, and the random suffix reduces cross-machine name
collisions. Local collisions are retried. Slugs are 1-40 lowercase ASCII
letters, digits, or hyphens, starting and ending in a letter or digit.
Name timestamps are labels, not synchronization clocks.

`session.json` contains exactly `v` (integer 1), `name`, `created` (Unix epoch
milliseconds), and `goal` (UTF-8 text, at most 64 KiB). It is published last
during creation. Remote sync can still deliver these files in any order.
Missing metadata or a missing messages directory is an operational error;
the reader can retry once synchronization completes. `ls` reports invalid
sessions and continues listing valid ones with exit code 3.

`SESSION.md` records the initial goal and labeled fields for any unspecified
deliverable and success criteria. Record subsequent decisions in messages.
`AGENTS.md` is self-contained. `CLAUDE.md` is a relative symlink, not a copy.
No file depends on a relative path back to the code repository.

## Message

```json
{
  "v": 1,
  "id": "11111111111141118111111111111111",
  "session": "20260101-1200-demo-collab-1a2b3c4d",
  "ts": 1767268800000,
  "from": "alice",
  "to": "bob",
  "thread": "11111111111141118111111111111111",
  "in_reply_to": null,
  "body": "What worked, and where is the evidence?"
}
```

All fields are required; unknown fields or versions are rejected. Timestamps
are integer Unix epoch milliseconds between 1970 and the end of year 9999.
The CLI creates UUID4 IDs; readers accept 32 lowercase hex characters for
message, thread, and parent IDs. New threads use their first message's ID.
Replies address the explicit parent's author and preserve its thread ID.
`send --thread ID` can add to a thread whose root is not available locally.
A reader does not reject an otherwise valid reply because its parent is
missing. Display ordering uses `(ts, id)` and is not causal ordering.

Aliases match `^[a-z0-9][a-z0-9._-]{0,63}$`. `all` is reserved for broadcast
recipients. Own broadcasts are excluded from the sender's inbox. A direct
message to yourself is allowed. The sender always comes from the resolved
CLI identity. That convention does not prevent impersonation outside the CLI.

Bodies must be nonblank and at most 65,536 UTF-8 bytes. Stdin preserves
newlines; specify `--stdin` explicitly. The entire JSON file is bounded to
512 KiB before parsing, allowing JSON escaping overhead. Duplicate JSON
keys, nonfinite numbers, invalid UTF-8, deep parse failures, and non-regular
files are diagnosed. Hidden files and names not ending in `.json` are ignored.

Readers inspect all other `.json` files, including provider-renamed copies.
Identical validated records with one ID appear once. If records disagree
under the same ID, that ID is excluded and a diagnostic is emitted. Invalid
files remain untouched and are retried on the next invocation. A snapshot
with skipped records returns exit code 3 while retaining valid output.

## Publication

The writer exclusively creates a private `.tmp` file inside the messages
directory. It writes, flushes, and fsyncs the content, then uses `os.link` to
add the final filename atomically. Unlike replacement, this operation fails
if the destination already exists, including a symlink. It fsyncs the
directory and removes the temporary name. Published content is never edited.

The temporary and final names briefly refer to the same completed file.
Persistent hard links are not part of the replicated format. A sync client
only needs to copy the completed regular files and the instruction symlink.
After a crash, leftover `.tmp` files are ignored. The CLI does not remove
unknown temporary files because another process could still own them.

Directory descriptors and `O_NOFOLLOW` prevent following symlinks beneath
configured data and state roots. Regular-file checks and nonblocking opens
also avoid treating devices or FIFOs as messages. Configured roots themselves
are resolved explicitly, allowing a user-chosen path through a symlink.
Instruction symlinks are intentional; message and receipt symlinks are not.

If a filesystem cannot publish safely, the command fails without a fallback
that replaces existing files. If an error occurs after publication, the
diagnostic identifies that uncertainty. Inspect the message before retrying.
An interruption or lost stdout can also leave a successfully published file.
There is no exactly-once send retry contract or remote-delivery guarantee.
fsync is not a promise against every hardware failure or provider behavior.

## Acknowledgements

The local state tree is:

```text
<NOTEDROP_STATE_HOME>/<sha256-of-resolved-data-root>/<session>/<alias>/<message-id>
```

Each acknowledgement is an empty regular file created exclusively. This
makes overlapping acknowledgements idempotent without a shared set rewrite.
Receipt paths must not be symlinks. Invalid receipts produce diagnostics and
leave the corresponding message unread. `ack` validates every requested ID
against valid, locally available messages addressed to the selected reader.
If a disk error interrupts a multi-ID ack, a subset may exist; retrying the
same IDs is safe.

`inbox`, `show`, `reply`, and `export` do not acknowledge. Reads do not create state.
Changing the local data-root path or local state directory creates a separate
reader namespace, so messages can appear unread again. Sync only the data
tree, not the state tree. The CLI rejects state at or beneath the data root;
it cannot discover whether an external application also syncs your state.

## Output and exits

`send` and `reply` print a message ID, or the full record with `--json`.
`inbox --json` prints an array. `show ID --json` prints one message object.
`whoami --json` prints values and sources.
Diagnostics go to stderr. Terminal inbox output escapes control characters.
Markdown export indents bodies as literal text, keeping peer Markdown from
changing transcript structure. JSONL export retains message records. Both
exports cover the whole locally available session, regardless of receipts,
unless `--thread ID` selects only messages whose `thread` field equals ID.
Source references remain in the bodies; the CLI never fetches them.

`show ID` and `export --thread ID` require full 32-character lowercase hex
IDs. They need no alias and can read messages between any participants.
Both use the same complete validated scan as unfiltered export, retaining
duplicate/conflict handling, ordering, and warnings even for unrelated files.
Filtering reduces output, not scan cost. A missing root does not prevent a
thread export from returning replies already present locally.

An empty thread export succeeds: JSONL emits nothing, and Markdown emits a
snapshot header with the requested thread ID. This does not prove the thread
is complete or nonexistent remotely. `show` exits 2 with no stdout if its
message is missing, invalid, or conflicted; scan warnings still go to stderr.
A valid result with scan warnings returns 3, including an empty thread export.

- 0: operation succeeded, including an empty inbox.
- 2: invalid input or operational failure. A write error after publication
  reports that the final file may already exist.
- 3: usable but incomplete scan results; diagnostics explain omitted records.
- 130: interruption; check for publication before retrying a write.

A reply may publish successfully and then return 3 for unrelated bad files
found during its scan. Receiving its message ID or JSON object confirms local
publication. `ack` can also complete for the named IDs while returning 3 for
unrelated malformed records. Never treat every nonzero exit as a failed send.

The Python storage module is internal. This document and the CLI are the v1
interoperability contract.
