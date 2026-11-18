import os
from dotenv import load_dotenv
import asyncio
import logging
import os
import re
import sys
import time
from functools import wraps
from dotenv import load_dotenv
import pandas as pd
import httpx
from mcp.server.fastmcp import FastMCP


load_dotenv()
mcp = FastMCP("indian-railways")


RAILRADAR_BASE = "https://api.railradar.in/v1"
RAILRADAR_API_KEY = os.environ.get("RAILRADAR_API_KEY")



# ───────────── capping: the most the LLM will ever see ─────────────
MAX_TRAINS = 5      # trains in a list
MAX_STOPS = 20      # halts in a timetable


def _code(value: str) -> str:
    """Station codes / train numbers go into the URL, so allow only safe characters."""
    v = (value or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{1,10}", v):
        raise ValueError(f"invalid code: {value!r}")
    return v


async def _get(path: str, params: dict | None = None):
    """Call RailRadar. Returns (data, None) on success or (None, {"error": ...}) on failure."""
    params = {k: v for k, v in (params or {}).items() if v}   # drop empty params
    try:
        payload = await _call_api(f"{RAILRADAR_BASE}{path}", params or None)
    except Exception as e:
        return None, {"error": f"network error: {type(e).__name__}"}
    if "error" in payload or not payload.get("success"):
        return None, {"error": str(payload.get("error"))[:200]}
    return payload["data"], None


# ───────────── tools ─────────────
@mcp.tool()
async def travel_to(source: str, destination: str, date: str | None = None,
                    train_type: str | None = None):
    """Find trains between two stations. source/destination are station CODES (e.g. ANG, BAP).
    date: YYYY-MM-DD, optional. train_type: optional, e.g. rajdhani, superfast, express, passenger."""
    data, err = await _get(f"/trains/between/{_code(source)}/{_code(destination)}",
                           {"date": date, "type": train_type})
    if err:
        return err
    trains = data.get("trains", [])
    return {
        "total_trains": data.get("count", len(trains)),
        "shown": min(len(trains), MAX_TRAINS),
        "trains": [
            {
                "number": t["train"]["number"],
                "name": t["train"]["name"],
                "runDays": t["train"].get("runDays"),
                "departure": t.get("from", {}).get("departure"),
                "arrival": t.get("to", {}).get("arrival"),
                "duration_min": t.get("duration"),
            }
            for t in trains[:MAX_TRAINS]
        ],
    }


@mcp.tool()
async def get_train_timetable(train_number: str):
    """Timetable of a train: source, destination, running days and its halts with times."""
    data, err = await _get(f"/trains/{_code(train_number)}", {"haltsOnly": "true"})
    if err:
        return err
    train, route = data.get("train", {}), data.get("route", [])
    return {
        "number": train.get("number"),
        "name": train.get("name"),
        "from": train.get("source", {}).get("name"),
        "to": train.get("destination", {}).get("name"),
        "runDays": train.get("runDays"),
        "total_halts": len(route),
        "halts": [
            {"station": r["station"]["code"], "arrival": r.get("arrival"),
             "departure": r.get("departure"), "platform": r.get("platform")}
            for r in route[:MAX_STOPS]
        ],
    }


@mcp.tool()
async def get_live_status(train_number: str, date: str | None = None):
    """Live running status of a train: delay in minutes, last halt and next halt.
    date: journey start date YYYY-MM-DD, optional (default: current run)."""
    data, err = await _get(f"/trains/{_code(train_number)}/live", {"date": date})
    if err:
        return err
    loc = data.get("currentLocation") or {}
    return {
        "train": f'{data.get("trainNumber")} {data.get("trainName")}',
        "status": data.get("status"),
        "delay_min": data.get("delayMinutes"),
        "last_updated": data.get("lastUpdatedAt"),
        "current": {"station": loc.get("stationCode"), "state": loc.get("status")},
        "previous_halt": (data.get("previousHalt") or {}).get("stationName"),
        "next_halt": (data.get("nextHalt") or {}).get("stationName"),
        "alerts": [e.get("message") for e in (data.get("exceptions") or [])[:2]],
    }


@mcp.tool()
async def get_station_live_board(station_code: str, hours: int = 4):
    """Live arrivals and departures at a station for the next `hours` hours (2, 4, 6 or 8)."""
    if hours not in (2, 4, 6, 8):
        return {"error": "hours must be 2, 4, 6 or 8"}
    data, err = await _get(f"/stations/{_code(station_code)}/live", {"hours": hours})
    if err:
        return err
    trains = data.get("trains", [])
    return {
        "station": data.get("station", {}).get("name"),
        "total_trains": data.get("count", len(trains)),
        "trains": [
            {
                "number": t["train"]["number"],
                "name": t["train"]["name"],
                "arrival": t.get("stop", {}).get("arrival"),
                "departure": t.get("stop", {}).get("departure"),
                "state": t.get("live", {}).get("type"),
                "platform": t.get("live", {}).get("platform"),
                "delay_min": t.get("live", {}).get("delayMinutes"),
            }
            for t in trains[:8]
        ],
    }


@mcp.tool()
async def get_station_schedule(station_code: str):
    """Scheduled (not live) trains that stop at a station, with arrival and departure times."""
    data, err = await _get(f"/stations/{_code(station_code)}/trains")
    if err:
        return err
    trains = data.get("trains", [])
    return {
        "station": data.get("station", {}).get("name"),
        "total_trains": data.get("count", len(trains)),
        "trains": [
            {"number": t["train"]["number"], "name": t["train"]["name"],
             "arrival": t.get("stop", {}).get("arrival"),
             "departure": t.get("stop", {}).get("departure")}
            for t in trains[:MAX_TRAINS * 2]
        ],
    }


@mcp.tool()
async def get_coach_layout(train_number: str):
    """Coach order of a train (e.g. ENG-H1-A1-B1-S1...) and how many coaches of each class."""
    data, err = await _get(f"/trains/{_code(train_number)}/coaches")
    if err:
        return err
    return {
        "train": f'{data.get("trainNumber")} {data.get("trainName")}',
        "formation": data.get("baseFormation"),
        "total_coaches": data.get("totalCoaches"),
        "class_counts": data.get("summary"),
        "engine_reverses_at": data.get("reversals"),
    }


@mcp.tool()
async def get_coach_position(train_number: str, station_code: str):
    """Coach order of a train as it stands on the platform at one station."""
    data, err = await _get(f"/trains/{_code(train_number)}/coaches/{_code(station_code)}")
    if err:
        return err
    return {
        "station": data.get("stationName"),
        "platform": data.get("platform"),
        "direction": data.get("direction"),
        "formation": data.get("formation"),
    }
    
    

if __name__ == "__main__":
    mcp.run()