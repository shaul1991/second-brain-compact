# second-brain-compact

Private-only second brain starter for local Markdown notes, MCP tools, and an
optional private Git remote for your data.

`private` in tool results means your local user vault under `data/`.

## Quickstart

```bash
git clone <this-repo-url> second-brain-compact
cd second-brain-compact
cp .env.example .env
docker compose build
docker compose run --rm cli init
```

This creates an ignored local vault:

```text
data/
  capture/default/
  capture/triaged/
  capture/archive/
  notes/
  requests/
runtime/
  logs/
```

The app repository tracks code only. `data/` and `runtime/` are ignored.

## MCP Tools

The MCP server runs over stdio:

```bash
python -m services.mcp
```

It exposes four tools:

- `capture`: write a note into `data/capture/default` as restricted draft capture.
- `recall`: search promoted private notes and other non-restricted Markdown.
- `get_note`: read a non-restricted note by `doc_id`.
- `status`: show local vault counts and metadata.

`capture` always writes `visibility: restricted`, `status: draft`,
`classification: untriaged`, and `promotion_target: undecided`. `recall` and
`get_note` never return restricted notes.

## Register MCP Clients

All examples use the same Docker stdio command. Replace `/ABS/PATH` with the
absolute path to this checkout.

Claude project config:

```json
{
  "mcpServers": {
    "second-brain": {
      "command": "docker",
      "args": ["compose", "-f", "/ABS/PATH/second-brain-compact/docker-compose.yml", "run", "--rm", "-i", "-T", "mcp"]
    }
  }
}
```

Codex config:

```toml
[mcp_servers.second-brain]
command = "docker"
args = ["compose", "-f", "/ABS/PATH/second-brain-compact/docker-compose.yml", "run", "--rm", "-i", "-T", "mcp"]
startup_timeout_sec = 60
```

Gemini settings:

```json
{
  "mcpServers": {
    "second-brain": {
      "command": "docker",
      "args": ["compose", "-f", "/ABS/PATH/second-brain-compact/docker-compose.yml", "run", "--rm", "-i", "-T", "mcp"]
    }
  }
}
```

Ready-to-edit examples are in `mcp/`.

## Capture And Promote

Create a capture:

```bash
docker compose run --rm cli ingest --json '{"body":"Remember this implementation note","title":"Implementation note","tags":["dev"]}'
```

Captures are intentionally hidden from search until you promote them:

```bash
docker compose run --rm cli promote --id CAP-local-YYYYMMDD-0001 --target notes
```

After promotion, `recall` can find the note and `get_note` can read it.

Archive a capture instead:

```bash
docker compose run --rm cli archive --id CAP-local-YYYYMMDD-0001 --reason "not useful"
```

## Data Git

`data/` can be a nested private Git repository.

```bash
docker compose run --rm cli data init
docker compose run --rm cli data remote add git@github.com:you/your-private-brain-data.git
docker compose run --rm cli data status
docker compose run --rm cli data commit -m "backup: notes"
docker compose run --rm cli data push
```

One-step sync:

```bash
docker compose run --rm cli data sync
```

`data sync` commits dirty files, pulls with rebase, then pushes. It does not
resolve conflicts. Git failures are logged to `runtime/logs/data-git.log`.

## Local Python Mode

Docker is the default path. For direct Python usage:

```bash
python3 -m venv .venv
. .venv/bin/activate
export PYTHONPATH="$PWD"
export PRIVATE_REPO_PATH="$PWD/data"
export INGESTION_CAPTURE_PATH="$PWD/data/capture/default"
export INGESTION_LEDGER_PATH="$PWD/runtime/ingestion/seen-keys"
export MCP_AUDIT_LOG="$PWD/runtime/mcp/audit.log.jsonl"
bin/brain init
python -m services.mcp
```

