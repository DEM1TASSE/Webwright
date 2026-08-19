# shopping_admin candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `catalog`

- `shopping_admin/catalog/list_catalog_products_by_quantity_range_from_admin_grid` — Retrieve product records from the shopping admin catalog products grid filtered by inventory quantity range.
  - Owns: Navigate to the shopping admin catalog product grid page, Authenticate to the admin site when the login form is presented, Open the grid's Filters UI and populate the quantity range filter fields, Apply the site filter and wait for filtered grid results, Parse typed product records from the rendered grid table, including stable displayed fields demonstrated by the workflow, Return the records visible in the filtered grid page
  - Does not own: Choosing the business-relevant quantity range for a particular task, Further post-filtering rows client-side beyond the site filter, Reducing records to only SKU values, Proving that no matching products exist outside the currently acquired grid page, Cross-page pagination traversal or full-result exhaustion
  - Evidence workflows: task187_t368

### `customers`

- `shopping_admin/customers/filter_customers_by_billing_phone_in_admin_grid` — Filter the Magento admin customer grid by billing phone number and return typed customer rows visible in the filtered result set.
  - Owns: Navigating to the Magento admin customers grid, Authenticating to the admin site when a login form is presented, Clearing saved active customer filters in the grid when the UI exposes a Clear all control, Opening the Filters panel if needed, Filling the billing telephone filter field, Applying the filter through the site UI, Reading visible grid rows and parsing row text into typed customer records with name, email, and matched phone
  - Does not own: Choosing which phone number to search for, Ranking or selecting among multiple returned customers beyond preserving visible row order, Proving site-wide absence beyond the currently acquired filtered grid result slice, Returning raw DOM or page text without parsing
  - Evidence workflows: task209_t364

### `orders`

- `shopping_admin/orders/get_recent_dashboard_orders` — Retrieve the recent orders listed in the shopping admin dashboard's Last Orders table as typed order summary records.
  - Owns: Read the current authenticated shopping admin page content, Locate the dashboard's Last Orders table on the current page, Parse the displayed rows of the Last Orders widget into typed records, Return the recent-order summaries exactly as exposed by that dashboard widget, including item counts and order-view links
  - Does not own: Authenticating to the shopping admin site as a separate reusable capability, Navigating to the dashboard page, Computing aggregates such as the sum of items across returned orders, Choosing that exactly 5 rows should answer a downstream business question beyond the widget's displayed slice, Ranking, filtering, or interpreting orders beyond preserving dashboard order, Navigating into each order detail page
  - Evidence workflows: task130_t1002
- `shopping_admin/orders/list_orders_from_admin_orders_grid_page` — Extract typed order records from the shopping admin orders grid currently displayed on the admin sales order page.
  - Owns: Navigate to the shopping admin orders grid page URL after authentication, Read the visible HTML table rows from the admin orders grid, Parse each row's table cells into a typed order record using stable column positions demonstrated by the workflow, Return objective fields exposed by the grid such as order identifier, purchase date, status, row position, and row cell texts
  - Does not own: Logging into the site as a standalone reusable capability beyond what is necessary for this page access, Determining which status is task-relevant (for example canceled only), Computing recency or selecting the most recent order, Paginating beyond the currently displayed grid page, Proving that no matching orders exist site-wide or across all pages
  - Evidence workflows: task202_t366

### `reviews`

- `shopping_admin/reviews/export_product_review_report_csv` — Export the shopping admin product review report as typed rows for a caller-supplied date range.
  - Owns: Navigate to the shopping admin product review report page, Fill the report's date filter fields for created_at[from] and created_at[to], Submit the report search/filter action, Read the site-generated export URL from the report export control after filters are applied, Request the export from the site's own export endpoint within the authenticated admin session, Parse the returned CSV into typed report rows
  - Does not own: Authenticating to the admin site as a standalone reusable capability, Choosing which date range answers a business question, Aggregating row counts into a final answer such as summing Reviews, Interpreting whether returned rows are acceptable for a particular task beyond exposing their fields, Formatting the answer for the user
  - Evidence workflows: task345_t248
- `shopping_admin/reviews/get_admin_reviews_total_count_via_http_session` — retrieve the total number of review records shown by the shopping admin All Reviews page using an authenticated admin HTTP session
  - Owns: establishing an authenticated admin HTTP session using the site's login form and cookies, submitting site-specific admin credentials to the /admin login endpoint, requesting the site-local All Reviews admin page at /admin/review/product/index/, parsing the returned HTML page text to extract the typed total review record count from the pager phrase '<n> records found', returning the resolved reviews page URL and HTTP status alongside the typed count
  - Does not own: deciding that the business question should be answered using review records rather than some other admin metric, formatting screenshots or final answer artifacts, returning raw HTML/page text as the primary product, proving that no reviews exist beyond what the page's displayed total states
  - Evidence workflows: task347_t248
- `shopping_admin/reviews/get_pending_review_grid_summary` — retrieve the Magento admin Pending Reviews grid total count from the shopping admin site after authenticating
  - Owns: Magento admin login session establishment using the site's login form and hidden form_key, navigation to the site's Pending Reviews admin page, parsing the Pending Reviews page HTML to extract the typed grid total count from the reviewGrid-total-count element
  - Does not own: choosing that only Pending reviews are relevant to the user task beyond using the demonstrated Pending Reviews page URL, formatting the count as the final answer payload, general raw HTML export or arbitrary page scraping outside this page's demonstrated summary element
  - Evidence workflows: task77_t277
- `shopping_admin/reviews/get_product_review_details` — Open one or more shopping admin review detail pages and extract typed review details from stable review form controls using either review URLs or review ids.
  - Owns: Authenticate with the admin login form when the sign-in page is shown, Navigate to one or more shopping admin review detail pages identified by caller-supplied review URLs or review ids, Read stable review form fields from each loaded review detail page, Return typed detail records including page URL and observed HTTP status
  - Does not own: Discovering which reviews to inspect, Determining sentiment or dissatisfaction from review text, Mutating reviews or saving edits, Proving that missing or unparsable ids do not exist site-wide
  - Evidence workflows: task123_t250, task112_t245, task120_t250
- `shopping_admin/reviews/get_review_grid_record_count_by_status` — Retrieve the site-reported record count from the shopping admin product reviews grid after applying a caller-supplied review status filter.
  - Owns: Navigate to the shopping admin reviews grid page, Authenticate with the admin login form when the sign-in page is shown, Apply the reviews-grid status dropdown filter using a caller-supplied status label, Submit the grid search/filter action, Read the grid header/body summary text and parse the site-reported '<n> records found' count into a typed integer
  - Does not own: Choosing which review status is relevant to the caller's task, Computing aggregates beyond the single filtered count, Returning raw page text or DOM instead of the parsed count
  - Evidence workflows: task78_t277, task79_t277
- `shopping_admin/reviews/list_reviews_by_created_date_range_from_reviews_grid` — Retrieve review records visible in the shopping admin reviews grid after applying a created-date range filter.
  - Owns: Navigate to the shopping admin product reviews grid, Use admin-session-authenticated page access to the reviews grid, Fill the grid's created date from/to filter inputs, Submit the grid search, Parse typed review-grid row records visible after filtering, Return the displayed post-filter summary count as an objective site field alongside the records
  - Does not own: Choosing the business period of interest such as May 2023, Computing a workflow-level answer by counting records instead of using the site's displayed total, Aggregating across multiple separate filter runs, Returning raw DOM or full page text
  - Evidence workflows: task348_t248
- `shopping_admin/reviews/search_product_reviews_by_product_name` — Search the shopping admin product reviews grid by product name and return typed current-page review grid records together with review edit handles found on the filtered page.
  - Owns: Navigate to the shopping admin product reviews grid, Authenticate with the admin login form when the sign-in page is shown, Fill the product-name filter field and submit the grid search, Read visible review-grid rows from the filtered current page, Extract stable row-level fields exposed in the grid including displayed product name, ordered cell texts, and Edit-link review detail URLs when present, Return both typed current-page row records and review edit handles for downstream detail retrieval
  - Does not own: Opening each review detail page, Classifying sentiment or dissatisfaction, Combining results across multiple grid pages, Proving that no matching reviews exist site-wide
  - Evidence workflows: task123_t250, task112_t245

## Approval

Review only. Editing generated package.py invalidates its hash.
