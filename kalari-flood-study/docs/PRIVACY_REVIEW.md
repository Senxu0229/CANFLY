# Privacy review for the GitHub upload

Reviewed 3 October 2026. Scope: the files included in this study folder and its final upload archive. The existing CANFLY repository and the rest of the original workspace are outside this audit.

## Included content

The report, charts, aggregate flood measurements, geographic footprints, approximate public village location, analysis scripts, method notes, source filenames and file hashes. No individual or household records are included. Public source URLs and attribution remain intact.

## Excluded from the upload

- The optional local browser report, which embedded a Codex chat identifier and unnecessary app runtime code.
- macOS Finder `.DS_Store` files, caches, bytecode, virtual environments and local tool configuration.
- The original GDB archive, source PDF, source XLSX, satellite imagery and unrelated workspace documents.

## Checks performed

- Text review and pattern scans for common API/access tokens, private keys, passwords, signed URLs, credential-bearing URLs, email addresses and personal filesystem paths.
- Review of CSV/JSON/GeoJSON fields for individual identities, private person locations, contact details and account data.
- Review of PNG and SVG metadata; only plotting-tool metadata and chart descriptions were found.
- Checks for symlinks, hidden files, unexpected archive members, broken report links and source-file fingerprint mismatches.
- Recalculation of the final package checksums and verification that ZIP contents match the reviewed folder.

No credentials, personal records or private identifiers were detected in the prepared upload. Geographic coordinates describe a public village and mapped flood areas, not an individual's location. These checks do not guarantee detection of every possible secret format; they document the scope and results of the review. This privacy review does not determine third-party data licensing rights.
