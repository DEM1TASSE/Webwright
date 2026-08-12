# shopping_admin candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `customers`

- `shopping_admin/customers/get_customer_detail_from_admin_url` — Open a shopping admin customer edit page from a provided admin URL and extract the displayed customer email.
  - Owns: Open a provided admin customer edit URL in an authenticated session, Parse the customer detail page for displayed email, Return typed facts from the customer-detail acquisition boundary supported by evidence
  - Does not own: Logging into the admin site, Discovering the customer URL from unrelated pages, Searching the customer grid, Inferring unsupported customer profile fields, Mutating customer records
  - Evidence workflows: task244_t244

### `orders`

- `shopping_admin/orders/get_bestsellers_report_csv` — Retrieve typed bestseller report rows from the shopping admin bestsellers report export for a specified date range and period grouping.
  - Owns: Open the Magento bestsellers report for a caller-specified filter set, Construct the encoded filter URL for the report, Extract the export CSV endpoint from the filtered report page, Download and parse the CSV export into typed bestseller rows, Return export-based completeness metadata
  - Does not own: Logging into the admin site, Aggregating rows to find top sellers, Resolving brands from product names, Ranking or tie-breaking products, Any heuristic inference beyond exported row fields
  - Evidence workflows: task1_t279
- `shopping_admin/orders/get_order_detail` — Open a shopping admin order detail page by URL or order ID and extract objective order metadata together with typed line-item names, displayed money strings, and rendered SKU occurrences shown on the page.
  - Owns: Navigate to an authenticated admin order detail page by URL or order_id, Parse stable order-level fields displayed on the page such as title, order date, and order status, Identify line-item tbody blocks corresponding to order items, Extract product name from each line-item block, Extract displayed money strings from each item block without overcommitting to a heuristic semantic interpretation, Read rendered page text from the order detail page, Parse SKU occurrences from the rendered page into typed SKU records preserving page order, Return typed order-detail facts rather than raw HTML or raw body text
  - Does not own: Selecting which order to inspect, Verifying business rules like requiring Complete status, Sorting items by price, Inferring which displayed currency amount corresponds to a canonical business field, Deduplicating or comparing SKUs in workflow logic, Formatting final answer, Mutating the order
  - Evidence workflows: task204_t366, task290_t234
- `shopping_admin/orders/get_sales_orders_report_rows` — Retrieve typed rows from the shopping admin Sales Orders report for a specified date range, period granularity, and optional order-status filtering.
  - Owns: Navigate to the Sales > Orders report page, Apply stable report form controls for period type, date range, order-status filtering, and empty-row inclusion, Submit the report and parse the rendered table into typed rows, Return objective report row fields actually exposed by the report table
  - Does not own: Logging into the admin site, Choosing task-specific date ranges or statuses, Mapping month numbers to month names for final answer formatting, Aggregating, ranking, or limiting rows beyond the requested report filters
  - Evidence workflows: task110_t270
- `shopping_admin/orders/list_sales_orders_from_grid` — Retrieve typed sales order records from the shopping admin sales order grid with optional status filtering, pagination, and stable grid-exposed order metadata.
  - Owns: Navigate to the shopping admin sales order area as needed to establish the grid context, Issue authenticated requests to the Magento sales order grid endpoint, Apply optional server-side status filtering via grid parameters, Apply requested page_number and page_size to the grid request, Parse Magento sales order grid payloads returned either as JSON, embedded x-magento-init HTML, or embedded sales_order_grid_data_source HTML, Return typed order records with stable identifiers, timestamps, status, billing name, and detail URL when present, Return page-level pagination metadata exposed by the grid including total_records
  - Does not own: Logging into the admin site, Selecting the latest or otherwise task-relevant order, Aggregating orders by month or customer, Counting cancellations or ranking customers, Opening order detail pages, Formatting final task answers
  - Evidence workflows: task107_t270, task204_t366, task290_t234

### `reviews`

- `shopping_admin/reviews/get_product_review_detail` — Open a shopping admin product review detail page by review ID and extract stable typed review facts displayed on that page, including reviewer fields, product name, selected rating, linked customer edit URL, and any displayed customer email.
  - Owns: Navigate to the admin review detail/edit page for a supplied review ID, Extract stable review-detail fields shown on the page, including nickname, title, review body text, product name, and selected rating, Extract linked admin customer edit URL when present on the review detail page, Extract displayed customer email when present on the review detail page, Return typed objective facts from the review-detail acquisition boundary
  - Does not own: Logging into the admin site, Discovering which review to inspect, Ranking or classifying review sentiment such as deciding which review is 'most unhappy', Opening the linked customer page, Counting, aggregating, or formatting final answers
  - Evidence workflows: task244_t244, task112_t245, task246_t244, task243_t244
- `shopping_admin/reviews/search_product_reviews` — Search the shopping admin product reviews grid using built-in detail and/or product filters and return typed visible-page review row records plus grid-reported total-match metadata.
  - Owns: Navigate to the admin product reviews grid, Apply built-in review detail and/or product-name filters demonstrated by the site UI, Submit the search and optionally inspect a requested result page, Parse visible review grid rows into typed records with stable row-level facts supported by evidence, including review identity via edit URL and review ID when present, Return the grid-reported total matching-record count and visible-page completeness metadata
  - Does not own: Logging into the admin site, Choosing business-specific search terms, Opening each review detail page for deeper verification, Counting records for final answers, Sentiment ranking, thresholding, or other subjective task logic
  - Evidence workflows: task11_t288, task14_t288, task112_t245, task246_t244

## Approval

Review only. Editing generated package.py invalidates its hash.
