# shopping candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `catalog_search`

- `shopping/catalog_search/search_products_results_page` — Submit a catalog search on the shopping site and return typed product records visible on the resulting search results page.
  - Owns: Navigate to the shopping site home page, Submit a query through the site search box, Read visible product cards from the search results page, Parse stable displayed fields from each visible result card into typed records, State that returned records are limited to the visible results page when pagination is not explored
  - Does not own: Task-specific semantic filtering such as identifying Canon photo printers, Excluding accessories or supplies based on workflow intent, Computing min/max price ranges or other aggregates, Claiming completeness across multiple search result pages without pagination evidence, Ranking, comparison, or final answer formatting
  - Evidence workflows: task126_t159

### `contact`

- `shopping/contact/extract_contact_phone_numbers_from_contact_page` — Navigate from the shopping site homepage to the Contact Us page via the footer link and extract displayed phone numbers from the rendered page text.
  - Owns: Open the shopping site homepage, Follow the visible footer Contact Us link, Read rendered contact-page body text, Parse displayed phone-number strings from visible text, Return reached page metadata together with all parsed phone numbers in encounter order
  - Does not own: Deciding which parsed number is the customer service number beyond page context, Exploring arbitrary alternate navigation paths not demonstrated by the source workflow, Returning raw page text or DOM, Task-level answer phrasing or not-found response formatting
  - Evidence workflows: task313_t134

### `orders`

- `shopping/orders/get_customer_order_details` — Open a signed-in customer's order detail page and return structured order facts including status, displayed date, shipping and handling amount, and grand total.
  - Owns: Open a provided customer order detail page within the signed-in account area, Read rendered order-detail page text, Parse stable order facts demonstrated by the workflow, Extract displayed shipping and handling amount and grand total as typed numbers, Return stable identity/state/time fields from the order detail page
  - Does not own: Determining refund policy or whether refund equals grand total, Filtering orders by month or status, Summing across multiple orders, Performing order mutations or cancellations
  - Evidence workflows: task320_t160
- `shopping/orders/list_customer_orders` — Sign in to a shopping customer account, open the My Orders page, and return typed order summary records from the visible orders table.
  - Owns: Authenticate with customer credentials using the sign-in form, Navigate from the signed-in account area to My Orders, Parse each visible order row in the orders table into structured summary records, Return stable summary fields demonstrated in the workflow: order number, displayed short date text, status, and order-detail URL, Report that results are limited to the visible orders page when pagination is not explored
  - Does not own: Filtering orders by month or status, Summing refunds or other monetary aggregates across orders, Interpreting cancellation/refund policy, Claiming account-wide completeness without pagination evidence
  - Evidence workflows: task320_t160

### `reviews`

- `shopping/reviews/extract_product_reviews_from_product_page` — Open a shopping product page's Reviews tab and return structured review records parsed from the rendered review content on that page.
  - Owns: Navigate to a product page URL on the shopping site, Open the Reviews tab using the site's review-tab selectors, Read rendered page text after the reviews content is loaded, Parse repeated review blocks into structured review records, Return objective review fields shown in the rendered reviews: title, rating percent, body, reviewer name, and posted date
  - Does not own: Classifying reviews into task-specific categories such as customer-service complaints, Keyword-based complaint or sentiment judgments, Selecting only matching reviewers for a final answer, Formatting task response payloads
  - Evidence workflows: task26_t222

## Approval

Review only. Editing generated package.py invalidates its hash.
