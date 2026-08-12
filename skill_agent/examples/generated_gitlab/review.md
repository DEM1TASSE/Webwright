# gitlab candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `commits`

- `gitlab/commits/list_repository_commits_via_api` — List repository commits from the GitLab REST API for a project, with optional date filtering, authenticated session cookies, and pagination headers.
  - Owns: GitLab repository commits API endpoint shape /api/v4/projects/{project_id}/repository/commits, encoding since/until/page/per_page query parameters, issuing the API request using the current authenticated browser session cookies when present, parsing JSON commit objects and returning pagination header signals exposed by the response
  - Does not own: filtering commits by author token or name substring, counting matching commits for a question, choosing a specific project or date range for the task answer
  - Evidence workflows: task306_t321
- `gitlab/commits/list_visible_repository_contributors_from_graphs_page` — List the visible contributor names and commit counts shown on a GitLab repository branch contributors graph page.
  - Owns: GitLab repository contributors graphs page URL pattern /{namespace}/{project}/-/graphs/{branch}, reading the visible contributors ranking from the page main content, parsing visible contributor display names and commit counts from the rendered page text, returning an explicit completeness signal for the visible parse result
  - Does not own: taking only the top N contributors, splitting names into first and last names for a task answer, claiming full-list completeness beyond what is visibly parsed from the page
  - Evidence workflows: task317_t324

### `projects`

- `gitlab/projects/get_project_metadata_from_project_page` — Read a GitLab project page and extract visible project metadata such as project id and star count.
  - Owns: navigating to a project page by base URL plus relative project href/path, reading visible project metadata from the page body, parsing Project ID and displayed Star count from the rendered project page
  - Does not own: deciding which projects should be opened, requiring the star count to equal a specific value, aggregating metadata across multiple projects
  - Evidence workflows: task172_t289
- `gitlab/projects/list_personal_projects_from_dashboard` — List personal projects from the GitLab dashboard Personal filter with visible summary counts from each project card.
  - Owns: navigation to /dashboard/projects and applying the Personal filter link, parsing each personal project card from main .projects-list > li, extracting project path text, href, and visible summary counts for stars, forks, merge requests, and issues
  - Does not own: filtering to only zero-star projects, opening each project page to confirm a follow-up condition, sorting or ranking projects for a task answer
  - Evidence workflows: task172_t289
- `gitlab/projects/list_project_members_from_members_page_blob` — List project members by decoding the structured members data embedded in a GitLab project members page.
  - Owns: GitLab project members page URL pattern /{namespace}/{project}/-/project_members, extracting the data-members-data attribute blob from the HTML, HTML-unescaping and JSON-decoding the embedded member data, returning typed member records from the decoded blob
  - Does not own: filtering members to a subset requested by a task, formatting usernames into a final answer, inferring permissions beyond fields present in the embedded blob
  - Evidence workflows: task350_t298

### `reviews`

- `gitlab/reviews/get_issue_state_from_detail_page` — Open a GitLab issue detail page and determine its visible state from rendered controls and text.
  - Owns: navigating to an issue detail URL, reading rendered page text and controls on the issue page, deriving the objective issue state open or closed from visible state signals
  - Does not own: finding which issue to inspect, converting the state into a question-specific boolean answer, keyword matching on issue titles
  - Evidence workflows: task175_t310
- `gitlab/reviews/list_dashboard_issues` — List issues from a GitLab dashboard issues view, following pagination and returning issue titles and links from each page.
  - Owns: dashboard issues URL patterns with query filters such as author_username, assignee_username, and state, iterating paginated issue list pages using the next link, extracting issue title text and href for issue links that match /issues/{iid}
  - Does not own: searching for a task-specific keyword in issue titles, choosing between author and assignee views for a task answer, deduplicating across multiple independent start views unless requested by the caller
  - Evidence workflows: task175_t310

## Approval

Review only. Editing generated package.py invalidates its hash.
