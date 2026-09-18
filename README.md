# ExA-SPIM Operations Agent

This repository contains a deployable, read-only agent framework for ExA-SPIM neuron reconstruction operations. It is built to ingest data from sources such as Smartsheet, S3, and local exports, normalize that data into a canonical document model, index it in a persistent local store, and answer questions with source attribution.

The current scaffold is production-oriented infrastructure:

- a read-only connector layer for Smartsheet, S3, and local JSON exports
- optional Microsoft Teams channel ingestion through Microsoft Graph
- Code Ocean capsule and computation-outcome ingestion, plus live run-status and (opt-in) run-launch tools
- Neuron Morphology Community Portal (NMCP) specimen ingestion and a live read-only GraphQL query tool
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
   - `CodeOceanConnector` for capsule metadata and recent computation outcomes
   - `MorphologyPortalConnector` for portal specimens (label, id, soma count, genotype)

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

   A tool registry provides an MCP-style execution surface. Alongside the offline
   knowledge tools (`search_knowledge`, `get_entity_context`, `list_sources`) it can
   expose live tools when credentials resolve:
   - `code_ocean_run_status` — status of a computation, reduced to an honest verdict
   - `code_ocean_launch_run` — launch a computation (only when launching is enabled)
   - `morphology_portal_query` — read-only GraphQL against the portal

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

   A ready-to-edit example lives at [teams_channels.example.json](data/sample/teams_channels.example.json).

   Recommended Microsoft Graph permissions:
   - `Team.ReadBasic.All`
   - `Channel.ReadBasic.All`
   - `ChannelMessage.Read.All`

   Official docs:
   - https://learn.microsoft.com/en-us/graph/api/teams-list?view=graph-rest-1.0
   - https://learn.microsoft.com/en-us/graph/api/channel-list-messages?view=graph-rest-1.0
   - https://learn.microsoft.com/en-us/graph/teams-changenotifications-chatmessage

4. Code Ocean (AIND deployment)
   - provide the API token via `secrets/codeocean_api_token` (gitignored) or `EXASPIM_CODE_OCEAN_API_TOKEN`
   - list the capsules to index in `EXASPIM_CODE_OCEAN_CAPSULES` as a JSON array:

     ```json
     [{"key": "snapshot", "capsule_id": "<uuid>", "name": "Snapshot generation",
       "description": "Converts processed reconstruction assets into the portal layout"}]
     ```

   - the connector indexes capsule metadata and the most recent computations, tagging
     each run with a verdict; `code_ocean_run_status` reads a run live
   - launching is off by default. Set `EXASPIM_CODE_OCEAN_ALLOW_LAUNCH=true` only where
     spending compute is intended — this is the one tool that mutates the deployment
   - run status is judged from `state`, `end_status`, `exit_code`, and `has_results`
     together; `has_results == false` is treated as failure even when the other fields
     look like success, because a terminated machine has been observed to report
     completed / exit 0 / succeeded while syncing nothing

5. Neuron Morphology Community Portal (NMCP)
   - published specimens are visible anonymously; set `EXASPIM_MORPHOLOGY_PORTAL_API_TOKEN`
     or `secrets/nmcp_api_token` (gitignored) to reach private records
   - the connector indexes specimens (label, id, soma count, genotype); optionally scope
     to one collection with `EXASPIM_MORPHOLOGY_PORTAL_COLLECTION_FILTER`
   - `morphology_portal_query` runs read-only GraphQL. Portal mutations (createSpecimen,
     importSomas, deleteSpecimen) are intentionally *not* exposed as tools — they write
     to shared, user-visible data and belong with a human operator
   - auth is a raw `Authorization: <token>` header; `Bearer <token>` is silently ignored
     and leaves the caller anonymous

6. Optional external LLM
   - set `EXASPIM_OPENAI_API_KEY`
   - install extras: `pip install -e ".[llm]"`
   - wire a responder implementation that calls your preferred model

## Security Model

- Every connector is a read-only adapter, and the query and portal-query tools are
  read-only. The single exception is `code_ocean_launch_run`, which is off unless
  `EXASPIM_CODE_OCEAN_ALLOW_LAUNCH=true`; nothing writes back to Smartsheet, S3, Teams,
  or the morphology portal.
- Credentials are resolved at runtime from environment variables or gitignored token
  files, never from committed code, and never written into the document store, logs, or
  indexed records.
- Token files default to the gitignored `secrets/` directory (`secrets/codeocean_api_token`,
  `secrets/nmcp_api_token`). `.gitignore` also blocks `*_token`, `*_secret*`, `.env`, and
  related patterns as defense in depth.
- `.env.example` ships only empty placeholders; copy it to `.env` (gitignored) and fill
  in locally.
- The system stores only local analytical artifacts under `exports/`.

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
