from fastapi import FastAPI

from app.routers import adjustment, conversion, tides, tranformation

app = FastAPI(
    title="Geodey & Gravity Corrections API",
    description="REST API for computing geophysical gravity corrections & transformations commonly used in geodesy.",
    version="0.1.0",
    license_info={"name": "MIT"},
)

app.include_router(tides.router)
app.include_router(conversion.router)
app.include_router(tranformation.router)
app.include_router(adjustment.router)


@app.get("/health", tags=["Meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
