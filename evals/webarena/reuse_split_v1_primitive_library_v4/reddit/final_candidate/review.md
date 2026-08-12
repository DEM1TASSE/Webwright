# reddit candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `forums`

- `reddit/forums/list_forum_posts` — List posts from a Reddit forum listing page for a given listing mode, preserving the site's displayed order and returning typed post records with stable identity and listing-visible metadata parsed from each submission card when available.
  - Owns: Open a forum listing URL parameterized by forum name and listing mode., Parse visible post records from the listing page into typed post objects., Preserve the displayed order from the page., Return stable post identity from the URL, including post id, relative path, and resolved URL., Extract listing-visible title, author username, and timestamp from the same submission card when available., Declare that results cover the visible listing page rather than claiming full forum completeness.
  - Does not own: Choose which forum or listing mode to inspect for a task., Decide that the first item is the correct business answer beyond the site's displayed order semantics., Aggregate, rank, or filter posts beyond the selected page and order., Fetch additional post-detail fields not present at the listing boundary.
  - Evidence workflows: task30_t33, task28_t33, task29_t33

### `posts`

- `reddit/posts/read_post_page` — Fetch a Reddit post page and return stable post metadata together with typed visible comment records parsed from the same page, preserving page-visible comment order and exposing page-level comment summary signals when available.
  - Owns: Open a post detail page by URL or path., Parse stable post metadata from page markup or metadata fallbacks, including title and author username., Parse page-exposed comment count summary metadata when present., Detect explicit empty-comments signals exposed by the page., Identify individual displayed comment blocks on the page., Parse each visible comment's author username, displayed net score, displayed timestamp, and OP-marking metadata., Return typed comment records for downstream filtering and aggregation., Return visible text excerpts as typed strings rather than raw HTML., Return post identity derived from the URL alongside extracted detail fields.
  - Does not own: Choose which post to inspect., Determine whether a comment counts for a particular task., Compare comment authors against the post author for task-specific exclusions., Interpret negative net score as satisfying a business rule., Aggregate counts or format final task outputs., Perform task-specific reasoning or final answer formatting.
  - Evidence workflows: task30_t33, task29_t33, task28_t33

## Approval

Review only. Editing generated package.py invalidates its hash.
