# shopping candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `contact`

- `shopping/contact/get_contact_page_phone_numbers` — Navigate from the shopping homepage to the Contact Us page and extract phone numbers displayed there.
  - Owns: footer Contact Us link selector and navigation path, visible Contact Us page text acquisition, phone-number parsing from rendered contact-page text
  - Does not own: choosing a single answer string when multiple phone numbers are displayed, task-specific interpretation beyond extraction, answer formatting
  - Evidence workflows: task313_t134

### `orders`

- `shopping/orders/get_order_detail_totals` — Open an order detail page and parse objective detail fields including order number, visible status, one displayed date text when shown, shipping amount, and grand total.
  - Owns: order detail page acquisition by URL, parsing displayed order identifier, status, one displayed date text, shipping charge, and grand total from page text
  - Does not own: choosing which order URLs to inspect, adding totals across orders, interpreting the total as a refund for a task answer
  - Evidence workflows: task320_t160
- `shopping/orders/list_orders_from_account_orders_page` — Authenticate to a customer account, open the My Orders page, and parse visible order rows into records containing order number, row text, and order detail URL.
  - Owns: login page URL and sign-in selectors, navigation to My Orders after authentication, extracting visible order-row text, order numbers, and detail links from the My Orders table
  - Does not own: filtering to task-requested orders, interpreting row text into unsupported typed subfields, summing totals across orders, answer formatting
  - Evidence workflows: task320_t160

### `reviews`

- `shopping/reviews/list_product_reviews_from_current_product_page` — Open the reviews section on a product page and parse visible product reviews into typed records.
  - Owns: review tab selectors on a product page, parsing review blocks from rendered page text into typed fields
  - Does not own: classifying reviews by task-specific criteria, selecting names for the answer, answer formatting
  - Evidence workflows: task26_t222

### `search`

- `shopping/search/search_products_from_results_page` — Submit a search query on the shopping site and parse visible product search-result cards into typed product records.
  - Owns: homepage search box and Search button selectors, visible result-card selectors for product names and displayed prices, price-text parsing into numeric values
  - Does not own: semantic inclusion or exclusion rules for which products matter to a task, aggregate computations such as min/max, answer formatting
  - Evidence workflows: task126_t159

## Approval

Review only. Editing generated package.py invalidates its hash.
