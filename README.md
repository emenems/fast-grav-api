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

### Single timestamp

```bash
curl -X POST "http://localhost:8000/tides/corrections?unit=ugal" \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 48.8,
    "lon": 17.7,
    "alt": 113.0,
    "date_times": ["2025-05-05T07:47:25Z"]
  }'
```

### Multiple timestamps (survey data)

```bash
curl -X POST "http://localhost:8000/tides/corrections?unit=ugal" \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 48.8,
    "lon": 17.7,
    "alt": 113.0,
    "date_times": [
      "2025-05-05T07:47:25Z",
      "2025-05-05T07:48:35Z",
      "2025-05-05T08:19:14Z"
    ]
  }'
```

Maximum 10 000 timestamps per request.

## Running tests

```bash
uv sync --group dev
uv run pytest
```
