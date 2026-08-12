# map candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `geocoding`

- `map/geocoding/search_local_geocoder_results` — Submit a query to the map site's session-backed local geocoder endpoint and parse typed place results from the returned HTML snippet.
  - Owns: Initializing the site search workflow needed for session and CSRF state, Extracting CSRF metadata from the site's search page, Submitting a POST request to /geocoder/search_osm_nominatim with viewport bounds and query, Parsing structured place attributes embedded in returned HTML anchors, Returning typed local-search result records with names, category labels, and coordinates
  - Does not own: Choosing which search terms to try for a task, Filtering results by city or interpreting categories subjectively, Computing distances or selecting the closest result, Aggregating across multiple independent queries, Formatting final user responses
  - Evidence workflows: task58_t69
- `map/geocoding/search_places` — Search the map site's configured Nominatim geocoding service with a free-text query and return ordered typed place candidates.
  - Owns: Constructing requests to the site's configured Nominatim /search endpoint, Sending free-text geocoding queries with caller-specified limit and response format, Parsing JSON geocoding responses into typed ordered place candidate records, Preserving stable place identity, display, classification, bounding-box, and coordinate fields returned by the service, Returning explicit non-exhaustive completeness metadata for ranked limited results
  - Does not own: Choosing which candidate best matches a user task, Task-specific query rewriting or synonym selection, Computing distances, proximity, or routing, Applying business-specific filters such as nearest Walmart or restaurant, Formatting final user-facing answers
  - Evidence workflows: task154_t36, task37_t77, task75_t65, task155_t36, task58_t69, task39_t77, task59_t69

### `routing`

- `map/routing/get_route` — Request a route from the map site's OSRM-compatible service for an ordered waypoint sequence and return typed route summaries and waypoint metadata, supporting both the site's default driving endpoint and caller-specified endpoint/profile configuration.
  - Owns: Constructing OSRM-compatible route requests from ordered coordinates, Calling the site's default or caller-specified OSRM-compatible route endpoint, Passing through stable request options such as overview, steps, annotations, geometries, and alternatives, Parsing route-level summary metrics returned by the service, Preserving returned route order and top-level response code, Parsing snapped waypoint metadata returned by the service, Returning endpoint configuration and exact request URL for traceability
  - Does not own: Geocoding place names into coordinates, Inferring transport mode from task intent, Choosing waypoint order to optimize a task, Applying thresholds such as within one hour, Selecting among candidate routes for task-specific reasoning, Formatting final user-facing answers
  - Evidence workflows: task154_t36, task37_t77, task75_t65, task52_t68, task16_t73

## Approval

Review only. Editing generated package.py invalidates its hash.
