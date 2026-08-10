# map candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `places`

- `map/places/search_places` — Search the site's demonstrated Nominatim geocoding service for one free-text place query and return ordered typed place candidates with stable identity, coordinates, and display metadata exposed by the service.
  - Owns: Constructing the site's demonstrated Nominatim search request for a free-text query, Calling the demonstrated geocoding endpoint and parsing JSON results, Returning ordered geocoding candidates exactly as objective service results, Preserving stable identity/display/coordinate metadata exposed by the service, Owning the requested result limit for the service call
  - Does not own: Choosing which query strings to search for a task, Selecting the semantically correct candidate for a specific user intent, Combining geocoding with routing or multi-step trip logic, Aggregating durations or formatting final answer strings
  - Evidence workflows: task81_t72, task85_t64, task76_t65

### `routes`

- `map/routes/get_osrm_route` — Request a route from the site's demonstrated OSRM service for an ordered list of waypoint coordinates and a supported profile endpoint, returning typed route summaries and leg metrics from the service response.
  - Owns: Constructing the demonstrated OSRM route request for ordered longitude/latitude waypoints, Mapping supported site-discovered routing profiles to their endpoint ports, Calling the routing service and parsing route summary JSON, Returning total route duration/distance and per-leg duration/distance when exposed, Preserving request metadata and ordered waypoint inputs needed to interpret the response
  - Does not own: Geocoding free-text locations into coordinates, Enumerating or ranking multiple candidate stop orders, Summing durations across separate route calls for a task answer, Formatting seconds into HH:MM:SS strings
  - Evidence workflows: task81_t72, task85_t64, task76_t65

## Approval

Review only. Editing generated package.py invalidates its hash.
