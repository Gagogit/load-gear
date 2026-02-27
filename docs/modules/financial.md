# Module: Financial Service (P6 — Cost Calculation)
Schicht: B
Letzte Aktualisierung: 2026-02-27

## Responsibility

Calculate energy costs by multiplying forecast time series (v3) with
Hourly Price Forward Curves (HPFC). Produce cost time series and summaries.

## Core Operation

Vector scalar product per hour:

```
Total_cost[h] = Consumption[h] (kWh, from Prophet) × Price[h] (€/MWh, from HPFC)
```

Converted to €: `cost_eur[h] = (consumption_kwh[h] / 1000) * price_mwh[h]`

## HPFC Management

### Upload & Versioning

- Multiple providers supported (EPEXSpot, EEX, custom)
- Multiple snapshots per provider (versioned by `snapshot_at`)
- Default: use latest available snapshot covering the forecast horizon
- Override: specific `snapshot_id` can be passed in calculation request

### Dropzone (future)

Automated ingestion from email/FTP delivery:
- Dropzone watcher detects new files
- Validate via Polars
- Store in `data.hpfc_series` + `data.hpfc_snapshots`

## Input

- `data.forecast_series` — consumption forecast (from P5)
- `data.hpfc_series` — price curve (uploaded separately)
- Calculation parameters: forecast_id, snapshot_id (optional)

## Output

| Data | Destination |
|------|-------------|
| Cost time series | Response JSON (€/h per timestamp) |
| Monthly summaries | Response JSON (total €/month) |
| Export | CSV/Excel via /financial/{calc_id}/export |

## Future: Reverse Engine (ADR — not yet)

Bidirectional feedback: define constraints (e.g., "reduce peak by 15%")
and calculate savings. Not implemented in v0.1.
