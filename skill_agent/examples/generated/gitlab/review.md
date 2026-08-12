# gitlab candidate primitive package

Status: candidate; not promoted.

## Feature classes

### `issues`

- `gitlab/issues/get_issue_closed_state_from_issue_page` — Open a GitLab issue detail page and determine whether the issue is closed from visible page state signals.
  - Owns: navigation to an issue detail URL, reading visible issue page text and title, parsing closed/open state signals from the presence of Closed/Reopen issue versus Open/Close issue controls
  - Does not own: finding the issue URL to inspect, converting the state into a task-specific boolean answer wrapper, answer formatting
  - Evidence workflows: task175_t310
- `gitlab/issues/search_dashboard_issues_by_role_and_title_substring` — Search authenticated dashboard issue listings for authored or assigned issues, follow pagination, and return issue links whose visible titles contain a supplied substring.
  - Owns: authenticated dashboard issues URL shapes with author_username or assignee_username and state query parameters, extracting issue links from issue list pages, following rel=next or Next pagination links, matching visible issue titles by substring
  - Does not own: deciding which matched issue is the answer when several exist, deriving a boolean answer from issue state, answer formatting
  - Evidence workflows: task175_t310

### `members`

- `gitlab/members/list_project_members_from_members_page` — List members with access to a GitLab project by parsing the embedded members data on the project's /-/project_members page.
  - Owns: authenticated GET of the GitLab project members page, locating the data-members-data attribute embedded in the members page HTML, HTML-unescaping and JSON-decoding the embedded members payload, extracting typed member records including username, name, access level, and member type
  - Does not own: excluding the current user from the results, choosing which project to inspect, answer formatting
  - Evidence workflows: task350_t298

### `projects`

- `gitlab/projects/get_project_id_and_star_count_from_project_page` — Open a GitLab project page and parse the visible Project ID and Star count from the page text.
  - Owns: authenticated navigation to a GitLab project page by namespace/project path, reading page body text, parsing visible Project ID and Star count semantics from the project page
  - Does not own: deciding which projects to inspect, filtering for star count equal to zero, aggregating ids across projects
  - Evidence workflows: task172_t289
- `gitlab/projects/list_personal_projects_from_dashboard_with_stats` — List personal projects from the GitLab dashboard Personal filter and parse the visible per-project stars, forks, merge requests, and issues counts from each project list row.
  - Owns: authenticated navigation to /dashboard/projects and application of the Personal filter, locating project list rows in main .projects-list > li, extracting project path/name link from each row, parsing visible stars, forks, merge requests, and issues counts from the row text
  - Does not own: filtering to only zero-star projects, opening each project detail page for more fields, sorting or answer formatting
  - Evidence workflows: task172_t289
- `gitlab/projects/search_personal_projects_by_name` — Search the authenticated user's personal projects from the dashboard projects view and return matching project paths and labels.
  - Owns: authenticated dashboard projects search endpoint shape /dashboard/projects with name, personal, and sort query parameters, parsing project links from the HTML response, deduplicating repeated project links
  - Does not own: selecting the correct project from among matches for a task, project member parsing, answer formatting
  - Evidence workflows: task350_t298

### `repository`

- `gitlab/repository/list_branch_contributors_from_graphs_page` — List contributors and their commit counts from a repository branch's GitLab contributors graphs page by parsing the visible ranking text.
  - Owns: authenticated navigation to the GitLab contributors graphs URL shape /{namespace}/{project}/-/graphs/{branch}, reading visible page text from the contributors graph page, parsing contributor names and commit counts from the ranking text, deduplicating repeated contributor rows
  - Does not own: taking only the top three contributors, splitting a full name into first and last name fields for a specific answer format, ranking or answer formatting beyond the page's own order
  - Evidence workflows: task317_t324
- `gitlab/repository/list_repository_commits_in_date_range` — List repository commits from the GitLab repository commits API within a supplied authored-date window.
  - Owns: GitLab repository commits API endpoint shape /api/v4/projects/{project_id}/repository/commits, query parameters for since, until, page, and per_page on commit listing, parsing commit records from the JSON response, exposing pagination/completeness headers returned by the API
  - Does not own: filtering commits to a particular author token, counting matching commits, answer formatting
  - Evidence workflows: task306_t321

## Approval

Review only. Editing generated package.py invalidates its hash.
