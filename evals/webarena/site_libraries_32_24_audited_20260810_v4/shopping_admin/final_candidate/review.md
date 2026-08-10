# shopping_admin candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `orders`

- `shopping_admin/orders/get_sales_orders_report_rows` — Retrieve Magento admin Sales Orders report rows for a specified date range, period granularity, and optional order-status filtering, parsed into typed report records.
  - Owns: Navigating to the Magento admin Sales Orders report page after authentication, Setting report filter controls including period type, date range, and order status mode/status value, Submitting the report filter form, Reading the report result table and parsing each row into typed records, Preserving the report period label and parsed temporal components exposed by the table
  - Does not own: Logging in to the site, Choosing task-specific months to return, Restricting output to January through May unless requested via inputs, Aggregating beyond the rows already provided by the report, Formatting a final answer for the user
  - Evidence workflows: task108_t270

### `reviews`

- `shopping_admin/reviews/get_product_review_detail_from_admin` — Open a product review detail page in the shopping admin by review id and extract structured review detail fields including product name and selected star rating.
  - Owns: Constructing and navigating to the admin review detail URL for a given review id, Reading the associated product name from the review detail page, Reading the selected star rating from the checked rating control, Returning structured review detail data for a single review
  - Does not own: Authenticating into the admin site, Discovering review ids from the review grid, Filtering by product or rating threshold, Aggregating multiple review details into a task answer, Formatting the final response
  - Evidence workflows: task215_t249
- `shopping_admin/reviews/list_product_review_records` — List product review records from Magento admin review listing pages for a requested scope, returning typed review identifiers and page-level pagination facts from the currently loaded listing page.
  - Owns: Navigating to Magento admin product review listing pages for supported scopes after authentication, Owning the mapping from stable review-list scope names to listing endpoints, Parsing review edit links on the listing page into stable review identifiers, Parsing page-level pagination facts exposed on the listing page, Returning typed page records plus pagination/completeness metadata for the currently loaded scope page
  - Does not own: Authenticating into Magento admin, Choosing which scope is relevant to a user task, Counting, aggregating, or comparing reviews across pages or scopes, Inventing unsupported pagination navigation mechanics beyond the evidenced current-page fetch, Formatting a final answer
  - Evidence workflows: task77_t277
- `shopping_admin/reviews/list_product_reviews_from_admin_grid_page` — Fetch the shopping admin product reviews grid with an optional product-name filter and return typed review records visible on the current grid page, together with page-level pagination and completeness facts.
  - Owns: Navigating to the admin product reviews grid after authentication, Applying the product-name filter in the reviews grid when requested, Enumerating review rows visible on the current grid page, Parsing typed review fields visible in each grid row, Parsing page-level pagination facts exposed on the filtered or unfiltered grid page, Returning current-page records with pagination/completeness metadata
  - Does not own: Authenticating into the admin site, Assuming the current grid page contains the complete filtered result set, Opening individual review detail pages, Extracting star rating from review detail pages, Filtering reviews by rating threshold, Aggregating or formatting the final task answer
  - Evidence workflows: task215_t249

## Approval

Review only. Editing generated package.py invalidates its hash.
