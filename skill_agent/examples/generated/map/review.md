# map candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `route`

- `map/route/get_osrm_route` — Request an OSRM route for an ordered list of two or more coordinates and return typed route summary and per-leg records from a leg-detailed response.
  - Owns: OSRM route endpoint shape with semicolon-separated coordinate path segments, Route request parameters overview=false and steps=true, Parsing route summary fields and per-leg duration and distance from the first returned route
  - Does not own: Geocoding place names into coordinates, Choosing which travel mode service or stop order to use for a task, Summing route durations across separate calls or selecting the best candidate route
  - Evidence workflows: task81_t72, task85_t64, task76_t65

### `search`

- `map/search/geocode_search_query` — Search a Nominatim geocoding service for a free-text place query and return typed location match records.
  - Owns: Nominatim search endpoint shape and query parameters, URL encoding of free-text queries, Parsing geocoding result fields exposed by the service
  - Does not own: Choosing which query strings to search, Assessing whether returned matches are semantically correct for a task, Any downstream routing, ranking, or aggregation across locations
  - Evidence workflows: task81_t72, task85_t64, task76_t65

## Approval

Review only. Editing generated package.py invalidates its hash.
