# map candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `geocoding`

- `map/geocoding/search_local_geocoder_places` — Search the site's CSRF-protected local geocoder endpoint within a specified map view and return typed place candidates parsed from the HTML response.
  - Owns: Opening the site search page to establish session context and extract CSRF metadata required by the site's local geocoder workflow, Submitting a place query to the site's /geocoder/search_osm_nominatim endpoint with bounded map parameters and AJAX-style headers, Parsing returned HTML result anchors into typed place candidate records, Returning stable place fields actually exposed in the response, including category prefix, display name, and coordinates
  - Does not own: Choosing which search terms to try for a task, Ranking results by distance or relevance beyond preserving parsed response order, Computing distances between places, Filtering to cafes, restaurants, or city-specific subsets for task purposes, Aggregating across multiple different queries into one deduplicated answer set
  - Evidence workflows: task58_t69
- `map/geocoding/search_places` — Search the map site's configured Nominatim geocoding service with a free-text query and return typed place candidate records in service order.
  - Owns: Constructing the map site's configured Nominatim search request from a free-text query and result limit, Issuing the HTTP request to the site-coupled geocoding service, Parsing JSON geocoding candidates into typed place records, Returning stable objective fields exposed by the response, including identity metadata, coordinates, category/type, and importance
  - Does not own: Choosing which query text to use for a task, Selecting the intended candidate among ambiguous results, Applying task-specific filters such as only Walmarts, cafes, or restaurants, Computing distances, route feasibility, or route optimality, Formatting final user answers
  - Evidence workflows: task154_t36, task37_t77, task59_t69, task58_t69, task39_t77

### `routing`

- `map/routing/get_route` — Request a route between ordered coordinates from the map site's configured OSRM service for a supported transportation mode and return typed route summaries plus snapped waypoint metadata.
  - Owns: Constructing the site-configured OSRM route request from ordered waypoint coordinates, Resolving semantic transportation mode to the site's coupled OSRM deployment details internally, Issuing the HTTP request to the map site's routing service and parsing JSON, Returning typed route summaries including duration, distance, snapped waypoints, and leg/step records exposed by the response
  - Does not own: Geocoding text place queries into coordinates, Choosing which origin/destination candidates to route between, Applying task-specific threshold comparisons such as within one hour, Formatting durations into HH:MM:SS strings for final answers, Selecting the nearest destination or best candidate across multiple searched places
  - Evidence workflows: task154_t36, task75_t65, task221_t35, task52_t68

## Approval

Review only. Editing generated package.py invalidates its hash.
