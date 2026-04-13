# fast-grav-api

REST API for computing geophysical gravity corrections, built with [FastAPI](https://fastapi.tiangolo.com/).

## Corrections available

| Correction | Endpoints | Source |
|---|---|---|
| Tidal gravity (Longman 1959) | `/tides/corrections`, `/tides/series` | [LongmanTide](https://github.com/bradyzp/LongmanTide) |

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

### Arbitrary timestamps (survey data)

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

### Regular time series

```bash
curl -X POST "http://localhost:8000/tides/series" \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 48.8,
    "lon": 17.7,
    "alt": 113.0,
    "start_date_time": "2024-06-15T00:00:00Z",
    "end_date_time": "2024-06-15T23:00:00Z",
    "resolution_seconds": 3600
  }'
```

Both `start_date_time` and `end_date_time` are inclusive. Maximum 10 000 samples per request.
