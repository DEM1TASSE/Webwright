# map candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `core`

- `map/core/get_directions_summary` — retrieve directions summary between two places on the map site for a supported transport mode
  - Owns: navigating to the site's directions workflow, populating origin and destination route inputs, selecting a supported routing mode from the site's routing engine control, submitting the route query, waiting for the directions result page to render, parsing displayed distance and duration from the rendered summary, reading back the resolved origin, resolved destination, selected mode label, and result URL
  - Does not own: choosing which places to compare for a user task, repeating queries over many origin/destination pairs, ranking or comparing multiple routes beyond what one rendered result shows, discovering business ownership or candidate destinations, formatting the final natural-language answer
  - Evidence workflows: task155_t36, task766_t75
- `map/core/get_driving_route_summary` — Get driving directions summary between two locations on the map site's directions page.
  - Owns: Navigate to the site's directions page, Fill origin and destination direction fields, Submit the directions form, Wait for route results to render, Parse displayed route summary fields from the results page
  - Does not own: Choosing which destination candidate is nearest, Discovering gas stations or any POI search results, Comparing multiple destinations, Ranking or selecting among alternatives, Formatting a natural-language final answer
  - Evidence workflows: task237_t39
- `map/core/get_place_coordinates_from_place_detail` — Extract a place's geographic coordinates from a map site place-detail page.
  - Owns: Navigate to a map place-detail page on this site using a site-local detail path or already-open detail URL, Wait for the detail page heading identifying the place to load, Read the site's coordinate-bearing link or URL state from the detail page, Parse latitude and longitude into typed decimal-degree fields, Return the displayed place-identifying heading text when available as provenance
  - Does not own: Searching for which place to inspect from arbitrary user intent, Selecting the correct result among multiple search results, Cross-page orchestration from search page to chosen detail page, Formatting the final answer string for end-user response
  - Evidence workflows: task252_t46
- `map/core/get_place_details_from_result_page` — open a map place/detail page and extract typed place details including decimal-degree coordinates when displayed in the page content
  - Owns: Navigating to or operating on an existing place detail page on the map site, Reading displayed place-detail text from the page, Parsing the displayed Location field into typed latitude and longitude decimal-degree values, Returning the displayed coordinate representation alongside canonical numeric fields
  - Does not own: Finding the correct place via search query, Deciding which result page to open, Geocoding arbitrary free text outside the site's displayed place page, Inferring coordinates when the page does not display a parseable Location field
  - Evidence workflows: task250_t46
- `map/core/get_route_directions` — retrieve route directions and summary between two locations on the map site's directions page
  - Owns: Navigate to the map site's directions page using the current deployment origin, Fill the site's From and To routing inputs, Map supported semantic travel modes to the site's demonstrated mode labels, Submit the directions form, Wait for directions results to render, Parse displayed route summary fields including distance and time, Return the resolved origin and destination values displayed by the site, Return the result page URL
  - Does not own: Choosing which places to query, Inferring a person's hometown from external knowledge, Finding the closest matching business, Ranking or comparing multiple routes, Looping over many candidate destinations, Formatting the final natural-language answer
  - Evidence workflows: task139_t51, task152_t36, task763_t75
- `map/core/get_route_summary` — Retrieve a typed route summary between two caller-provided locations from the map site's directions workflow, including the site's resolved endpoints and displayed distance/time for supported travel modes.
  - Owns: Navigate to the site's directions page, Fill the site's From and To controls with caller-provided location text, Select a supported travel mode through the site's directions UI, Submit the directions request on the site, Wait for the rendered directions results to appear, Read the site's resolved endpoint values from the form after routing, Parse displayed route summary fields into typed distance and duration text
  - Does not own: Choosing which business or place is the nearest or otherwise task-relevant, Generating or iterating over multiple destination candidates, Ranking or comparing route results across repeated calls, Inferring subjective business attributes such as locally owned, Formatting a final natural-language answer
  - Evidence workflows: task100_t66, task767_t75, task138_t51, task222_t35
- `map/core/query_feature_coordinates_at_map_point` — Open the map context menu at a specified visible map point, invoke the site's Query features action, and return the queried point coordinates parsed from the resulting URL.
  - Owns: Map UI interaction to open the context menu at a rendered map location, Invoking the site-local 'Query features' action, Parsing latitude and longitude from the resulting map/query URL into typed numeric coordinates
  - Does not own: Choosing which real-world bus stop or landmark to click, Computer-vision or semantic grounding from a natural-language place description to screen coordinates, Ranking or filtering among multiple nearby stops, Formatting the final answer string
  - Evidence workflows: task251_t46
- `map/core/search_locations_by_text` — search map locations by free-text query and return typed location candidates
  - Owns: Submitting a site geocoder/search query on the map deployment, Applying site-local query parameters required for search execution, Parsing returned location candidates into typed records with coordinates and displayed name
  - Does not own: Choosing which user query to issue, Ranking candidates by external distance logic, Cross-query deduplication or semantic filtering beyond the issued query, Route computation between locations
  - Evidence workflows: task224_t35
- `map/core/search_places` — search the map site for a place or address and return typed place result records from the visible search results, including site-exposed coordinates when present
  - Owns: submitting a query through the site's search UI, waiting for search results to render in the site UI, parsing visible result entries into typed place records, reading site-exposed latitude/longitude attributes from result entries when present
  - Does not own: choosing which queries to issue for a user task, repeating searches over multiple caller-selected queries and comparing results across searches, deciding which result is closest or best, general geospatial reasoning beyond what the site explicitly shows, final answer formatting
  - Evidence workflows: task58_t69, task248_t46
- `map/core/search_places_by_text` — search the map site for places matching a text query and return typed candidate place records from the site's search results
  - Owns: Submitting a text query through the site's search UI, Capturing and parsing the site search results payload/HTML for result entries, Returning typed place candidate records with parsed coordinates and site-local detail link
  - Does not own: Choosing which query to search for, Ranking results by external criteria such as distance from an arbitrary caller-provided origin, Repeating searches over many queries, Computing nearest result client-side, Formatting a final answer
  - Evidence workflows: task223_t35

## Approval

Review only. Editing generated package.py invalidates its hash.
