# Solar Power Forecast

Fetches hourly weather forecasts and historical data from [Open-Meteo](https://open-meteo.com) and estimates the power output of a single-row garden-mounted solar PV array.

- **`solar_forecast.py`** — forecast for today and tomorrow (prints an ASCII chart)
- **`solar_history.py`** — historical production model for any 30-day window (writes `solar_history.json`)

**No API key or login required** — Open-Meteo is a free, open-source service.

---

## System configuration

| Parameter | Value |
|---|---|
| Location | Uzhgorod, Ukraine (48.621°N, 22.288°E) |
| Peak power | 9 kW (two strings, ESE and SSE; modelled as one SE plane) |
| Panel orientation | South-east (azimuth –45°) |
| Panel tilt | 45° |
| Performance ratio | 0.85 (inverter losses, wiring, soiling, mismatch) |
| Temperature coefficient | –0.4 %/°C (standard c-Si) |
| Inverter max input | 9 kW (Deye `pv_power` setting) |
| Morning shading | Building ESE; clears at sun azimuth ~112° (string 1) / ~126° (string 2) |

---

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python solar_forecast.py
```

### Sample output

```
==============================================================================
  Solar Power Forecast — Uzhgorod, Ukraine
  9 kW south-east array, tilt 45°  |  Performance ratio: 85%  |  Temp coeff: -0.4%/°C
==============================================================================

TODAY — Wednesday, 2026-06-04
──────────────────────────────────────────────────────────────────────────────
   Hour      GTI  Cloud    Temp     Power  Chart (0–9 kW)
──────────────────────────────────────────────────────────────────────────────
  05:00       38    20%   13.5°C    0.18 kW  
  06:00      210    15%   14.2°C    1.02 kW  ████
  07:00      480    10%   15.8°C    2.24 kW  ██████████
  ...
  13:00      820     5%   24.0°C    5.28 kW  ████████████████
  ...
  20:00       18    55%   20.1°C    0.08 kW  
──────────────────────────────────────────────────────────────────────────────
  Total: 38.2 kWh  |  Peak: 5.92 kW at 13:00  |  Sunshine: 13h 10m
```

---

## Power model

```
cell_temp     = ambient_temp + 25°C          (simplified NOCT model)
temp_factor   = 1 + (−0.004) × (cell_temp − 25)
dc_power      = GTI (W/m²) ÷ 1000 × 9 kW × 0.85 × temp_factor
shade_factor  = shading_factor(solar_azimuth)  (morning ESE obstruction)
ac_power      = min(dc_power × shade_factor, 9 kW inverter limit)
Energy (kWh)  = Power (kW) × 1 h
```

`global_tilted_irradiance` (GTI) is computed by Open-Meteo for the exact panel angle and orientation — no manual geometric correction needed.

**Performance ratio (0.85)** was fitted on 2026-09-12 against Home Assistant recorder statistics (uncurtailed clear hours, Aug 14–Sep 11). The product `PEAK_KW × PERFORMANCE_RATIO ≈ 7.7 kW` is fixed; 9.0 / 0.85 is one consistent split. If the real panel nameplate total is known, adjust `PEAK_KW` and recalculate PR = 7.7 / PEAK_KW.

**Shading factor** models a building shadow to the ESE that clears when the sun's azimuth passes ~112° (string 1) and ~126° (string 2). While shaded, output is ~20% of expected (diffuse light). This is exact for Aug–Sep but will over-shade in summer and under-shade in winter; re-measure in December and June to add an elevation term.

The array is two strings facing different directions (ESE ~44%, SSE ~56%); azimuth –45° is the single-plane approximation.
