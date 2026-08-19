# map candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `places`

- `map/places/search_places` — search the map deployment's place-search backend by free-text query and return typed place candidates with the lossless union of objectively evidenced backend fields
  - Owns: Constructing the site-local search request to the map deployment's place-search backend with caller-supplied query text, Fetching and parsing the JSON search response, Returning typed place candidate records with stable displayed label, coordinates, identity/location metadata, and address details when present, Applying the demonstrated result limit parameter as part of this site's search request shape
  - Does not own: Choosing task-specific query text such as business names, categories, or landmarks, Selecting the best candidate for a task from among returned results, Inferring whether a result satisfies a category, jurisdiction, or relevance criterion beyond what the site returns, Computing routes or travel times, Combining or comparing results from multiple distinct queries
  - Evidence workflows: task37_t77, task152_t36, task73_t70, task85_t64

### `routes`

- `map/routes/get_route_summary` — submit origin and destination place queries on the map site's directions page, request an evidenced semantic travel mode, and parse the displayed route summary with optional caller-supplied destination fallbacks
  - Owns: Navigating to the site's directions page, Filling the From and To textboxes with caller-supplied location strings, Selecting a supported transport mode through a semantic mode input internally mapped to the site's controls, Submitting the directions form through the site's Go control, Waiting for the directions results view to render, Reading the site's displayed route summary text and parsing distance/time fields, Returning resolved origin and destination values as displayed by the site when observable, Optionally retrying caller-supplied destination fallbacks using the same site directions workflow
  - Does not own: Choosing which origin or destination strings to compare for a task, Generating fallback synonyms automatically, Ranking multiple successful routes across separate calls, Applying task thresholds such as one hour or five minutes, Formatting a final natural-language answer
  - Evidence workflows: task39_t77, task84_t64, task52_t68, task83_t72
- `map/routes/get_route_summary_by_coordinates` — retrieve a route summary between two coordinates from the map deployment using an evidenced supported travel mode and return typed route facts from the appropriate site response surface
  - Owns: Constructing the site's evidenced coordinate-to-coordinate route request for supported semantic travel modes, Hiding coupled engine/path details behind a semantic travel_mode enum, Fetching typed route data from the deployment's routing surfaces used by the map site, Parsing objective duration and distance facts from the returned response surface, Preserving waypoint metadata for car routes when present and displayed page summary text for walking routes
  - Does not own: Geocoding place names into coordinates, Choosing which origin/destination pairs to compare, Ranking multiple route results across separate calls, Formatting duration or distance into a final answer string, Applying task-specific thresholds such as 'within one hour' or 'at most 5 minutes'
  - Evidence workflows: task152_t36, task218_t41, task100_t66

## Approval

Review only. Editing generated package.py invalidates its hash.
