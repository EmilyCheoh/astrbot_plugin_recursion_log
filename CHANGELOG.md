## June 14

v2.0.0 — full restructure

- Replaced flat entry list with section-based structure (states, deltas, unresolved threads)
- Added per-section `enabled` toggle
- Added per-entry `enabled` toggle for recurring items
- Removed all `rs` chat commands — entry management moves to Web UI
- Removed `display_count` config (injection count now controlled by entry-level enabled flags)
- Removed `inject_entries` config toggle (use section/entry enabled flags instead)
- Updated injection formatting: sections displayed with display_name headers, empty sections skipped

## May 31

added in-tag footer
