# gitlab candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `auth`

- `gitlab/auth/authenticate_with_sign_in_form` — authenticate to this GitLab deployment by submitting the web sign-in form and report whether authentication succeeded
  - Owns: Fetches the GitLab sign-in page, Extracts the CSRF/authenticity token from the sign-in form HTML, Submits username and password with the extracted token to the sign-in endpoint, Observes whether an authenticated session was established without exposing cookie or token values
  - Does not own: Choosing which user credentials to use, Validating authorization for any later resource beyond whether login succeeded, Performing project search or repository data retrieval, Exposing raw CSRF tokens, session cookies, or bearer tokens
  - Evidence workflows: task315_t324

### `commits`

- `gitlab/commits/collect_all_repository_commits` — collect all commits for a GitLab project and branch by traversing paginated commit results
  - Owns: Iterating through GitLab commit result pages for a specified project and ref until exhaustion, Combining paginated site records into one collection, Preserving typed commit records across pages including stable commit identity, author/committer metadata, timestamps, and web URL, Using the endpoint's empty final page or short page as pagination termination evidence
  - Does not own: Filtering collected commits by date or contributor, Counting matches for a task-specific predicate, Claiming completeness beyond the specified project and ref
  - Evidence workflows: task134_t322
- `gitlab/commits/get_commit_groups_from_project_commits_page` — retrieve date-grouped commit entries from a GitLab project's commits history page for a given ref
  - Owns: Constructing the GitLab project commits history URL from a project base URL and ref name, Loading the GitLab commits page in the browser, Parsing rendered page text into typed commit-date groups based on GitLab's displayed grouping semantics, Extracting per-group displayed commit count and commit entry author attribution lines from the page
  - Does not own: Choosing which authors to count or compare, Summing or filtering commits for task-specific people, Interpreting one page as complete repository history beyond the displayed page contents, Returning raw page text or DOM without parsing
  - Evidence workflows: task207_t320
- `gitlab/commits/list_branch_commit_day_summaries_from_url` — Retrieve a GitLab branch commits page from its absolute URL and parse its displayed day summary headers into typed records.
  - Owns: Navigate to a GitLab project branch commits history page using its absolute URL, Use authenticated page session to access the commits history view when required, Parse displayed day summary headers like '02 Mar, 2023 3 commits' from the currently loaded commits page, Extract the displayed commit count shown by GitLab for each visible day header
  - Does not own: Constructing the commits page URL from separate project and branch inputs, Filtering to a specific author, Selecting a specific day as the answer target, Counting commits for one author on one day, Parsing per-commit identity, timestamp, or link fields not demonstrated by the source code, Exhaustive traversal across additional commit history pages beyond the loaded page, Proof that no commits exist outside the currently loaded/visible commits page
  - Evidence workflows: task133_t322
- `gitlab/commits/list_repository_commits` — List commit records for a GitLab repository from the GitLab commits API with supported single-page filtering and pagination controls.
  - Owns: Constructing the GitLab repository commits API request for a specific project, Applying supported single-page GitLab commits API filters and pagination controls: ref_name, author, since, until, per_page, and page number, Parsing the GitLab commits API JSON into typed commit records, Returning the lossless union of evidenced stable commit metadata fields exposed by the API response, including author and committer metadata and authored/committed timestamps
  - Does not own: Choosing task-specific author, branch, or date values, Counting commits for the caller beyond reporting the returned page size, Cross-checking against HTML evidence, Project selection beyond the caller-supplied repository identifier, Pagination across multiple pages beyond the single requested page
  - Evidence workflows: task205_t320, task134_t322

### `contributors`

- `gitlab/contributors/list_repository_contributors` — retrieve contributor statistics for a GitLab project repository
  - Owns: Calls the GitLab repository contributors endpoint for a specified project, Parses JSON contributor records, Returns objective contributor statistics exposed by the site, including identity and commit counts
  - Does not own: Sorting contributors for a task-specific ranking, Selecting only top N contributors, Reducing records to only email addresses
  - Evidence workflows: task315_t324
- `gitlab/contributors/list_repository_contributors_from_graph_page` — Retrieve contributor records from a GitLab repository contributors graph page using one page-local browser mechanism and parse displayed contributor names, commit counts, and related summary text.
  - Owns: Navigate to a GitLab repository contributors graph page, Parse contributor records from the page using GitLab-local DOM structure with a rendered-text fallback, Extract contributor display name, Extract displayed summary text when present, Parse displayed commit counts from the page, Capture displayed email when exposed by the page
  - Does not own: Choosing which contributor is most relevant or has the maximum commits, Ranking or aggregating contributors beyond returning parsed records, Inferring repository or branch outside the supplied graph page URL, Returning raw DOM or page text without typed parsing
  - Evidence workflows: task318_t324, task787_t316

### `issues`

- `gitlab/issues/get_issue_detail_state` — Fetch a GitLab issue detail page and parse basic typed issue details including title and whether the issue is closed from visible page content.
  - Owns: Requesting an issue detail page within the authenticated GitLab session, Parsing the HTML title from the issue page, Converting the page HTML to visible text for state detection, Detecting whether the issue is closed based on visible page text, Returning typed issue detail fields instead of raw page text
  - Does not own: Finding candidate issue URLs to inspect, Ranking multiple issues by recency, Guaranteeing robust interpretation of every possible workflow state beyond the demonstrated closed-state check, Editing or mutating the issue
  - Evidence workflows: task177_t310
- `gitlab/issues/search_dashboard_issues` — Search the authenticated GitLab dashboard issues listing with site-supported filters and return typed issue-summary records parsed from the HTML results page.
  - Owns: Authenticating to GitLab via the sign-in form using authenticity_token/session-backed browser login flow, Constructing and requesting the GitLab dashboard issues URL with assignee_username, state, and search query parameters, Parsing the issues results HTML for issue links matching GitLab issue URL shape, Extracting per-result updated timestamp from nearby datetime markup when present, Deduplicating repeated issue links within the returned page by stable issue path, Returning typed summary records from the page rather than raw HTML
  - Does not own: Choosing which query terms to search for, Selecting only the latest result among returned matches, Determining semantic relevance beyond the site's own filters and the parsed returned records, Fetching the full issue detail page, Interpreting issue closed/open state from the issue detail page, Proving that no matching issue exists outside the returned results page
  - Evidence workflows: task177_t310

### `profiles`

- `gitlab/profiles/get_user_follower_count_from_profile_page` — Extract a GitLab user's follower count from their profile page.
  - Owns: Navigate to a GitLab user profile page, Locate the followers link on the profile page, Read the rendered followers link text, Parse integer follower count from the visible text
  - Does not own: Discovering which user profile to inspect, Verifying that a profile belongs to a task-selected contributor by matching arbitrary body text, Returning unrelated profile metadata not demonstrated in the workflow
  - Evidence workflows: task787_t316

### `projects`

- `gitlab/projects/search_projects` — search GitLab projects and return matching project records
  - Owns: Calling the GitLab projects search endpoint with a caller-supplied search string, Returning typed project records from the site response including stable identity and canonical web URL, Preserving page-scoped search results as returned by the endpoint
  - Does not own: Choosing which project among search results is the task-relevant repository, Inferring exact namespace/path match rules for a specific task, Any commit retrieval or counting logic
  - Evidence workflows: task134_t322, task315_t324

## Approval

Review only. Editing generated package.py invalidates its hash.
