# core-lens API

Querying API for [core-lens](https://github.com/ApoorvaKashyap/core-lens), exposing GeoParquet-backed
entity data over REST and GraphQL from one FastAPI process.

## Architecture

- **FastAPI** is the HTTP server. It mounts two things: a REST router and a Strawberry GraphQL router
  (`GraphQLRouter` is itself a FastAPI `APIRouter`, so GraphQL rides on top of FastAPI rather than
  replacing it).
- **Strawberry** (`strawberry-graphql`) implements the GraphQL layer — one endpoint
  (`/graphql/v1`) where clients ask for exactly the fields they want instead of hitting many
  fixed REST routes.
- **core-lens** reads the actual GeoParquet files. This repo never touches parquet files directly —
  it calls `core_lens.entities.*` classes, which know how to scan/filter/paginate against a
  `data_root` directory.
- On startup (`lifespan` in [main.py](main.py)), `generated.initialize()` peeks at each entity's
  parquet schema (footer only, no row data) and dynamically builds matching GraphQL types — so the
  schema tracks whatever columns actually exist in the data, rather than being hand-written.

## Data layout

Two independent data roots, because they're structured differently:

- **`DATA_ROOT`** — flat layout, one dataset per entity, used by MWS/Tehsil/Waterbody:
  ```
  <DATA_ROOT>/mws/{static,annual,sub-annual}.parquet
  <DATA_ROOT>/tehsil/static.parquet
  <DATA_ROOT>/waterbodies/{static,annual}.parquet
  <DATA_ROOT>/meta/mws_layer_version.csv
  ```
- **`FARM_DATA_ROOT`** — partitioned by state/district/block, one folder per block:
  ```
  <FARM_DATA_ROOT>/<state>/<district>/<block>/farms/{static,annual,sub_annual}.parquet
  ```
  A fresh `FarmEntity` is built per GraphQL request pointed at the specific block folder the
  caller asks for (see `resolve_farm_timeseries` in
  [src/app/graphql/resolvers.py](src/app/graphql/resolvers.py)) — there's no single flat farms
  dataset to scan, unlike the other three entities.

## Local development

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14 (see [.python-version](.python-version)).

```bash
uv sync                 # creates .venv, installs pinned deps from uv.lock
cp .env.example .env    # then edit DATA_ROOT / FARM_DATA_ROOT to point at real data
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Then:
- `http://localhost:8000/docs` — REST/Swagger
- `http://localhost:8000/graphql/v1` — GraphiQL
- `http://localhost:8000/api/v1/meta/health` — health check

Lint/typecheck before committing:
```bash
uv run ruff check .
uv run ruff format .
uv run mypy .
```

## Environment variables

| Variable | Used by | Meaning |
|---|---|---|
| `DATA_ROOT` | app | Root for MWS/Tehsil/Waterbody data (flat layout above). |
| `FARM_DATA_ROOT` | app | Root for partitioned farm boundary data. |
| `TEMP_PATH` | app | Scratch directory for working files. |
| `REDIS_HOST` / `REDIS_PORT` | app | Reserved, not yet used by any route. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` / `S3_BASE` | app | Reserved for cloud-backed data roots (`s3://...`), not yet used locally. |
| `DATA_ROOT_HOST` / `FARM_DATA_ROOT_HOST` | `docker compose` only | Host-side paths substituted into the bind mounts in `docker-compose.yml`. Not read by the Python app — see Docker section below. |
| `LOG_LEVEL` | `docker compose` only | Passed through as a container env var. |

## REST API

| Route | Description |
|---|---|
| `GET /api/v1/meta/active_tehsils` | Tehsils with `Algorithm Version > 1`, from `meta/mws_layer_version.csv`. |
| `GET /api/v1/meta/health` | `{"status": "ok", "data_root": ..., "farm_root": ...}` — use for container health checks / readiness probes. |

## GraphQL API

Endpoint: `POST /graphql/v1` (GraphiQL IDE available at the same URL in a browser).

```graphql
{
  mws(limit: 10, district: "Godda") {
    items { mwsId tehsil district state }
    totalCount
  }

  tehsils { tehsilId tehsil district state }

  waterbody { wbId district state }

  entities(filter: { coordinates: { latitude: 24.05, longitude: 85.05 } }) {
    mws
    tehsil
    waterbody
  }

  farmTimeseries(
    state: "rajasthan"
    district: "jaipur"
    block: "dudu"
    farmId: "rajasthan_jaipur_dudu_000000"
  ) {
    farmId
    annual { year maiAnnual kharifWaterStress }
    monthly { date mai }
  }
}
```

`farmTimeseries` returns empty `annual`/`monthly` lists (not an error) if `farmId` doesn't exist
under that state/district/block.

`geometry` fields (GeoJSON) are only decoded from the underlying WKB column when a query actually
selects them — omit `geometry` from a query if you don't need it, it's the expensive part.

## Docker

```bash
cp .env.example .env   # fill in DATA_ROOT_HOST / FARM_DATA_ROOT_HOST with real host paths
docker compose build
docker compose up
```

`docker-compose.yml` mounts `DATA_ROOT_HOST` and `FARM_DATA_ROOT_HOST` (host paths) read-only into
the container at `/data` and `/farm_data`, and sets the container's own `DATA_ROOT=/data` /
`FARM_DATA_ROOT=/farm_data` accordingly. The container owns no data — it only ever reads through
these mounts.

The Dockerfile runs `uv lock --upgrade-package core-lens` before installing, so every image build
picks up the latest published `core-lens` release regardless of what's pinned in `uv.lock` in git —
intentional, since core-lens is developed alongside this repo. Every other dependency stays locked
to `uv.lock` as normal.

### Running the built image directly (no compose)

```bash
docker run -d -p 8000:8000 \
  -v /path/to/data:/data:ro \
  -v /path/to/farm_boundaries:/farm_data:ro \
  -e DATA_ROOT=/data \
  -e FARM_DATA_ROOT=/farm_data \
  corelens-api
```

## Known gaps

- No automated tests yet.
- The `entities` point-lookup query intentionally excludes farms — farm boundaries are partitioned
  by state/district/block, so there's no single flat dataset to point-in-polygon scan against
  without already knowing which block to look in.
- `resolve_farm_timeseries`'s monthly-grain fetch bypasses `core-lens`'s own `view.sub_annual`
  resolution and scans the parquet directly — the sub-annual file carries both a `year` (int) and
  `date` (datetime) column, and core-lens's time-column auto-detection currently picks `year` first
  and misinterprets it as a date. Worth fixing upstream in core-lens.
