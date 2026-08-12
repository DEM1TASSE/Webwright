# shopping candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `auth`

- `shopping/auth/login_customer_account` — Authenticate a customer account on the shopping site via the Magento customer login form and report whether the current browser session became authenticated.
  - Owns: Open the customer login page, Extract the Magento login form action URL and hidden form_key token, Submit username and password through the site login form, Determine whether the browser session became authenticated from resulting account page state
  - Does not own: Choosing which credentials to use, Navigating to orders, reviews, or products after login, Any downstream business filtering, aggregation, or final answer formatting
  - Evidence workflows: task143_t162, task322_t160

### `catalog`

- `shopping/catalog/search_products` — Search the shopping catalog and return typed product records from one or more paginated search-result pages.
  - Owns: Construct catalog search URLs from a free-text query, Fetch search result pages, Discover pagination pages from search-result HTML, Parse product result cards into typed records, Track fetched versus discovered pagination coverage
  - Does not own: Filtering results by brand-name containment or other task predicates, Computing aggregate statistics such as min/max price, Task-specific ranking, comparison, or final answer formatting
  - Evidence workflows: task230_t370

### `orders`

- `shopping/orders/get_order_detail` — Retrieve structured objective facts from an authenticated customer order detail page, including order identity, dates, status, displayed financial totals, line items shown on the page, and any displayed arrival or delivery date normalized when recoverable.
  - Owns: Open a specific authenticated order detail page, Parse displayed order identity, order date, and status facts when present, Parse line items shown on the detail page, Extract displayed subtotal, shipping and handling, and grand total amounts, Detect displayed arrival or delivery date text when present and normalize it to YYYY-MM-DD
  - Does not own: Choosing which order to inspect, Classifying items into semantic categories, Applying refund policy or exclusion rules, Aggregating across multiple orders, Inferring an arrival date when the page does not display one
  - Evidence workflows: task143_t162, task322_t160, task96_t193
- `shopping/orders/list_customer_order_history_page` — Retrieve structured order summary rows from one authenticated customer order-history page on the shopping site.
  - Owns: Open one authenticated customer order-history page, Parse order-history table rows that link to order detail pages, Extract stable displayed row fields and resolve order detail URLs, Represent completeness only for the fetched history page
  - Does not own: Authenticating the customer session, Searching across multiple pages for a target order, Filtering by date, status, or recency, Aggregating counts or spend across orders
  - Evidence workflows: task234_t213, task232_t213

### `reviews`

- `shopping/reviews/get_product_review_feed_metadata` — Fetch a shopping product detail page and extract stable review-feed metadata exposed in the product HTML.
  - Owns: Open a product detail page URL on the shopping site, Read product HTML for embedded review-source metadata, Extract the embedded product review feed URL when present, Extract the displayed review count when present, Return page title context from the product page when present
  - Does not own: Fetching or parsing the review feed response itself, Filtering reviews by rating or any other task-specific predicate, Interpreting review percentages into business thresholds, Formatting a final user answer
  - Evidence workflows: task165_t136
- `shopping/reviews/list_product_reviews` — Retrieve structured review records for a shopping product from the site's Magento review listing endpoint.
  - Owns: Construct the Magento review listing endpoint for a product, Fetch one review-list page from the site, Parse review items into typed review records, Return objective review fields including author, title, content, and rating when present
  - Does not own: Topic or sentiment classification such as customer-service complaints, Filtering reviews by task-specific predicates, Deduplicating or aggregating reviewer names across pages, Claiming whole-corpus completeness beyond the fetched page
  - Evidence workflows: task26_t222, task166_t136

## Approval

Review only. Editing generated package.py invalidates its hash.
