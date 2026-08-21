# shopping candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `catalog`

- `shopping/catalog/search_products_graphql` — Search the shopping site's product catalog through its GraphQL products endpoint and return typed product records with pricing and product URLs.
  - Owns: Issuing a single site GraphQL products search request with a caller-provided search term, Passing page-size configuration supported by the site request, Parsing the GraphQL response into typed product records, Returning stable product identity fields exposed by the site such as sku, Returning site product URL constructed from url_key and url_suffix on this deployment, Returning minimum-price regular and final price values with currency when present in the response
  - Does not own: Brand filtering such as keeping only titles that begin with Perricone MD, Any client-side inclusion/exclusion logic based on task-specific title rules, Computing aggregate statistics such as min/max price range across returned products, Looping over multiple search terms, Cross-query merge or deduplication, Answer formatting for end-user response
  - Evidence workflows: task230_t370, task126_t159

### `orders`

- `shopping/orders/get_order_detail` — Retrieve and parse a shopping-site order detail page into a typed order record when the page matches the demonstrated order-detail layout and exposes a single-word status token after the order number.
  - Owns: Navigate to a site order-detail URL by order_id, Read the order detail page content from the site, Parse order number from page text, Parse the demonstrated single-word status token when present immediately after the order number, Parse displayed order date text from page text, Parse displayed grand total text and canonical numeric amount from page text, Extract product/item names from order line items using the demonstrated table selector
  - Does not own: Choosing which order IDs to inspect, Date-range filtering, Determining whether an order should count toward a task result, Classifying items as food vs non-food, Aggregating totals across multiple orders, Proving that an order does not exist site-wide, Recovering item names through unsupported generic text fallbacks when the demonstrated selector is absent
  - Evidence workflows: task144_t162
- `shopping/orders/get_order_history_page` — authenticate to the shopping site and acquire the My Orders history page HTML for the signed-in account
  - Owns: Opening the login page at /customer/account/login/, Extracting the hidden form_key from the login page HTML, Submitting site login credentials to /customer/account/loginPost/ with the extracted form_key, Retaining authenticated cookies across requests, Fetching the authenticated My Orders page at /sales/order/history/, Returning the acquired orders page HTML and final URL/status for further site-specific parsing
  - Does not own: Parsing HTML rows into typed order records, Filtering orders by date range, Classifying which statuses count as fulfilled for the caller's task, Aggregating counts or monetary totals across orders, Formatting the final natural-language answer
  - Evidence workflows: task47_t197
- `shopping/orders/list_authenticated_customer_orders` — List the signed-in customer's order records from the shopping site via the site's authenticated GraphQL orders connection with pagination.
  - Owns: Authenticate a customer against the site-local Magento customer token endpoint using email and password, Call the site-local GraphQL customer orders query with a requested page number, Follow the site's pagination using page_info.total_pages when fetch_all_pages is true, Return typed order records with stable order number, order timestamp, status, and monetary total/currency as exposed by the site, Return customer identity fields included in the same GraphQL response, Return pagination metadata for the acquired page or full traversal
  - Does not own: Choosing which customer credentials to use, Filtering orders by month, store, or status for a task-specific answer, Summing totals across returned orders, Cross-query merging or deduplication across multiple unrelated searches, Rendering answer text or writing local files
  - Evidence workflows: task331_t147
- `shopping/orders/list_authenticated_customer_orders_graphql` — Authenticate a customer on the current shopping-site deployment through the site's GraphQL customer token flow and retrieve authenticated customer orders from the site's GraphQL API either as a single paginated page or using the site's native order-number match filter, preserving the evidenced union of customer, order, and pagination fields actually requested and parsed.
  - Owns: Authenticate the customer against the current shopping deployment using the evidenced GraphQL generateCustomerToken flow, Query the authenticated customer.orders GraphQL field on the same deployment, Use either the paginated customer.orders query or the site's native order-number match filter selected by semantic query_mode, Return customer identity fields exposed by the same GraphQL response, Return site-provided order collection metadata including total_count and page_info when present, Preserve the evidenced union of objective order fields actually requested and parsed across the overlapping GraphQL candidates: number, status, created_at when queried, order_date when queried, legacy grand_total when queried, and nested total.grand_total.value/currency
  - Does not own: Traversing all pages in a Python loop; workflows can call the atomic single-page primitive repeatedly, Authenticating through the separate REST token endpoint, Looping over multiple independent order-number searches, Filtering orders by task-specific date or status rules, Selecting a single order as the final answer, Aggregating spend or counts across multiple invocations, Formatting user-facing output
  - Evidence workflows: task359_t206, task189_t214
- `shopping/orders/list_customer_orders_page` — List the visible order-summary records shown on the authenticated customer's order history page.
  - Owns: Navigate to the site's customer order history page after authentication, Read the orders table rows rendered on the page, Parse each visible row into typed order-summary fields from the first four table cells as demonstrated
  - Does not own: Logging in with specific hard-coded credentials as a business task, Filtering by date range, Selecting specific order numbers, Determining whether an order is food-related, Summing totals across orders, Following pagination or proving all orders were retrieved across multiple pages
  - Evidence workflows: task144_t162
- `shopping/orders/list_orders_from_order_history_page` — parse typed order records from the shopping site's My Orders history page
  - Owns: Parsing each order table row from the My Orders page HTML, Extracting objective order fields exposed on the page: order identifier, displayed order date, displayed total amount, and displayed status, Normalizing displayed values into typed canonical fields where demonstrated: ISO calendar date and numeric amount, Returning one typed record per parsed order row from the acquired page
  - Does not own: Authenticating or navigating to the orders page, Choosing the date window of interest, Deciding which statuses should be treated as fulfilled beyond exposing the parsed status text, Summing totals or counting records, Proving account-wide absence beyond the acquired page if the site paginates history
  - Evidence workflows: task47_t197

### `reviews`

- `shopping/reviews/get_product_review_texts_from_reviews_tab` — Open a shopping product page's Reviews tab and extract the visible review body texts as a list of strings.
  - Owns: Navigate to a product detail page URL on the shopping site, Open the Reviews tab using the site's review-tab selector, Read the site's rendered review section text, Extract individual review body texts from `.review-content` elements in the reviews section
  - Does not own: Classifying which review sentences are criticisms, Filtering out shipping or delivery complaints, Summarizing or selecting only the main criticisms, Sentence-level extraction from review text beyond returning the raw review bodies, Any cross-product aggregation or ranking
  - Evidence workflows: task164_t136

## Approval

Review only. Editing generated package.py invalidates its hash.
