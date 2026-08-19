# reddit candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `forums`

- `reddit/forums/list_forum_new_posts` — Retrieve the posts shown on a Reddit forum's /new listing page in displayed order, including stable post URL and displayed author username, plus displayed post title when available from the rendered listing structure.
  - Owns: Navigate to a specified Reddit forum's /new listing page, Read the rendered listing page, Extract displayed post URLs for posts shown on that /new page, Extract displayed author usernames associated with shown posts, Extract displayed post title when the rendered listing structure exposes it, Preserve the displayed order of posts on the listing page, Return typed listing records for the acquired page slice
  - Does not own: Choosing which forum to inspect for a task, Interpreting 'latest' beyond the site's displayed /new ordering, Selecting one post from the returned list for task logic, Ranking, filtering, or semantic relevance decisions beyond the site's displayed order, Answer formatting
  - Evidence workflows: task30_t33, task27_t33
- `reddit/forums/list_forum_top_posts` — Retrieve the posts shown on a Reddit forum's top listing page in displayed order, including stable post title and post URL.
  - Owns: Navigate to a specified Reddit forum's top listing page with a supported time filter, Read the rendered top-listing page, Extract repeated displayed post titles and stable post URLs from the loaded page, Preserve displayed rank order on the page, Return typed post records for the loaded page slice
  - Does not own: Choosing which forum or time filter to inspect for a task beyond the supported parameter, Semantic relevance judgments about post topics, Opening a selected post and interpreting its contents, Aggregation, ranking, or final answer formatting outside the loaded page slice
  - Evidence workflows: task69_t17, task67_t17

### `posts`

- `reddit/posts/load_post_page` — Load a Reddit post detail page by URL and return page-level fetch facts for the reached post page.
  - Owns: Navigate to a specific Reddit post detail URL, Wait for the post page to load, Return typed fetch facts about the reached page
  - Does not own: Returning raw HTML, raw DOM, or arbitrary page text, Classifying the meaning of the post content, Extracting subjective recommendations or book names from prose
  - Evidence workflows: task67_t17
- `reddit/posts/open_post_from_listing_by_title` — Open a Reddit post from the current listing page by its displayed link title and return the destination post URL.
  - Owns: Locate a Reddit post link on the current rendered listing page by visible link title, Navigate to the selected post page by clicking that link, Return typed navigation facts for the opened destination
  - Does not own: Determining which title should be selected for a task, Extracting entities, organizations, or semantic meaning from the destination page, Returning arbitrary page text or HTML from the destination page
  - Evidence workflows: task69_t17

### `users`

- `reddit/users/get_user_comments_page_state` — Retrieve a Reddit user's comments page state, including whether the page explicitly shows the site's no-entries empty state.
  - Owns: Navigate to a specified Reddit user's /comments page, Acquire the rendered page body text and page URL/status context, Detect the explicit site empty-state message on the comments page, Return typed page-state metadata for that user comments page
  - Does not own: Parsing individual comment records when comments exist, Counting comments with specific vote properties, Inferring anything beyond the single loaded comments page, Task-specific choice of which username to inspect, Answer formatting
  - Evidence workflows: task30_t33, task27_t33

## Approval

Review only. Editing generated package.py invalidates its hash.
