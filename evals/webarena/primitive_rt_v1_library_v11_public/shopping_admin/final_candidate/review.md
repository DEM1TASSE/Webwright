# shopping_admin candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `auth`

- `shopping_admin/auth/login_admin_dashboard` — Authenticate to the shopping_admin Magento admin dashboard and report typed authenticated-state facts without exposing raw authentication artifacts.
  - Owns: Open the shopping_admin admin entry page, Detect whether the site currently presents the admin login form, Submit admin credentials through the demonstrated Magento login controls when login is required, Report typed authenticated-state facts after the login attempt without exposing raw FORM_KEY or cookie/token values
  - Does not own: Choosing which downstream admin page or business data to inspect after login, Returning raw authentication implementation artifacts such as FORM_KEY, cookies, or bearer tokens, Parsing dashboard business tables beyond authenticated-state detection, Answering task-specific questions from authenticated pages
  - Evidence workflows: task130_t1002, task202_t366

### `catalog`

- `shopping_admin/catalog/filter_product_grid_by_quantity_range_and_extract_products` — Filter the shopping admin catalog products grid by inventory quantity range and return typed product rows from the current results page.
  - Owns: Navigating to the shopping admin catalog product grid page within the current deployment origin, Opening the product-grid Filters panel, Filling the site's quantity range filter fields `qty[from]` and `qty[to]`, Applying the site's filter action and waiting for filtered results to load, Reading structured product rows from the rendered product grid table on the current page, Parsing demonstrated row fields: product name, SKU, quantity text, and salable text, Parsing numeric quantity_value when the displayed quantity text is directly numeric
  - Does not own: Authentication credential acquisition or secret management, Establishing authentication when no valid admin session already exists, Choosing business-specific quantity bounds, Cross-page pagination through additional product-grid result pages, Reducing rows to only SKUs or computing counts, Task-level filtering, ranking, or formatting beyond the site acquisition
  - Evidence workflows: task187_t368

### `customers`

- `shopping_admin/customers/search_customers_by_phone_in_admin_grid` — Search the shopping admin All Customers grid by billing phone number and return typed customer records from the filtered visible results on the current grid page.
  - Owns: Navigating to the shopping admin customer grid page within the current deployment origin, Filling the billing telephone filter field with the requested phone number using the evidenced selector, Applying the customer-grid filter and waiting for filtered results to load, Reading visible customer grid rows from the current filtered page, Parsing demonstrated typed fields from matching visible rows: name, email, and matched phone number
  - Does not own: Authentication credential acquisition or secret management, Establishing authentication when no valid admin session already exists, Clearing saved filters with unevidenced controls, Opening optional filter panels with unevidenced controls, Looping over multiple phone-number queries, Cross-page pagination over additional customer grid pages, Ranking, deduplication, or business selection among multiple matched customers, Returning raw row_text or generic page text, Final answer formatting or task-level success/not-found policy
  - Evidence workflows: task209_t364, task210_t364

### `dashboard`

- `shopping_admin/dashboard/get_dashboard_last_orders` — Extract the Last Orders records shown on the Magento admin dashboard.
  - Owns: Use the authenticated Magento admin dashboard page as the acquisition boundary, Locate the 'Last Orders' dashboard table in page HTML, Parse table rows from the dashboard widget, Extract typed order fields shown in each row: order_view_url, customer, items, total_text, Return the dashboard-presented recent-order records in display order
  - Does not own: Authenticating if caller has not already reached an authenticated dashboard page, Summing items across orders, Choosing a top-N subset other than the page-presented rows, Claiming site-wide completeness beyond the dashboard widget contents
  - Evidence workflows: task130_t1002

### `orders`

- `shopping_admin/orders/list_orders_grid_rows` — List order records from the shopping_admin orders grid page, including visible row fields parsed from the table.
  - Owns: Navigate to the admin orders grid URL, Read the visible orders table rows from `table.data-grid tbody tr`, Parse row cell text into structured order-grid records using demonstrated column positions, Return status text and displayed purchase date text exactly as shown on the site for each visible row
  - Does not own: Authenticating to shopping_admin admin, Selecting only canceled/cancelled orders for a task-specific subset, Assuming the first matching canceled row is the most recent business answer, Cross-page pagination through the full orders collection, Proving no canceled orders exist site-wide when none are visible on the current page, Sorting, ranking, or validating whether the current grid is descending beyond what the page already shows, Answer formatting for the final user response
  - Evidence workflows: task202_t366

### `reviews`

- `shopping_admin/reviews/export_product_reviews_report_csv` — Export the shopping admin product reviews report as typed per-product records for a created-at date range.
  - Owns: Navigate to the shopping admin product reviews report page after authenticated session is established, Fill the report filter inputs `input[name="created_at[from]"]` and `input[name="created_at[to]"]` with caller-provided storefront date strings, Trigger report refresh with the `Search` button, Read the selected export value from `select[name="gridProducts_export"]` after filters are applied and normalize it to an absolute site URL, Download the CSV export from that site-provided URL using the same authenticated browser context, Parse CSV rows into typed product review report records including displayed review count and last review date text
  - Does not own: Logging into the admin site as a separate reusable capability, Choosing the date range for the business question, Summing review counts across exported rows, Checking whether dates satisfy a task-specific month constraint beyond returning the site's displayed `last_review_text`, Answer formatting
  - Evidence workflows: task345_t248
- `shopping_admin/reviews/get_product_review_detail` — Open a shopping admin review edit page and extract typed review details including title, nickname, body text, product field text, numeric rating, raw status value, loaded URL, and navigation HTTP status.
  - Owns: Navigate to a review edit URL in the shopping admin, Read structured form values from the review detail page, Parse the selected star/radio rating into a numeric integer when present, Capture the site's raw status field value when present, Read the displayed product field text when the evidenced Product field block is present, Preserve the page URL and navigation HTTP status as objective metadata
  - Does not own: Discovering review URLs from search results, Admin authentication/session bootstrap, Sentiment classification, Selecting only positive or negative reviews, Summarizing or extracting reasons from review text, Any mutation of review data
  - Evidence workflows: task123_t250, task112_t245
- `shopping_admin/reviews/get_product_review_page_count` — Retrieve the page-reported total count from a selected shopping admin product-review page variant using either the unfiltered All Reviews grid or the Pending Product Reviews page.
  - Owns: Authenticate to the shopping admin admin area when login is required and credentials are supplied, Navigate to one selected site-local review page variant using a semantic page enum rather than separate overlapping public methods, Parse the page-reported count from the appropriate evidenced on-page mechanism for that variant, Return typed count and observed page metadata tied to the requested review page state
  - Does not own: Choosing credentials source or hard-coding credentials outside the primitive interface, Aggregating counts across multiple review pages or statuses, Iterating through review rows or paginating through records, Interpreting the count as a business answer beyond returning the page-reported integer
  - Evidence workflows: task347_t248, task77_t277
- `shopping_admin/reviews/get_review_grid_result_count_by_status` — Get the shopping admin product reviews grid's site-reported result count after applying one review status filter, using an existing authenticated session or inline login when credentials are supplied and login is required.
  - Owns: Navigate to the product reviews admin grid page, Optionally authenticate through the site's admin login flow when login is required and credentials are supplied, Apply the grid Status filter using the site's review status control, Submit the grid search/filter action, Read the site-rendered grid summary text and parse the numeric result count
  - Does not own: Choosing which review status to query for task-specific purposes beyond the single provided status input, Aggregating across multiple different filters or pages, Extracting individual review row records, Interpreting the count as a business answer beyond returning the site-reported filtered count
  - Evidence workflows: task78_t277, task79_t277
- `shopping_admin/reviews/list_product_review_grid_rows` — Search the shopping admin product reviews grid by product name and return typed visible row records from the current filtered result page, including normalized row text and review edit targets when present.
  - Owns: Navigate to the shopping admin product reviews grid page after authentication, Fill the product-name filter input `#reviewGrid_filter_name` with a caller-supplied product name, Submit the grid search via the Search button, Read the resulting grid rows from `#reviewGrid_table tbody tr` on the current filtered page, Extract row-scoped data demonstrably present in each row, including normalized row text and the review detail Edit link text/URL when available, Return the filtered Edit-link targets as a derived lossless projection of rows for workflows that only need downstream review detail targets
  - Does not own: Admin login/authentication bootstrap, Choosing which product name to search for, Opening each review detail page, Classifying review sentiment or dissatisfaction, Cross-row ranking, deduplication, or business selection, Proving site-wide absence beyond the current filtered result page
  - Evidence workflows: task123_t250, task112_t245
- `shopping_admin/reviews/list_product_reviews_by_created_date_range` — List visible product review records from the shopping admin reviews grid for a specified created-date range on the current results page.
  - Owns: Navigating to the shopping admin product reviews grid within the current deployment origin, Filling the created-date filter inputs `created_at[from]` and `created_at[to]` with caller-provided text, Submitting the filter using the site's Search button, Reading the resulting current-page review rows from the grid table, Reading the resulting grid summary text from the page body and parsing the site's `N records found` total when present
  - Does not own: Authentication credential acquisition or secret management, Establishing authentication when no valid admin session already exists, Choosing the business date range of interest, Repeating the query over multiple date ranges, Counting or aggregating records beyond returning the site's observed total_count field, Typing individual review columns beyond the generic current evidence of visible row cells, Computing derived KPIs or formatting final answers
  - Evidence workflows: task348_t248

## Approval

Review only. Editing generated package.py invalidates its hash.
