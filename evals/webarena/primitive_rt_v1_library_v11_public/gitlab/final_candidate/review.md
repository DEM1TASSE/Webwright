# gitlab candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `commits`

- `gitlab/commits/list_repository_commits` — List commit records for a GitLab repository ref from the repository commits API with optional site-native filters and optional paginated traversal.
  - Owns: Constructing the GitLab repository commits API request for one project and ref, Accepting either a numeric project_id or a path-based project_path for the same site-local commits resource, Applying site-supported query parameters such as ref_name, author, since, until, page, and per_page, Retrieving commit records from either a single API page or all pages via explicit traversal_mode, Parsing JSON response items into typed commit records with stable identifiers, authorship, timestamps, and web links
  - Does not own: Choosing which repository, branch, author, or time range to inspect, Looping over multiple repositories or refs, Cross-query merge or deduplication across repeated commit-list requests, Task-level filtering, counting, ranking, or summarizing beyond the API response slice(s) requested, Using the HTML commits page as a verification source
  - Evidence workflows: task205_t320, task134_t322
- `gitlab/commits/list_visible_commit_day_buckets` — List commit history buckets shown on a GitLab project's branch commits page, including displayed day labels, per-day commit counts, and visible commit author names within each day section.
  - Owns: Open a specific project's commits page for a given branch, Parse the rendered commits listing into typed day-bucket records, Extract the displayed day label for each visible bucket, Extract the displayed per-day commit count from each visible bucket, Extract visible commit author names within each visible day bucket
  - Does not own: Filtering for specific people such as Eric or Kilian, Inferring site-wide or branch-wide absence of commits by an author from one visible page slice, Aggregating counts across multiple days, Navigating pagination or infinite scroll beyond the demonstrated visible page, Ranking, comparison, or answer formatting
  - Evidence workflows: task207_t320, task135_t322

### `contributors`

- `gitlab/contributors/list_repository_contributors` — Retrieve contributor records for a GitLab project's repository from the repository contributors endpoint.
  - Owns: Issuing the GitLab repository contributors request to /api/v4/projects/{project_id}/repository/contributors, Parsing the JSON response into typed contributor records, Preserving contributor fields demonstrated by the workflow, including name, email, and commits
  - Does not own: Ranking contributors by commit count, Selecting the top N contributors, Project discovery or project_id lookup, Formatting contributor emails for the final answer
  - Evidence workflows: task315_t324
- `gitlab/contributors/list_repository_contributors_from_graph_page` — Open a GitLab repository branch graphs page and extract contributor commit summary records shown on that page as typed contributor records, while also supporting direct navigation to a known graphs page URL.
  - Owns: Navigating to a GitLab repository branch graphs page at /<namespace>/<project>/-/graphs/<branch> or directly to a caller-supplied graphs page URL, Optionally authenticating to the GitLab site with username/password before accessing repository pages, Extracting contributor summary cards from the rendered contributors graph section when that UI is present, Falling back to rendered page-text parsing for contributor entries when card selectors are absent, Parsing typed contributor records including both demonstrated name field spellings, commit_count, optional displayed email, preserved summary_text, and commit_count_text, Returning the full contributor list visible on that one graphs page
  - Does not own: Choosing which repository or branch to inspect for a user task, Ranking, sorting, or selecting top contributors, Cross-page pagination or infinite-scroll handling beyond the loaded graphs page, Cross-source joins with profile pages or repository APIs, Proving repository-wide absence beyond the acquired page
  - Evidence workflows: task318_t324, task787_t316

### `issues`

- `gitlab/issues/get_issue_detail` — Open a GitLab issue detail page and extract typed issue metadata including title and whether the page indicates the issue is closed.
  - Owns: Authenticating to the GitLab instance via the sign-in form using authenticity_token and session cookies, Fetching a GitLab issue detail page by relative or absolute issue URL, Extracting the page title from the HTML title element, Deriving a normalized issue title from the page title text by removing the trailing (#...) suffix when present, Detecting whether the rendered issue page text indicates a closed state
  - Does not own: Finding candidate issue URLs from searches or listings, Ranking or choosing which issue to inspect, Guaranteeing that text-state parsing captures every possible GitLab visual state variant beyond the demonstrated closed indicator, Formatting the final answer for the user
  - Evidence workflows: task177_t310
- `gitlab/issues/list_dashboard_issues` — List issues from the GitLab dashboard issues page with site-supported assignee, state, and text-search filters, returning issue links and page-exposed updated timestamps.
  - Owns: Authenticating to the GitLab instance via the sign-in form using authenticity_token and session cookies, Requesting the dashboard issues page with GitLab query parameters assignee_username, state, and search, Parsing issue result entries from the returned HTML, Extracting each issue's relative URL from /-/issues/<number> links, Extracting page-exposed update timestamp values from datetime attributes near each issue result, Returning a query-scoped collection of matching issue candidates
  - Does not own: Choosing which username, state, or search term to use for a task, Client-side keyword confirmation against nearby snippet text beyond the site's own search filter, Deduplicating repeated issue links emitted by page parsing, Sorting candidates client-side by updated timestamp, Selecting the latest issue from the returned collection, Opening an issue detail page, Determining whether an issue is closed from the issue page text, Cross-query merge/dedup or looping over multiple searches
  - Evidence workflows: task177_t310

### `profiles`

- `gitlab/profiles/get_user_follower_count_from_profile` — Read a GitLab user's follower count from their profile page
  - Owns: Navigate to a GitLab user profile page, Locate the followers link using the demonstrated selector `a[href$="/followers"]`, Extract displayed follower text and parse an integer follower count from it
  - Does not own: Determining which user profile to inspect, Validating that the profile belongs to a contributor selected elsewhere, Listing follower identities, Inferring missing counts when the followers link/text is absent
  - Evidence workflows: task787_t316

### `projects`

- `gitlab/projects/search_projects` — Search GitLab projects by a text query and return typed project records from the site search results.
  - Owns: Issuing the GitLab projects search request to /api/v4/projects with a caller-provided search string, Parsing the JSON response into typed project records, Preserving stable project identity and canonical repository fields exposed by the API, including project id, path_with_namespace, and web_url
  - Does not own: Choosing which returned project is the task target, Exact-match filtering for a specific path_with_namespace, Looping over multiple search terms, Cross-query merge or deduplication, Ranking or selecting a nearest/best project beyond the site response
  - Evidence workflows: task134_t322, task315_t324

## Approval

Review only. Editing generated package.py invalidates its hash.
