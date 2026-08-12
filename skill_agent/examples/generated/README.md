# Generated candidate packages, four sites

Built by the agent-driven pipeline from the seventeen gold workflows in
`skill_agent/inputs/workflows/`. Nothing here is promoted. Each site is one batch, so each was
built in two episodes -- one that extracts and writes primitives, one that assigns feature
classes -- plus the independent reviewer and judge episodes those spawn.

| site | primitives | scripted `audited_site_library_v2` |
|---|---:|---:|
| gitlab | 8 | 9 |
| map | 2 | 2 |
| shopping | 5 | 5 |
| shopping_admin | 6 | 5 |
| **total** | **21** | **21** |

## What to look at

`package.py` is the deliverable: feature classes under a site class, each method a site
acquisition returning typed records. `index.json` carries the contracts and the source evidence
behind each one. `quality_verdicts.json` is the independent judge's ruling on every operation --
worth reading where a capability looks thin, since a FAIL there is usually why.

## Per site

### gitlab — 8 primitives

- `gitlab/issues/get_issue_closed_state_from_issue_page` → `['issue_state']`
- `gitlab/issues/search_dashboard_issues_by_role_and_title_substring` → `['matches']`
- `gitlab/members/list_project_members_from_members_page` → `['members']`
- `gitlab/projects/get_project_id_and_star_count_from_project_page` → `['project']`
- `gitlab/projects/list_personal_projects_from_dashboard_with_stats` → `['projects']`
- `gitlab/projects/search_personal_projects_by_name` → `['projects']`
- `gitlab/repository/list_branch_contributors_from_graphs_page` → `['contributors']`
- `gitlab/repository/list_repository_commits_in_date_range` → `['commits', 'pagination']`

### map — 2 primitives

- `map/route/get_osrm_route` → `['code', 'duration_seconds', 'distance_meters', 'legs']`
- `map/search/geocode_search_query` → `['results']`

### shopping — 5 primitives

- `shopping/contact/get_contact_page_phone_numbers` → `['phone_numbers']`
- `shopping/orders/get_order_detail_totals` → `['order_detail']`
- `shopping/orders/list_orders_from_account_orders_page` → `['orders']`
- `shopping/reviews/list_product_reviews_from_current_product_page` → `['reviews']`
- `shopping/search/search_products_from_results_page` → `['products']`

### shopping_admin — 6 primitives

- `shopping_admin/admin/login_admin_http` → `['authenticated_url', 'dashboard_contains_pending_reviews_link', 'dashboard_contains_all_reviews_link']`
- `shopping_admin/admin/login_admin_ui` → `['final_url', 'already_authenticated']`
- `shopping_admin/orders/get_sales_orders_report_rows` → `['rows', 'records_found_text_present']`
- `shopping_admin/reviews/get_review_detail_record` → `['review_id', 'review_title', 'product_name', 'rating', 'rating_widget_style']`
- `shopping_admin/reviews/list_review_ids_from_review_listing_page` → `['review_ids', 'page_count', 'page_title', 'listing_path']`
- `shopping_admin/reviews/list_reviews_by_product_name_from_grid` → `['product_name', 'rows', 'visible_row_count']`

## Known gaps

- **GitLab has eight where the scripted library has nine.** The eight pair up one-for-one; the
  ninth is repository reachability, which the scripted version ships returning `body_snippet`,
  a 500-character slice of raw page text that the boundary rules forbid. The agent extracted
  that capability in an earlier run, had it rejected for exactly that, and dropped it rather
  than narrowing it to `{repository_path, url, title, accessible}`. The rules now ask for
  narrowing first; in this run the capability was not extracted at all.
- **`shopping_admin` has six where the scripted has five**, because it separates HTTP and UI
  login as two mechanisms. Two source workflows demonstrate them separately, with different
  inputs and outputs, so this looks right rather than redundant.
- **None of this code has ever been executed.** The checks are static: contracts, evidence,
  boundary, name resolution, declared imports. They establish that a method will not raise on
  its first call for a reason visible in the source. They say nothing about whether it returns
  the right facts from the live site.

## Where these came from

GitLab, Map and Shopping come from one run; `shopping_admin` from a later one, after the site
stage was reduced to feature classification. The difference does not affect the other three --
their consolidations were already pure `KEEP` -- but it is worth knowing when comparing.
