# ExA-SPIM Operations Agent

This repository contains a deployable, read-only agent framework for ExA-SPIM neuron reconstruction operations. It is built to ingest data from sources such as Smartsheet, S3, and local exports, normalize that data into a canonical document model, index it in a persistent local store, and answer questions with source attribution.

The current scaffold is production-oriented infrastructure rather than a finished domain model. It gives you:

- a read-only connector layer for Smartsheet, S3, and local JSON exports
- optional Microsoft Teams channel ingestion through Microsoft Graph
- a canonical ingestion pipeline that turns heterogeneous records into normalized documents and chunks
- a persistent SQLite-backed local knowledge store for deployment and offline testing
- a retrieval and synthesis layer with citations, fact separation, and traceability
- an MCP-style tool registry that exposes source search and targeted context lookup
- a FastAPI service and Typer CLI for ingestion, querying, and operations
- sample data and tests so the system runs before real credentials exist

The repository is now preconfigured with three ExA-SPIM Smartsheet source profiles:

- neuron reconstruction tracking
- specimen-level pipeline tracking
- manual registration tracking

By default the application will try to read the Smartsheet token from `CO_API/CO_ACCESS_TOKEN.txt` if `EXASPIM_SMARTSHEET_API_TOKEN` is not set.

## Architecture

The system is organized into five layers:

1. Connectors
   Read-only adapters that fetch records from approved systems. Current implementations:
   - `LocalJsonConnector` for local exports and testing
   - `SmartsheetConnector` for operational sheets
   - `TeamsConnector` for selected Microsoft Teams channels
   - `S3Connector` for manifests, logs, metadata, and text-like payloads

2. Normalization and ingestion
   Raw records are converted into a canonical `NormalizedDocument` model with stable identifiers, metadata, entity keys, and provenance. Documents are then chunked for retrieval and stored locally.

3. Index and retrieval
   Chunks are persisted in SQLite. Retrieval currently uses a deterministic keyword-plus-entity scoring layer so the project is usable before embeddings or external LLM credentials are configured.

4. Query and tool orchestration
   The query service returns:
   - direct answer text
   - extracted facts
   - derived metrics
   - inferred observations
   - citations and supporting chunks

   A tool registry provides an MCP-style execution surface for search and entity context lookup.

5. API and CLI
   The same application services are exposed through FastAPI and a local CLI.

## Quick Start

Create a virtual environment and install the package:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Copy the example environment file if you want to override defaults:

```bash
cp .env.example .env
```

Ingest the sample dataset:

```bash
exaspim-agent ingest
```

Run a local query:

```bash
exaspim-agent query "Which samples have completed annotation but not reconstruction?"
```

Start the API:

```bash
exaspim-agent serve
```

The API will be available at `http://127.0.0.1:8000` and interactive docs at `/docs`.

## API Endpoints

- `GET /health`
- `GET /sources`
- `GET /tools`
- `POST /ingest`
- `POST /query`
- `POST /tools/{tool_name}`

## Real Integration Plan

When you provide credentials later, the main steps are:

1. Smartsheet
   - either set `EXASPIM_SMARTSHEET_API_TOKEN` or place the token in `CO_API/CO_ACCESS_TOKEN.txt`
   - the three current sheet profiles are already configured by Smartsheet permalink
   - optionally override them with `EXASPIM_SMARTSHEET_SHEETS` as a JSON array
   - the connector preserves row hierarchy, important operational columns, and raw Smartsheet format strings

### Smartsheet Modeling Notes

- Parent and child rows are preserved through `parent_row_id`, `is_child_row`, and parent context merged into the indexed document.
- The connector extracts key fields such as specimen or sample id, genotype, status, manually estimated soma compartment, CCF soma compartment, registration status, imaging notes, and neuroglancer links when present.
- Raw cell `format` strings are also stored in metadata so color-coded cues, such as reporter conventions, are not lost during ingestion.

2. S3
   - set `EXASPIM_S3_BUCKET`
   - set `EXASPIM_S3_PREFIXES`
   - configure AWS auth in the runtime environment with read-only IAM permissions
   - install extras: `pip install -e ".[aws]"`

3. Microsoft Teams
   - create or reuse an Azure app registration for Microsoft Graph
   - set `EXASPIM_TEAMS_TENANT_ID`
   - set `EXASPIM_TEAMS_CLIENT_ID`
   - set `EXASPIM_TEAMS_CLIENT_SECRET` or `EXASPIM_TEAMS_TOKEN_FILE`
   - set `EXASPIM_TEAMS_CHANNELS` to a JSON array of team/channel targets
   - the connector uses app-only client-credentials auth and ingests selected channels in read-only mode

   Example:

   ```json
   [
     {
       "key": "ops_updates",
       "team_name": "Neuron Reconstruction Ops",
       "channel_name": "Announcements",
       "include_replies": true
     }
   ]
   ```

   A ready-to-edit example lives at [teams_channels.example.json](/Users/peter.grotz/Documents/ExM_Reconstructions_Project_Agent/data/sample/teams_channels.example.json).

   Recommended Microsoft Graph permissions:
   - `Team.ReadBasic.All`
   - `Channel.ReadBasic.All`
   - `ChannelMessage.Read.All`

   Official docs:
   - https://learn.microsoft.com/en-us/graph/api/teams-list?view=graph-rest-1.0
   - https://learn.microsoft.com/en-us/graph/api/channel-list-messages?view=graph-rest-1.0
   - https://learn.microsoft.com/en-us/graph/teams-changenotifications-chatmessage

4. Optional external LLM
   - set `EXASPIM_OPENAI_API_KEY`
   - install extras: `pip install -e ".[llm]"`
   - wire a responder implementation that calls your preferred model

## Security Model

- All connectors are implemented as read-only adapters.
- The system stores only local analytical artifacts in `exports/`.
- No code path writes back to Smartsheet, S3, or any operational source.
- Credentials are read from environment variables and not persisted into the document store.

## Deployment Notes

- The included `Dockerfile` builds a simple API image.
- The local SQLite file is mounted under `exports/` for persistence.
- For enterprise deployment, move the SQLite layer to a managed database or vector store when data scale requires it. The connector and query interfaces are already separated enough to support that upgrade.

## Repository Layout

```text
src/exaspim_agent/
  api/
  application/
  connectors/
  domain/
  indexing/
  llm/
  storage/
data/sample/
tests/
```
