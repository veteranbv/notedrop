# Session files

Real sessions default to `~/.notedrop/sessions/`, outside this repository.
Set `NOTEDROP_HOME` to change the parent data directory. Local read receipts
must live separately at `NOTEDROP_STATE_HOME`, outside sync.

Each session contains metadata, self-contained operating instructions, a
relative `CLAUDE.md -> AGENTS.md` symlink, and immutable message files.
Session names use local date/time, a short slug, and a random suffix.

Only the fictional sessions in `examples/` are committed. Other traffic
placed beneath this repository's `sessions/` directory is gitignored. There
is no generated shared index that could conflict or leak private goals.

See [the file protocol](../docs/protocol.md) and
[the example walkthrough](../docs/blog-example.md).
