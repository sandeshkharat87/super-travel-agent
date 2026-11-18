import json
import logging
import os
import re
from datetime import date as date_cls

import dotenv
import requests
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

dotenv.load_dotenv()

log = logging.getLogger(__name__)

# ---------------------------------------------------------------- city -> code
AIRPORTS = {
    "pune": "PNQ", "mumbai": "BOM", "delhi": "DEL", "bengaluru": "BLR",
    "chennai": "MAA", "kolkata": "CCU", "hyderabad": "HYD", "ahmedabad": "AMD",
    "goa": "GOI", "jaipur": "JAI", "nagpur": "NAG", "lucknow": "LKO",
    "kochi": "COK", "nashik": "ISK", "indore": "IDR", "bhopal": "BHO",
    "surat": "STV", "thiruvananthapuram": "TRV", "chandigarh": "IXC", "patna": "PAT",
}

STATIONS = {
    "pune": "PUNE", "mumbai": "CSMT", "delhi": "NDLS", "bengaluru": "SBC",
    "chennai": "MAS", "kolkata": "HWH", "hyderabad": "SC", "ahmedabad": "ADI",
    "goa": "MAO", "jaipur": "JP", "nagpur": "NGP", "lucknow": "LKO",
    "nashik": "NK", "indore": "INDB", "bhopal": "BPL", "surat": "ST",
}

ALIASES = {
    "bangalore": "bengaluru", "bombay": "mumbai", "new delhi": "delhi",
    "calcutta": "kolkata", "madras": "chennai", "trivandrum": "thiruvananthapuram",
    "panaji": "goa", "madgaon": "goa",
}


def _norm(name: str) -> str:
    n = re.sub(r"\s+", " ", name.strip().lower())
    return ALIASES.get(n, n)


def to_iata(name: str):
    n = _norm(name)
    if n in AIRPORTS:
        return AIRPORTS[n]
    s = name.strip()
    return s.upper() if re.fullmatch(r"[A-Za-z]{3}", s) else None


def to_station(name: str):
    n = _norm(name)
    if n in STATIONS:
        return STATIONS[n]
    s = name.strip()
    return s.upper() if re.fullmatch(r"[A-Z]{2,5}", s) else None


def _get(d, *keys):
    """Walk nested dicts that may contain None."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


# @@@ Train tools  ----------------------------------------------------------------------- train
_RAIL_BASE = "https://api.railradar.in/v1"


@tool
def search_train(source: str, destination: str, date: str = "") -> str:
    """Search trains between two Indian cities or stations.

    Args:
        source: Origin city (e.g. "Pune") or station code (e.g. "PUNE").
        destination: Destination city (e.g. "Mumbai") or station code (e.g. "CSMT").
        date: Optional date in YYYY-MM-DD format; defaults to today.

    Returns train numbers and names. This tool only searches; it never books tickets.
    """
    src, dst = to_station(source), to_station(destination)
    if not src or not dst:
        return (f"Couldn't find a railway station for '{source}' or '{destination}'. "
                "Ask the user for the station code.")
    date = date or date_cls.today().isoformat()
    try:
        r = requests.get(
            f"{_RAIL_BASE}/trains/between/{src}/{dst}",
            headers={"Authorization": f"Bearer {os.getenv('RAILRADAR_API_KEY', '')}"},
            params={"date": date},
            timeout=15,
        )
        r.raise_for_status()
        trains = r.json()["data"]["trains"][:5]
        if not trains:
            return f"No trains found from {src} to {dst} on {date}."
        # Extend with departure/arrival fields once you've inspected a real response.
        return json.dumps(
            [{"number": t["train"]["number"], "name": t["train"]["name"]} for t in trains]
        )
    except Exception as e:
        log.warning("train search failed: %s", type(e).__name__)
        return f"Train search failed for {src}->{dst} ({type(e).__name__})."


@tool
def train_get_live_status(train_number: str, date: str | None = None):
  """Live running status of a train: delay in minutes, last halt and next halt.

  date: journey start date YYYY-MM-DD, optional (default: current run).
  """
  date = date or date_cls.today().isoformat()
  train_number = train_number.strip()

  try:
    r = requests.get(
        f"{_RAIL_BASE}/trains/{train_number}/live",
        headers={"Authorization": f"Bearer {os.getenv('RAILRADAR_API_KEY', '')}"},
        params={"date": date},
        timeout=15,
    )
    r.raise_for_status()
    payload = r.json().get("data", {})

    return {
        "trainNumber": payload.get("trainNumber"),
        "trainName": payload.get("trainName"),
        "status": payload.get("status"),
        "delayMinutes": payload.get("delayMinutes"),
        "currentLocation": payload.get("currentLocation"),
        "nextHalt": payload.get("nextHalt"),
        "route": payload.get("route", [])[:5],  # Limits to 5 entries
    }
  except Exception as e:
    print(e)
    return "Train search failed"
    



#END @@@ Train tools  ----------------------------------------------------------------------- train



#@@@ Bus tools ------------------------------------------------------------------------- bus
@tool
def search_buses(source: str, destination: str) -> str:
    """Search the web for bus options between two cities in India.

    Args:
        source: Origin city (e.g. "Pune").
        destination: Destination city (e.g. "Mumbai").

    Returns web results about bus operators, timings, fares and booking links.
    This tool only searches; it never books tickets.
    """
    query = f"{source} to {destination} bus operators timings fare booking"
    try:
        data = TavilySearch(max_results=3).invoke({"query": query})
        results = data.get("results", []) if isinstance(data, dict) else data
        if not results:
            return f"No web results found for buses from {source} to {destination}."
        return "\n\n".join(
            f"{r.get('title', '')}\n{r.get('url', '')}\n{(r.get('content') or '')[:300]}"
            for r in results
        )
    except Exception as e:
        log.warning("bus search failed: %s", type(e).__name__)
        return f"Bus search failed for {source}->{destination} ({type(e).__name__})."


#END @@@ Bus tools ------------------------------------------------------------------------- bus


#@@@ Flight tools ---------------------------------------------------------------------- flight
# Free plan only supports HTTP. On a paid plan, switch to https.
_AVIATION_BASE = os.getenv("AVIATIONSTACK_BASE", "http://api.aviationstack.com/v1")


@tool
def search_flights(source: str, destination: str, limit: int = 3) -> str:
    """Search current/recent flights between two Indian cities or airports.

    Args:
        source: Departure city (e.g. "Pune") or IATA code (e.g. "PNQ").
        destination: Arrival city (e.g. "Delhi") or IATA code (e.g. "DEL").
        limit: Max number of flights to return (default 3, max 10).

    Returns airline, flight number, status and scheduled times. Data is real-time or
    recent, not a future timetable. This tool only searches; it never books tickets.
    """
    src, dst = to_iata(source), to_iata(destination)
    if not src or not dst:
        return (f"Couldn't find an airport for '{source}' or '{destination}'. "
                "Ask the user for the airport code.")
    limit = max(1, min(limit, 10))
    try:
        r = requests.get(
            f"{_AVIATION_BASE}/flights",
            params={
                "access_key": os.getenv("AVIATIONSTACK_API_KEY", ""),
                "dep_iata": src,
                "arr_iata": dst,
                "limit": limit,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return f"Flight search failed: {_get(data, 'error', 'message') or 'API error'}"
        flights = [
            {
                "airline": _get(f, "airline", "name"),
                "flight": _get(f, "flight", "iata"),
                "status": f.get("flight_status"),
                "date": f.get("flight_date"),
                "from": _get(f, "departure", "airport"),
                "departure": _get(f, "departure", "scheduled"),
                "terminal": _get(f, "departure", "terminal"),
                "to": _get(f, "arrival", "airport"),
                "arrival": _get(f, "arrival", "scheduled"),
            }
            for f in data.get("data", [])
        ]
        if not flights:
            return f"No flights found from {src} to {dst}."
        return json.dumps(flights)
    except Exception as e:
        # Never include str(e): the URL (with access_key) is inside requests' messages.
        log.warning("flight search failed: %s", type(e).__name__)
        return f"Flight search failed for {src}->{dst} ({type(e).__name__})."

#END Flight tools ---------------------------------------------------------------------- flight
