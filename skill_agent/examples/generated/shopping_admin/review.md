# shopping_admin candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `admin`

- `shopping_admin/admin/login_admin_http` — Authenticate to the Magento admin over HTTP by fetching the login form, extracting the hidden form_key, and submitting admin credentials.
  - Owns: Magento admin login URL and POST shape, hidden form_key extraction from login HTML, typed confirmation facts from the returned authenticated page
  - Does not own: exposing a reusable HTTP session object for later requests, which downstream admin page to inspect for a task, task-specific counting or filtering over retrieved records
  - Evidence workflows: task77_t277
- `shopping_admin/admin/login_admin_ui` — Authenticate to the Magento admin UI with Playwright by filling the username and password fields and submitting the sign-in form when a login page is shown.
  - Owns: Magento admin login page selectors, username/password field selectors and sign-in button selector, authenticated dashboard reachability through UI login
  - Does not own: browser/context creation, what records to inspect after authentication
  - Evidence workflows: task215_t249

### `orders`

- `shopping_admin/orders/get_sales_orders_report_rows` — Open the Magento Sales Orders report page, apply report filters, and parse the visible report table rows into typed monthly order-count records.
  - Owns: Sales Orders report URL /admin/reports/report_sales/sales/, report filter selectors for period, date range, and order status, table parsing for month/year rows and order-count values from the rendered report
  - Does not own: choosing task-specific date ranges or statuses beyond passed parameters, formatting months for a final answer outside the typed records it returns, comparisons or aggregation beyond the report rows displayed by the site
  - Evidence workflows: task108_t270

### `reviews`

- `shopping_admin/reviews/get_review_detail_record` — Open a Magento admin review detail page by review ID and extract the review title, associated product name, and selected star rating.
  - Owns: review detail URL pattern /admin/review/product/edit/id/<id>/, product-name selector on review detail pages, selected rating extraction from checked radio input id, with rating widget style as supporting evidence, carrying forward the review title associated with the opened review ID into the detail record
  - Does not own: filtering for one specific product, deciding whether a rating meets a task threshold, assembling final task answer objects across many reviews
  - Evidence workflows: task215_t249
- `shopping_admin/reviews/list_review_ids_from_review_listing_page` — Fetch an authenticated Magento admin review listing page over HTTP and extract the visible review edit IDs together with pager and title metadata when present.
  - Owns: review listing URLs under /admin/review/product/..., authenticated HTTP fetch of a review listing page using supplied Cookie header, review identity parsing from edit links /admin/review/product/edit/id/<id>/, pager total-pages parsing from listing HTML, HTML title parsing from listing pages
  - Does not own: performing the login that obtained the authenticated cookies, deciding whether a specific listing page answers a question, counting, comparing, or aggregating records for a task beyond returning the visible IDs and pager facts
  - Evidence workflows: task77_t277
- `shopping_admin/reviews/list_reviews_by_product_name_from_grid` — Open the admin All Reviews grid, filter by product name, and return the visible review IDs and titles from matching rows.
  - Owns: All Reviews grid URL /admin/review/product/, product-name filter input selector #reviewGrid_filter_name, grid row parsing for review ID and title columns after filtering
  - Does not own: thresholding by rating, opening each review detail page, question-specific inclusion or exclusion logic
  - Evidence workflows: task215_t249

## Approval

Review only. Editing generated package.py invalidates its hash.
