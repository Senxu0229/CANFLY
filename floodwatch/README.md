# FloodWatch Maiduguri

Recovery tracking after the September 2024 Alau Dam failure, built on RADARSAT-2
radar passes. Helps an emergency or humanitarian coordinator **understand** where
water is still standing and **act**: rank places to send drainage, shelter or
farm support first, and hand the list to field teams.

Mission Accepted Space Hackathon 2026, Challenge 1.

## Run it

Needs Node 18+ and Python 3.

```bash
npm install
npm run dev          # opens http://localhost:5173
```

The repo ships with **mock data** in `public/data/` so the app runs before the
real processing is done. A dashed banner says so.

## Load the real GeoTIFFs

```bash
pip install -r scripts/requirements.txt
# copy the server's .tif files (and optional .geojson) into incoming/
npm run ingest:init  # drafts ingest.config.json from the file names; check it
npm run ingest       # converts everything into public/data/
npm run dev
```

The ingest reprojects UTM / web-mercator / lon-lat GeoTIFFs onto one grid, builds
the flood-duration map (the VAP), per-pass water and radar images, context layers
such as rainfall, and per-place statistics. Details and file naming:
`DATA_CONTRACT.md`.

`npm run mock-data` writes synthetic GeoTIFFs to `incoming_mock/` and runs the same
ingest, so the whole path is testable without the real data.

## Build for the demo

```bash
npm run build        # static site in dist/ (works from any folder, S3, GitHub Pages)
npx serve dist       # check the build locally; also the offline fallback
```

Background tiles (Esri imagery, OpenStreetMap) need internet. Everything else is
served from `public/data/`.

## What is on screen

| Area | Question it answers | Code |
|---|---|---|
| Top bar | How bad is it at this pass, better or worse than the last? | `KpiStrip.tsx` |
| Map, "How long it stayed flooded" | Where was hit hardest? (the VAP) | `MapView.tsx` |
| Map, radar image | What did RADARSAT-2 actually see? | `MapView.tsx` |
| Context data | Rainfall (or any other dataset) for the same dates | `LayerPanel.tsx` |
| Timeline of passes | How did the water recede? Play it, or swipe between two passes | `PassStrip.tsx` |
| Where to act first | Which places first, for my team's priorities? | `PriorityPanel.tsx`, `analysis.ts` |
| Place detail | What is happening here, when will it be dry, how much rain fell? | `PlacePanel.tsx` |
| Export | KML for phones offline, CSV, GeoJSON | `exporters.ts` |

## Stack

Vite + React + TypeScript, MapLibre GL JS (no API key). Python ingest needs only
numpy, Pillow and scipy (no GDAL install). No backend: the app reads static files,
so a failed server or network at demo time cannot break it.
