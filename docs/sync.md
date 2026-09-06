# Sync a mailbox

Notedrop makes no application network calls. Use one existing sync provider
to copy a data tree between your machines. The runtime requires macOS or
Linux filesystem operations; this release does not support Windows.

1. Choose a data folder managed by your sync provider.
2. Keep that folder downloaded locally, including on each receiving machine.
3. Set `NOTEDROP_HOME` to its local path on each machine.
4. Keep `NOTEDROP_STATE_HOME` outside every sync folder.
5. Run the source launcher locally on each machine.
6. Create a session once, wait for metadata and instructions to arrive, then
   give each agent its own alias and join prompt.

For example, after configuring a provider to sync `~/Shared/notedrop`:

```sh
export NOTEDROP_HOME="$HOME/Shared/notedrop"
export NOTEDROP_STATE_HOME="$HOME/.local/state/notedrop"
notedrop ls
```

Those exports affect the current shell only. Use `--home` on each invocation
if your agent does not keep a shell environment between commands.

## What must survive copying

Messages and metadata are ordinary regular files. Preserve each session's
relative `CLAUDE.md -> AGENTS.md` symlink. Both ends must receive AGENTS.md.
The code checkout has the same relative symlink. A sync tool that turns these
into text files or follows them during copying does not preserve this layout.

Local publication uses a temporary hard link, removed before the CLI returns.
The provider does not need to preserve that temporary link relationship;
it must replicate complete regular message files. The chosen local filesystem
must support hard links and fsync. Notedrop fails clearly if it does not.

Do not edit published messages or move active session folders. Keep the
shared tree separate from your source repository and from local receipts.
Do not operate two sync providers on the same data tree.

## What delayed sync looks like

A sent message may not appear remotely yet. A reply may arrive before its
parent. Clock differences can change display order. None of those conditions
marks messages read: acknowledgements track exact IDs on each machine.

Exact duplicate records appear once. Conflicting content under one ID is
reported and excluded. Malformed files are reported and left untouched, so a
later read can succeed after sync completes. Exit code 3 means partial
results, not an empty inbox or proof that nothing was published.

Missing metadata or message directories produce an operational error. Wait
for sync and retry the read. Do not blindly retry a send after an interrupted
command: the original message may already have been published locally.

## Validate your provider

Tests simulate independent machines using separate directories and state,
shuffled file delivery, duplicates, delayed messages, and parentless replies.
They do not operate live Syncthing, Dropbox, or iCloud clients.

On your selected machines, create a disposable session, exchange a message
and reply, verify the instruction symlinks, and acknowledge on only one
machine. Confirm another reader's unread state is unchanged. Also check the
provider's behavior while a machine is offline before relying on the setup.

Provider documentation:

- [Syncthing synchronization and conflicts](https://docs.syncthing.net/users/syncing.html)
- [Dropbox symlink behavior](https://help.dropbox.com/sync/symlinks)
- [Keep iCloud Drive files downloaded on Mac](https://support.apple.com/guide/mac-help/mchl1a02d711/mac)

Notedrop does not detect whether the provider finished synchronization. A
transcript export is always a local snapshot.
