from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from datetime import datetime
from dateutil import tz
from skyfield.api import load, wgs84
from math import atan2, degrees

app = FastAPI(title="Astro Engine API (Skyfield)")

# Load timescale & ephemeris (Skyfield downloads DE421 automatically)
ts = load.timescale()
eph = load('de421.bsp')

PLANET_KEYS = {
    "sun": "sun",
    "moon": "moon",
    "mercury": "mercury",
    "venus": "venus",
    "mars": "mars",
    "jupiter": "jupiter barycenter",
    "saturn": "saturn barycenter",
    "uranus": "uranus barycenter",
    "neptune": "neptune barycenter",
    "pluto": "pluto barycenter"
}

class ChartRequest(BaseModel):
    date: str
    time: str
    timezone: str
    lat: float
    lon: float

    @field_validator("date")
    @classmethod
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except:
            raise ValueError("date must be YYYY-MM-DD")

    @field_validator("time")
    @classmethod
    def validate_time(cls, v):
        try:
            datetime.strptime(v, "%H:%M")
            return v
        except:
            raise ValueError("time must be HH:MM")

@app.get("/")
def health_check():
    return {"status": "ok"}

def to_utc(dt_local, tz_name):
    local_zone = tz.gettz(tz_name)
    if local_zone is None:
        raise ValueError(f"Unknown timezone: {tz_name}")

    return dt_local.replace(tzinfo=local_zone).astimezone(tz.UTC)

def ecliptic_longitude(body, t, observer):
    """Compute ecliptic longitude from observer location."""
    astrometric = observer.at(t).observe(body)
    eclip = astrometric.ecliptic_position()
    x, y, z = eclip.km
    lon = (degrees(atan2(y, x)) + 360) % 360
    return lon

def compute_asc_mc(t, lat, lon):
    """Approximate ASC and MC for MVP."""
    # Local sidereal time (in degrees)
    lst_deg = t.gast * 15.0
    mc = lst_deg % 360
    asc = (lst_deg + 90) % 360
    return asc, mc

@app.post("/chart")
def chart(req: ChartRequest):
    # Build datetime
    try:
        dt_local = datetime.strptime(f"{req.date} {req.time}", "%Y-%m-%d %H:%M")
    except:
        raise HTTPException(status_code=400, detail="Invalid date/time")

    # Convert to UTC
    try:
        dt_utc = to_utc(dt_local, req.timezone)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Skyfield time
    t = ts.from_datetime(dt_utc)

    # Observer on Earth
    location = wgs84.latlon(req.lat, req.lon)
    observer = eph["earth"] + location

    # Compute planets
    planets = {}
    for name, key in PLANET_KEYS.items():
        body = eph[key]
        lon = ecliptic_longitude(body, t, observer)
        planets[name] = {"lon": lon}

    # Compute ASC & MC
    asc, mc = compute_asc_mc(t, req.lat, req.lon)

    return {
        "engine": "skyfield_de421",
        "input": req.model_dump(),
        "chart": {
            "asc": asc,
            "mc": mc,
            "planets": planets
        }
    }
