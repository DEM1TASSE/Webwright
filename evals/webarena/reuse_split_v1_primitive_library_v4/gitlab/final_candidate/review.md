# gitlab candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `commits`

- `gitlab/commits/list_repository_commits` — List repository commits for a GitLab project with optional ref and time-window filters via the REST API.
  - Owns: Call the GitLab repository commits API for a specified project., Accept optional ref and time-window filters supported by the endpoint., Parse and return typed commit records from the API response., Preserve stable commit identity, author, timestamp, title, and link fields., Expose page-scoped pagination completeness from response headers.
  - Does not own: Filtering commits to a specific contributor after retrieval., Counting commits for a month, date, or author., Summarizing or formatting final numeric answers.
  - Evidence workflows: task133_t322
- `gitlab/commits/list_repository_commits_history_page` — Open a GitLab repository commits history page for a ref and return typed date-group summaries and visible commit metadata from the current page.
  - Owns: Navigate to a GitLab repository commits history page for a specified project and ref., Read the rendered commits history page text from the current page., Parse displayed date-group labels and their shown commit counts., Parse visible authored metadata entries associated with those date groups., Return typed current-page commits-history facts without claiming full repository history completeness.
  - Does not own: Choosing which date group or author is relevant to a task., Counting only a chosen author's commits for a task answer., Aggregating across multiple history pages unless the caller paginates., Inferring repository-wide completeness from a single page.
  - Evidence workflows: task132_t322

### `issues`

- `gitlab/issues/get_issue_details` — Retrieve details for a specific GitLab issue by project path with namespace and issue IID.
  - Owns: Call the GitLab issue detail API for a specific project and issue IID., Handle URL encoding of project path with namespace., Return typed issue detail fields from the API response., Provide authoritative issue state and timestamps for downstream workflows.
  - Does not own: Choosing which issue to inspect., Converting state into a final boolean answer., Comparing multiple issues or applying task-specific title matching.
  - Evidence workflows: task175_t310
- `gitlab/issues/get_issue_state_from_page` — Open a GitLab issue detail page and extract its normalized open or closed state from the rendered page.
  - Owns: Navigate to a GitLab issue detail page by URL., Read rendered issue page text from the browser session., Parse the displayed issue state into a normalized open or closed value., Return typed issue-state facts from the page boundary.
  - Does not own: Finding the correct issue URL from search or list pages., Converting the state into a task-specific boolean answer., Mutating issue state or performing issue actions.
  - Evidence workflows: task180_t500
- `gitlab/issues/list_dashboard_issues_page` — Open the GitLab dashboard issues page with supported author or assignee filters and return typed issue link summaries from the current results page.
  - Owns: Navigate to the GitLab dashboard issues page for author-filtered or assignee-filtered queries., Apply demonstrated query-string controls for assignee username, author username, free-text search, sort, state, and page number., Parse issue links from the rendered current results page into typed issue summary records., Preserve visible result order on the fetched page., Return page-scoped results without claiming corpus-wide completeness.
  - Does not own: Choosing which returned issue is the latest relevant one for a task., Opening an issue detail page to inspect additional fields like state., Aggregating across multiple dashboard pages., Formatting a downstream boolean or final answer.
  - Evidence workflows: task176_t310, task180_t500
- `gitlab/issues/list_project_issues` — List issues for a GitLab project via the REST API with optional scope, ordering, sorting, and pagination.
  - Owns: Call the GitLab project issues API endpoint for a specified project., Accept scope, ordering, sort direction, and pagination inputs supported by the endpoint., Parse and return typed issue records from the API response., Preserve stable issue identity, timestamps, state, and web URL fields., Expose page-scoped pagination completeness using response headers.
  - Does not own: Filtering issues by task-specific title substring or semantic relevance., Selecting the latest matching issue across multiple projects., Converting issue state into a workflow boolean answer., Aggregating issues across projects.
  - Evidence workflows: task175_t310
- `gitlab/issues/search_issues` — Search GitLab issues from the current search results page and return typed issue result records in displayed order.
  - Owns: Navigate to GitLab search results with issues scope and a caller-provided query., Parse visible issue search result cards from the current results page., Extract typed issue facts demonstrated at the result boundary, including title, visible state label, and issue link when present., Preserve displayed result ordering for the parsed current page., Limit completeness claims to the fetched search results page.
  - Does not own: Choosing which matching issue is relevant for a specific task., Interpreting 'latest updated' from visible ordering as a final task answer., Aggregating results into a single boolean answer., Guaranteeing corpus-wide completeness across additional pages.
  - Evidence workflows: task174_t310

### `projects`

- `gitlab/projects/get_project_by_path` — Retrieve a GitLab project record by full path with namespace via the REST API.
  - Owns: Call the GitLab project API using a URL-encoded full path with namespace., Parse and return a typed project record from the JSON response., Preserve stable project identity, path, default branch, and repository URL fields.
  - Does not own: Choosing which project path to resolve., Comparing the returned project against task-specific expectations., Searching across multiple projects.
  - Evidence workflows: task133_t322
- `gitlab/projects/get_project_clone_urls` — Open a GitLab project page and extract clone URLs exposed in the rendered HTML.
  - Owns: Navigate to a GitLab project page by project path., Read the project page HTML from the authenticated browser session., Parse clone URL fields exposed by the page, including SSH and HTTP when present., Return typed clone URL data associated with the project page.
  - Does not own: Searching for the correct project to inspect., Choosing which clone protocol a workflow should prefer., Performing git clone or other local repository operations.
  - Evidence workflows: task295_t329, task293_t329
- `gitlab/projects/list_membership_projects` — List GitLab projects accessible to the authenticated user from the membership-scoped projects API.
  - Owns: Call the GitLab membership-scoped projects API endpoint., Accept pagination inputs supported by the endpoint., Parse and return typed project records from the API response., Preserve stable project identity, path, namespace, and web URL fields., Expose page-scoped pagination completeness using response headers.
  - Does not own: Filtering projects for a downstream task., Inspecting issues within each project., Ranking or selecting projects for a workflow goal., Combining project results with issue-derived conclusions.
  - Evidence workflows: task175_t310
- `gitlab/projects/list_personal_projects_page` — Open the GitLab personal projects listing with supported sort options and return typed project summaries from the current page.
  - Owns: Navigate to the GitLab personal projects listing UI., Apply the Personal scope and supported sort option demonstrated by the source., Parse visible current-page project list items into typed project summaries., Extract stable listing fields demonstrated in evidence, including project name, URL, path, star count, and viewer owner marker., Limit completeness claims to the visible page.
  - Does not own: Choosing which project has the highest star count., Resolving ties or aggregating across pages., Opening individual projects to retrieve additional metadata such as project ID., Performing authentication bootstrapping beyond requiring an authenticated browser session.
  - Evidence workflows: task169_t289
- `gitlab/projects/search_project_links` — Submit a GitLab project search and return typed project link candidates parsed from the current search results page.
  - Owns: Submit a GitLab project search request using the projects scope., Parse candidate project links from the current search results page., Return typed project link candidates with project path, resolved URL, and visible link text., Preserve current-page discovery order without claiming full multi-page completeness.
  - Does not own: Choosing which of multiple matching projects is the correct task target., Ranking or semantically filtering results beyond the search query itself., Opening a project page for clone URL or other detail extraction., Claiming all project results are captured across additional pages.
  - Evidence workflows: task293_t329, task295_t329

## Approval

Review only. Editing generated package.py invalidates its hash.
