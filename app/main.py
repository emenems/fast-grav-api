from fastapi import FastAPI

from app.routers import tides

app = FastAPI(
    title="Geodey & Gravity Corrections API",
    description="REST endpoints for computing geophysical various corrections.",
    version="0.1.0",
    license_info={"name": "MIT"},
)

app.include_router(tides.router)


@app.get("/health", tags=["Meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
