# map candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `places`

- `map/places/search_places` — search the map site's single place-search resource for one free-text query and return ordered typed place candidates with backend-backed identity and coordinates, plus same-query UI link fields when objectively exposed by rendered result anchors
  - Owns: Calling the site-backed place search endpoint discovered from the deployment's own assets/configuration, Encoding one caller-supplied free-text query into the site's request format, Fetching JSON search results from the map site's search backend, Parsing each returned search result into typed place candidate records with stable identity and coordinates, Optionally enriching backend candidates with href/url/name fields only when the same query's rendered UI result anchors objectively expose matching coordinates, Preserving site-returned backend rank order within the single query result slice
  - Does not own: Choosing which user query or query family to issue, Looping over multiple queries, Task-specific filtering or preference logic, Cross-query merge or deduplication, Nearest/all decision logic, Routing or travel-time computation
  - Evidence workflows: task37_t77, task152_t36, task100_t66, task369_t52

### `routes`

- `map/routes/get_route_by_coordinates` — load the map site's directions page for one origin/destination coordinate pair and one supported travel mode, then return the displayed route summary fields and parsed duration when present
  - Owns: Constructing the demonstrated directions-page request for origin and destination coordinates with one supported site routing engine, Loading the site's directions page for that route, Reading displayed page text from the route page, Parsing the displayed route summary into typed distance and travel-time fields when present, Parsing displayed travel time into canonical seconds when the displayed text is unambiguous, Returning the final directions page URL used for the route
  - Does not own: Selecting the origin or destination place for the task, Geocoding arbitrary place names unless provided separately, Interpreting whether the displayed travel time satisfies a user threshold such as within one hour, Comparing multiple routes or transport modes, Guaranteeing that a route exists for all coordinate pairs
  - Evidence workflows: task37_t77, task85_t64, task218_t41
- `map/routes/get_route_summary` — submit a single directions query through the map site's directions UI for one origin, one destination, and one supported travel mode, then return the displayed route summary, resolved endpoints, selected mode value, and parsed duration when available
  - Owns: Navigating to the site's directions page on the current deployment, Filling one origin and one destination into the site's directions UI, Selecting one supported semantic travel mode and mapping it internally to the site's coupled engine labels, Submitting the directions request through the visible UI, Reading rendered route-summary text from the sidebar, summary paragraph, or page body, Parsing displayed distance and travel-time fields when present, Parsing displayed travel time into canonical seconds when the format is unambiguous and source-demonstrated, Returning submitted queries, resolved endpoint text, selected mode value, and final directions URL
  - Does not own: Choosing which origin and destination to query, Looping over multiple routes or fallback destinations, Task-specific threshold checks such as within one hour, Ranking or deduplicating multiple destinations, General place search outside what this single route submission resolves
  - Evidence workflows: task39_t77, task84_t64, task52_t68, task83_t72, task87_t64

## Approval

Review only. Editing generated package.py invalidates its hash.
