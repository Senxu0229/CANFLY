# Verification record

Prepared 3 October 2026.

- Reran the optional extraction from the original downloaded GDB. All 12 source CSV rows and all 6 GeoJSON feature contents matched the prior extraction exactly. See `extraction_validation.json`.
- The analysis pipeline passed 85 arithmetic and geometry checks. Source area differences were below 0.000000007 km²; projected versus ellipsoidal area differences were below 0.01%. See `../data/validation.json` for exact scope and checks.
- Rebuilding the derived data from a different working directory produced identical outputs.
- Independently checked the 6.68 km² spatial union and the mid-September shared/new/no-longer-mapped areas.
- Compared report tables, percentage changes, headline metrics and units with the CSV/JSON outputs.
- Visually inspected both PNG figures. Labels, period dates, geographic scales, study circles, north indication, scale bar and no-detection note were present and readable.
- Checked Python syntax, relative Markdown links, preserved-source SHA-256 fingerprints and browser-build hashes.
- The Markdown report and exported figures are the verified presentation outputs. The optional local browser version is excluded from this upload package.

These checks verify computation and presentation within the supplied evidence. They do not validate the satellite classifications on the ground, prove complete coverage or establish physical/economic damage.
