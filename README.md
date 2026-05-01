# fast-grav-api

REST API for computing geophysical gravity corrections & transformations commonly used in geodesy, built with [FastAPI](https://fastapi.tiangolo.com/).

## Corrections available

| Correction | Endpoint | Method |
|---|---|---|
| Tidal gravity | `/tides/corrections` | Longman (1959), orbital constants after Bartels (1957), Love-number factor 1.16 |

Correction values are returned in the unit requested via the `unit` query parameter (`mgal`, `gal`, `ugal`, `nm_s2`). Default is `mgal`.

## Running locally

**Requirements:** [uv](https://docs.astral.sh/uv/)

```bash
uv sync
uv run fastapi dev app/main.py
```

The API is available at `http://localhost:8000`.  
Interactive docs (Swagger UI): `http://localhost:8000/docs`

## Example requests

See the interactive docs at `http://localhost:8000/docs` for full request/response schemas and a built-in try-it-out interface.

## Running tests

```bash
uv sync --group dev
uv run pytest
```
