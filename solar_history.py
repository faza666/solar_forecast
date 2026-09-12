"""Historical solar power production estimate for the last 30 days.

Fetches hourly reanalysis weather data from the Open-Meteo archive API and
estimates what the rooftop PV system produced on each of the last 30 full
days (yesterday backwards). The result is written to solar_history.json
next to this script.

Site parameters and the power model are imported from solar_forecast.py so
both scripts always describe the same installation.

Open-Meteo is a free, no-auth API — no credentials needed.
"""
from __future__ import annotations

import json
import sys
from collections import OrderedDict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import requests

from solar_forecast import (
    AZIMUTH,
    LATITUDE,
    LONGITUDE,
    PEAK_KW,
    PERFORMANCE_RATIO,
    TEMP_COEFF,
    TILT,
    TIMEZONE,
    HourSlot,
)

HISTORY_DAYS = 30
OUTPUT_FILE = Path(__file__).with_name("solar_history.json")

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# ---------------------------------------------------------------------------
# API fetch
# ---------------------------------------------------------------------------

def fetch_history(start: date, end: date) -> List[HourSlot]:
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join([
            "global_tilted_irradiance",
            "temperature_2m",
            "cloud_cover",
            "sunshine_duration",
        ]),
        "tilt": TILT,
        "azimuth": AZIMUTH,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": TIMEZONE,
    }
    try:
        resp = requests.get(ARCHIVE_URL, params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"ERROR: Could not reach Open-Meteo archive API: {exc}", file=sys.stderr)
        sys.exit(1)

    raw = resp.json()
    hourly = raw["hourly"]

    slots: List[HourSlot] = []
    for i, ts in enumerate(hourly["time"]):
        slots.append(HourSlot(
            dt=datetime.fromisoformat(ts),
            gti=hourly["global_tilted_irradiance"][i] or 0.0,
            temp=hourly["temperature_2m"][i] or 0.0,
            cloud=hourly["cloud_cover"][i] or 0.0,
            sunshine=hourly["sunshine_duration"][i] or 0.0,
        ))
    return slots


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def _group_by_day(slots: List[HourSlot]) -> Dict[date, List[HourSlot]]:
    days: "OrderedDict[date, List[HourSlot]]" = OrderedDict()
    for s in slots:
        days.setdefault(s.dt.date(), []).append(s)
    return days


def _day_record(day: date, day_slots: List[HourSlot]) -> Dict[str, Any]:
    total_kwh = sum(s.energy_kwh for s in day_slots)
    peak = max(day_slots, key=lambda s: s.power_kw)
    sunshine = sum(s.sunshine for s in day_slots)
    # Average cloud cover over daylight hours only — night clouds don't matter
    daylight = [s for s in day_slots if s.gti > 0]
    avg_cloud = sum(s.cloud for s in daylight) / len(daylight) if daylight else 0.0

    return {
        "date": day.isoformat(),
        "weekday": day.strftime("%A"),
        "energy_kwh": round(total_kwh, 2),
        "peak_kw": peak.power_kw,
        "peak_time": peak.dt.strftime("%H:%M"),
        "avg_daylight_cloud_pct": round(avg_cloud, 1),
        "sunshine_seconds": int(sunshine),
        "hourly": [
            {
                "time": s.dt.isoformat(timespec="minutes"),
                "gti_wm2": s.gti,
                "cloud_pct": s.cloud,
                "temp_c": s.temp,
                "sunshine_seconds": int(s.sunshine),
                "power_kw": s.power_kw,
            }
            for s in day_slots
        ],
    }


def build_report(start: date, end: date, slots: List[HourSlot]) -> Dict[str, Any]:
    days = [_day_record(d, ds) for d, ds in _group_by_day(slots).items()]
    grand_kwh = sum(d["energy_kwh"] for d in days)
    best = max(days, key=lambda d: d["energy_kwh"]) if days else None

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": ARCHIVE_URL,
        "site": {
            "location": "Uzhgorod, Ukraine",
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "timezone": TIMEZONE,
            "peak_kw": PEAK_KW,
            "tilt_deg": TILT,
            "azimuth_deg": AZIMUTH,
            "performance_ratio": PERFORMANCE_RATIO,
            "temp_coeff_per_c": TEMP_COEFF,
        },
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": len(days),
        },
        "summary": {
            "total_kwh": round(grand_kwh, 2),
            "avg_kwh_per_day": round(grand_kwh / len(days), 2) if days else 0.0,
            "best_day": best["date"] if best else None,
            "best_day_kwh": best["energy_kwh"] if best else None,
        },
        "days": days,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=HISTORY_DAYS - 1)

    slots = fetch_history(start, end)
    if not slots:
        print("ERROR: No data available for the requested period.", file=sys.stderr)
        sys.exit(1)

    report = build_report(start, end, slots)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    s = report["summary"]
    print(f"Wrote {OUTPUT_FILE} - {report['period']['days']} days ({start} .. {end}), "
          f"{s['total_kwh']:.1f} kWh total, {s['avg_kwh_per_day']:.1f} kWh/day")


if __name__ == "__main__":
    main()
