# gitlab candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `commits`

- `gitlab/commits/list_repository_commits` — List commit records for a GitLab repository via the repository commits API with optional time-window and pagination parameters, returning typed commit facts plus response pagination metadata.
  - Owns: Constructing the GitLab repository commits endpoint from a project identifier, Applying optional repository commits query parameters such as since, until, per_page, and page_number, Fetching commit data from the GitLab repository commits endpoint, Parsing the JSON response into typed commit records, Preserving pagination metadata exposed by GitLab response headers
  - Does not own: Filtering commits to a task-specific author token, Counting commits for a specific person, Ranking, summarizing, or formatting the final answer, Determining the current repository from browser context when a project identifier is not provided
  - Evidence workflows: task306_t321

### `contributors`

- `gitlab/contributors/list_repository_branch_contributors` — List contributors for a GitLab repository branch from the branch contributors/graphs page, preserving displayed ranking order and commit counts from the inspected page.
  - Owns: Navigating to a GitLab repository branch contributors page using project path and branch name, Reading contributors ranking content from the page, Parsing displayed contributor entries into typed records with contributor identity, commit count, and displayed rank order
  - Does not own: Signing in outside whatever browser session is already provided, Choosing top N contributors as task logic beyond an explicit optional limit parameter, Splitting full names into first and last name, Cross-page aggregation, deduplication across branches, or subjective interpretation
  - Evidence workflows: task317_t324

### `issues`

- `gitlab/issues/get_issue_detail_state` — Open a GitLab issue detail page and return typed issue state derived from stable page signals plus page identity metadata.
  - Owns: Navigating to a GitLab issue detail page, Reading stable issue detail page signals for open/closed state, Returning typed issue page identity and state signals
  - Does not own: Searching for candidate issues, Filtering by title substring, Choosing among multiple candidate issues, Interpreting closed as a final task-specific boolean answer
  - Evidence workflows: task175_t310
- `gitlab/issues/list_dashboard_issues_by_actor_and_state` — List GitLab dashboard issue records for a specified actor filter and issue state, returning typed issue links from one results page with pagination metadata.
  - Owns: Navigating to GitLab dashboard issue listing pages, Applying actor-specific dashboard filters via URL parameters such as author_username or assignee_username, Applying issue state filter via URL parameter such as state, Extracting issue link records from the results page, Detecting pagination via the Next link
  - Does not own: Filtering issues by task-specific title substring like dependency, Combining multiple actor queries into one semantic result, Choosing the latest updated issue, Determining an issue's open/closed state from the issue detail page, Producing the final boolean answer
  - Evidence workflows: task175_t310

### `members`

- `gitlab/members/list_project_members` — List members who have access to a GitLab project by opening the project's members page and parsing embedded structured member data.
  - Owns: Opening a project's GitLab members page from a project path, Parsing the embedded structured members data blob from the page, Returning typed member records including stable identity and access metadata exposed by the page
  - Does not own: Searching for which repository to inspect based on task-specific text like a repo name query, Filtering out the current user or otherwise applying task-specific inclusion/exclusion rules, Ranking, aggregation, or answer formatting for the final response, Performing login beyond any existing authenticated browser session
  - Evidence workflows: task350_t298

### `projects`

- `gitlab/projects/get_project_overview_metrics` — Open a GitLab project overview page and extract visible project metadata such as project ID and star count from rendered page text.
  - Owns: Navigating to a project page by URL, Parsing rendered project overview text for visible project metadata, Returning typed project metadata including project ID and visible star count
  - Does not own: Discovering which project URLs to inspect, Deciding whether a project satisfies task-specific conditions such as having zero stars, Collecting data across multiple projects as a final task result
  - Evidence workflows: task172_t289
- `gitlab/projects/inspect_project_page_availability` — Inspect a GitLab project page at a known namespace/project path and return typed navigation and availability signals for that requested path.
  - Owns: Navigating directly to a GitLab project URL for a known namespace/project path, Capturing resulting page URL and title after navigation, Parsing stable page-level availability signals supported by the workflow into a typed availability state
  - Does not own: Authenticating to GitLab, Searching for alternate repositories if the requested path is unavailable, Creating issues or any other project mutation, Task-level reasoning about what to do when a project is inaccessible
  - Evidence workflows: task789_t328
- `gitlab/projects/list_dashboard_projects` — List visible project records from the GitLab dashboard projects page, optionally applying the built-in Personal scope, and parse project card counters from the inspected page.
  - Owns: Navigating to the dashboard projects page, Optionally activating a built-in dashboard scope tab such as Personal, Parsing visible project list items into typed project summary records, Extracting stable project identity shown in the list, including displayed project path text and project URL, Extracting visible numeric counters exposed on each project card: stars, forks, merge requests, and issues
  - Does not own: Choosing which scope/filter to use for a user task beyond exposing a parameter, Filtering records by business logic such as stars == 0, Opening each project detail page, Aggregating, ranking, or formatting final answers
  - Evidence workflows: task172_t289

## Approval

Review only. Editing generated package.py invalidates its hash.
