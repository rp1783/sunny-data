# Comma Stats Findings for `sunny-data`

Date: 2026-05-24

## Context

`sunny-data` is running on Ryan's Unraid server (`Tower`) and syncs Comma recordings into the Unraid `Recordings` share.

Current deployed container:

- Container: `sunny-data`
- Image: `sunny-data:v6`
- Host port: `8082`
- Recordings mount: `/mnt/user/Recordings` -> `/recordings`
- App data mount: `/mnt/user/appdata/sunny-data` -> `/app/data`

## Unraid recording share

Share path:

```text
/mnt/user/Recordings
```

Observed top-level structure:

```text
/mnt/user/Recordings/
  realdata/
  stitched/
```

The Comma recordings are stored in the flat segment layout, not nested session folders:

```text
/mnt/user/Recordings/realdata/00000000--e8e9b1e3c0--0/
/mnt/user/Recordings/realdata/00000000--e8e9b1e3c0--1/
...
```

This matches the existing `sunny-data` code path for flat session grouping.

## Recording inventory

Observed summary:

- Segment directories: `113`
- Sessions: `9`
- Every segment contains:
  - `ecamera.hevc`
  - `fcamera.hevc`
  - `qcamera.ts`
  - `qlog.zst`
  - `rlog.zst`

Observed file counts and approximate total sizes:

```text
ecamera.hevc: 113 files, ~4.0 GB
fcamera.hevc: 113 files, ~4.0 GB
qcamera.ts:   113 files, ~249 MB
qlog.zst:     113 files, ~52 MB
rlog.zst:     113 files, ~1.33 GB
```

Sample segment:

```text
/mnt/user/Recordings/realdata/00000000--e8e9b1e3c0--0
  ecamera.hevc  36 MB
  fcamera.hevc  35 MB
  qcamera.ts    2.3 MB
  qlog.zst      436 KB
  rlog.zst      12 MB
```

## Important parser finding

The logs appear to be from **sunnypilot**, not stock commaai/openpilot.

Observed log metadata included:

```text
origin: github.com/sunnypilot/openpilot
branch: release-mici
version: 2026.001.006
device: mici
```

This matters because `sunny-data` should not assume vanilla commaai/openpilot schemas. A stats parser should use schemas compatible with `sunnypilot/openpilot` for the relevant branch/version, or otherwise handle schema drift carefully.

## Current container dependency state

Inside the deployed `sunny-data` container, the required parsing dependencies are not currently installed:

```text
capnp: false
zstandard: false
cereal/openpilot: false
```

Current `requirements.txt` is minimal and does not include Comma log parsing support.

## Stats that should be extractable

Because every segment includes both `qlog.zst` and `rlog.zst`, the app should be able to extract useful drive stats.

Likely basic stats:

- Total distance driven
- Average speed
- Max speed
- Drive start/end time
- GPS start point
- GPS end point
- Route polyline / map path

Likely openpilot/sunnypilot stats:

- Openpilot enabled time
- Disengagement count
- Alert/warning counts
- Car/platform metadata
- Hard braking / acceleration events, depending on available signals

Recommended source preference:

1. Use `qlog.zst` first for card-level and summary stats because it is much smaller.
2. Use `rlog.zst` only when deeper detail is required.

## Implementation recommendation

### 1. Add parser dependencies

Add to `requirements.txt`:

```text
zstandard
pycapnp
```

Additional schema/source packaging is still needed. The cleanest option is likely one of:

- vendor the matching `sunnypilot/openpilot` cereal `.capnp` schemas, or
- install/use a pinned sunnypilot/openpilot parser source compatible with `release-mici`.

A quick local parser prototype using downloaded schemas hit a `pycapnp` schema parse issue around `safetyModel`, so avoid adding a brittle one-off parser without a proper compatibility pass.

### 2. Add backend stats module

Create:

```text
app/comma_stats.py
```

Responsibilities:

- scan flat session segment directories
- find `qlog.zst` / `rlog.zst`
- parse relevant cereal events
- tolerate missing/corrupt logs
- produce one summary stats object per session

Potential event/message types to evaluate:

- `carState`
- `gpsLocationExternal`
- `controlsState`
- `deviceState`
- other sunnypilot-specific messages if useful

### 3. Cache parsed stats

Do not parse logs on every page load.

Recommended cache file:

```text
/app/data/stats_cache.json
```

Cache key should account for:

- session ID
- segment count
- `qlog.zst` / `rlog.zst` file sizes
- `qlog.zst` / `rlog.zst` mtimes
- parser version

This allows incremental parsing after sync and avoids repeatedly reading large logs.

### 4. Expose stats through API

Extend `GET /api/recordings` so each session can include a compact stats object:

```json
{
  "session": "00000000--e8e9b1e3c0",
  "duration_min": 14,
  "stats": {
    "distance_miles": 14.8,
    "avg_speed_mph": 41.2,
    "max_speed_mph": 68.4,
    "openpilot_active_min": 12.5,
    "disengagements": 1
  }
}
```

Optionally add a dedicated detailed endpoint later:

```text
GET /api/recordings/{session}/stats
```

### 5. Update the frontend

Update `app/static/app.js` and `app/static/style.css` to show stats in:

- recording cards
- recording modal
- possibly date-group summaries

Card example:

```text
24 min · 14.8 mi · avg 41 mph
```

Modal example:

```text
Distance: 14.8 mi
Max speed: 68 mph
Avg speed: 41 mph
Openpilot active: 12.5 min
Disengagements: 1
```

### 6. Hook stats into sync

Current sync flow is effectively:

```text
rsync
stitch sessions
cleanup old sessions
```

Recommended new flow:

```text
rsync
update stats cache
stitch sessions
cleanup old sessions
```

Stats could also run after stitching; the key point is that it should happen after successful rsync and before/around UI refresh.

## Testing plan

Add tests for:

- flat layout session grouping still works with `qlog.zst` / `rlog.zst`
- stats parser handles missing logs
- stats parser handles corrupt logs
- cache invalidation on file size/mtime changes
- `/api/recordings` includes `stats` when available
- `/api/recordings` still works when stats are unavailable

If real log fixtures are too large for the repository, use tiny synthetic fixtures or mock parser outputs in unit tests.

## Main risks / unknowns

1. **Schema compatibility**
   - Logs are from sunnypilot `release-mici`, so parser schemas need to match or be tolerant of drift.

2. **Dependency weight**
   - `pycapnp` may require build/runtime considerations in the Docker image.

3. **Performance**
   - `rlog.zst` files are much larger than `qlog.zst`; parsing should be cached and preferably use `qlog.zst` for summaries.

4. **Privacy**
   - GPS route data is sensitive. If route maps or coordinates are displayed, consider whether to expose full location data in the UI by default.

## Bottom line

The needed data is already present in the Unraid `Recordings` share. The app needs a sunnypilot-compatible log parser, a stats cache, API wiring, and frontend display components. Basic distance/speed stats should be achievable once the parser compatibility issue is solved; richer openpilot-active/disengagement stats can be layered on after that.
