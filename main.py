from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Astro Engine API")

class ChartRequest(BaseModel):
    date: str        # "1990-05-14"
    time: str        # "15:30"
    timezone: str    # "America/Toronto"
    lat: float       # 43.65
    lon: float       # -79.38

@app.get("/")
def health_check():
    return {"status": "ok"}

@app.post("/chart")
def chart(req: ChartRequest):
    """
    Temporary placeholder.
    After deployment, this endpoint will call the Swiss Ephemeris Web API.
    """
    return {
        "message": "Swiss Ephemeris not integrated yet",
        "input": req.model_dump()
    }
