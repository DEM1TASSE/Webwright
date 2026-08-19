# shopping candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `auth`

- `shopping/auth/authenticate_customer_session_via_form_key` — authenticate to the shopping site as a customer via the site login form flow and establish a reusable authenticated browser session for downstream customer-account requests
  - Owns: Fetching the customer login page, Extracting the hidden Magento form_key from the login HTML, Submitting customer credentials to the site's login POST endpoint with required form_key and referer, Persisting authenticated cookies for subsequent browser or request-based site access on the same page context, Verifying authenticated state by loading the customer account page and checking for a signed-in indicator
  - Does not own: Fetching or parsing order history records, Selecting credentials, Exposing raw form_key values, cookies, or other authentication secrets, Task-specific reporting or answer formatting
  - Evidence workflows: task47_t197, task48_t197

### `catalog`

- `shopping/catalog/multi_search_products_graphql_dedup_by_sku` — issue multiple product catalog searches on the shopping site and merge deduplicated product records by SKU
  - Owns: Accepting several caller-supplied search queries for the same site GraphQL products search, Looping over those queries and issuing one site request per query, Merging hits across searches, Deduplicating products by stable SKU identity, Preserving the richest demonstrated typed product fields from the site response for each deduplicated product, Building canonical product URLs from site-local url_key and url_suffix fields
  - Does not own: Choosing which query strings to use for a particular task, Applying brand or category decisions such as whether a title is in-scope or an accessory, Computing derived aggregates like minimum/maximum price range, Ranking, filtering, or final answer formatting beyond the site's own search behavior, Proving no matching product exists site-wide beyond the supplied query set and per-query slice
  - Evidence workflows: task126_t159, task230_t370

### `orders`

- `shopping/orders/get_customer_order_detail` — Retrieve a customer's order-detail page and parse typed order detail fields and line-item names
  - Owns: Navigating to a site order-detail URL for a supplied order identifier, Parsing displayed order metadata from the page text, Parsing visible product name cells from the order items table when present, Falling back to regex extraction of product names from page text when the table cells are unavailable
  - Does not own: Choosing which order identifiers to inspect, Classifying items or orders as food/non-food, Summing totals across orders, Filtering by status or date for the final task answer
  - Evidence workflows: task144_t162
- `shopping/orders/list_authenticated_customer_orders_graphql` — retrieve authenticated customer order records from the shopping site's GraphQL API using site-local customer authentication, with either one requested page or complete traversal across all reported pages
  - Owns: Authenticating to the site's GraphQL customer API via generateCustomerToken as an internal prerequisite, Issuing authenticated customer.orders GraphQL requests to the site-local /graphql endpoint, Supporting either one requested page or complete traversal across all site-reported pages through a semantic retrieval_mode enum, Applying the site's order-number match filter when supplied, Parsing customer identity, pagination metadata, and stable order fields into typed records, Preserving the union of evidenced order fields across overlapping GraphQL order candidates
  - Does not own: Choosing which order number filter to use for a particular task, Filtering by task-specific statuses or dates beyond the site's own query parameters, Ranking or selecting a final answer, Exposing raw bearer tokens
  - Evidence workflows: task359_t206, task189_t214, task188_t214, task331_t147
- `shopping/orders/list_customer_orders_history_page` — List typed order summary records from the signed-in customer's orders-history page
  - Owns: Navigating to the site's orders history page after authentication, Parsing the orders table rows into typed order summary records from displayed cells, Preserving the demonstrated stable displayed row fields for order identity, date, addressee, and total text
  - Does not own: Logging in, Filtering by date range, Determining whether an order is food-related, Selecting specific target orders beyond what appears on the page, Traversing pagination beyond the demonstrated page
  - Evidence workflows: task144_t162
- `shopping/orders/list_order_history_page_html` — retrieve one authenticated customer order-history page and parse visible order-summary rows from its HTML into typed records
  - Owns: Requesting the authenticated order history page using an existing signed-in session, Parsing visible order table rows from the page HTML, Normalizing stable displayed order fields into typed records, Including machine-readable date and numeric amount parses when supported by the displayed values
  - Does not own: Logging in, Applying task-specific date windows or status filters, Summing totals or formatting answers, Claiming records beyond the single fetched order-history page
  - Evidence workflows: task47_t197, task48_t197

### `reviews`

- `shopping/reviews/extract_product_review_texts_from_product_page` — extract structured review text records from a shopping product page by opening the Reviews tab and parsing review content elements
  - Owns: Navigating to a product detail page on the shopping site, Opening the product page's Reviews tab via the site's UI, Reading the reviews section text from the rendered page, Parsing each rendered .review-content element into a typed review text record
  - Does not own: Classifying which review sentences are criticisms, Filtering out shipping or delivery complaints, Selecting only negative statements, Summarizing or formatting the final answer
  - Evidence workflows: task164_t136

## Approval

Review only. Editing generated package.py invalidates its hash.
