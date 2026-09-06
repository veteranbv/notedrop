# Compare two agents' findings for a blog

Create a session with a specific goal:

```sh
notedrop new webmcp-blog 'Compare two implementations and collect evidence for a blog'
```

Use aliases for two contributing agents and a writer. Generate a `join`
prompt for each, then paste it into the corresponding running conversation.
Ask contributors to summarize work from the conversations they can access.
No automatic provider-history integration is involved.

## Ask for comparable accounts

Have the writer send one question to `all`:

> What problem were you solving? What did you try? What worked or failed?
> Which evidence supports the finding? Include repository, commit, file,
> or accessible conversation references. What remains uncertain?

Each contributor replies to the question's message ID. The writer can ask
follow-up questions using the IDs of those responses. Avoid asking both
agents to edit the same summary file; collect their independent messages.

When the exchange is ready:

```sh
mkdir -p exports
notedrop --session SESSION_NAME export > exports/conversation.md
```

Give the writer the export and ask for a comparison with source attribution.
The writer should distinguish observations, inferences, and unresolved
questions. An exported transcript is source material, not proof that each
contributor's claim is correct or that every remote message has arrived.

Local paths in messages need an accessible repository or useful excerpts.
Do not treat an unavailable path as verified evidence.

## Inspect the fictional exchange

The repository includes `sessions/examples/20260101-1200-demo-collab-1a2b3c4d`.
It illustrates an author asking two agents about related failures. It makes
no claims about actual WebMCP API behavior. Copy the example to a disposable
mailbox to try the CLI without changing the committed fixture:

```sh
demo_dir=$(mktemp -d)
mkdir -p "$demo_dir/mail/sessions"
cp -R sessions/examples/20260101-1200-demo-collab-1a2b3c4d "$demo_dir/mail/sessions/"
NOTEDROP_STATE_HOME="$demo_dir/state" ./bin/notedrop \
  --home "$demo_dir/mail" \
  --session 20260101-1200-demo-collab-1a2b3c4d \
  --as writer inbox
NOTEDROP_STATE_HOME="$demo_dir/state" ./bin/notedrop \
  --home "$demo_dir/mail" \
  --session 20260101-1200-demo-collab-1a2b3c4d export
```

Run these commands from the repository root. The temporary directory stays
available for inspection; remove it yourself when finished.
