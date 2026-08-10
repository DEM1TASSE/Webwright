# Online-Mind2Web status and WebVoyager task study

Updated: 2026-08-10

## Executive summary

The Online-Mind2Web (OM2W) integration is functional end to end: Webwright can run a live task,
convert its trajectory for the official evaluator, use upstream WebJudge as the answer-admission
gate, build a same-site primitive catalog from admitted source runs, and run a held-out task through
the routed path. The frozen five-site pilot validates that plumbing, but it does **not** yet measure
primitive lift. Three sites produced eligible libraries, yet the primitive metadata gate selected
`skip` for every held-out task because the learned primitives did not cover a material part of the
held-out capability.

WebVoyager is a better development set for testing whether primitives can be learned and reused.
Its official data has 643 tasks over only 15 sites (41--46 tasks per site), versus OM2W's 300 tasks
over 136 sites. This makes a same-site, same-capability, different-instance train/held-out split
possible. WebVoyager should not replace OM2W as the final external-validity benchmark: its tasks are
older, several are date-sensitive, and its original evaluator and maintenance policy are weaker.

Recommended use:

1. Use WebVoyager to measure primitive treatment and lift.
2. Use OM2W to measure live-site robustness, answer-gate precision, safe primitive skipping, and
   cross-site external validity.

## 1. Online-Mind2Web: current implementation

### 1.1 Benchmark characteristics

The official OM2W release contains 300 live tasks over 136 websites. The project updates tasks that
become invalid or encounter CAPTCHA/site drift. Its WebJudge evaluation has three conceptual stages:
key-point identification, key-screenshot selection, and outcome judgment over the task, screenshots,
and action history. The official repository reports 86% agreement between the o4-mini WebJudge and
human evaluation, with a 3.8 percentage-point success-rate gap.

Primary references:

- [Online-Mind2Web official repository](https://github.com/OSU-NLP-Group/Online-Mind2Web)
- [Online-Mind2Web leaderboard](https://hal.cs.princeton.edu/online_mind2web)

### 1.2 Code now present on this branch

The branch `dev-online-mind2web-gate` contains:

| Component | Path | Purpose |
| --- | --- | --- |
| Official evaluator adapter | `src/webwright/skill_factory/om2w_eval.py` | Converts Webwright runs and invokes the upstream OM2W evaluator |
| Answer/admission gate | `src/webwright/skill_factory/gate.py` | Admits only source runs accepted by WebJudge |
| Single-task paired runner | `evals/om2w/smoke_pipeline.py` | Runs scratch/routed arms, materializes verdicts, and compares them |
| Primitive builder | `evals/om2w/build_generated_primitives.py` | Builds a site catalog from WebJudge-admitted source families |
| Primitive catalog/retrieval | `src/webwright/skill_factory/primitive_catalog.py`, `primitive_retrieve.py` | Stores primitives and performs metadata-only treatment selection |
| Frozen pilot split | `evals/om2w/pilot_5sites/manifest.json` | Fixes source and held-out IDs before judging |
| Pilot summary | `evals/om2w/pilot_5sites/results.json` | Records outcomes and whether primitive treatment actually occurred |

Dataset and evaluator used for the pilot:

- Dataset: `Online_Mind2Web.json`, 300 tasks, SHA-256
  `7dedf381531d423dc0fc48d21dc1d425655dd75f38b10211a880fa09102f257f`.
- Upstream evaluator commit: `f0d805ee0e9e0b3ea70911e45e5264b72968f3dc`.
- Judge: `o4-mini`, admission threshold 3.
- Complete generated artifacts: `/home/t-demiwang/om2w-pilot-5sites`.

### 1.3 Five-site pilot result

The pilot froze 14 source tasks and five held-out tasks over Recreation.gov, AKC, BBB,
Healthline, and The Weather Network.

| Site | Source planned | Judgeable | Admitted | Active primitives | Held-out scratch | Held-out routed | Primitive used? |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Recreation.gov | 3 | 3 | 3 | 2 | 1 | 1 | No; metadata gate skipped |
| AKC | 3 | 3 | 2 | 2 | 1 | 1 | No; metadata gate skipped |
| BBB | 3 | 3 | 3 | 1 | 0 | no final artifact | No; metadata gate skipped |
| Healthline | 3 | 1 | 1 | 0 | not run | not run | Ineligible library |
| The Weather Network | 2 | 2 | 1 | 0 | not run | not run | Ineligible library |

Totals:

- 12 of 14 source tasks were judgeable.
- 10 of 12 judgeable sources passed WebJudge.
- Three of five sites met the minimum two-admitted-family library requirement.
- Two held-out pairs produced verdicts for both arms; both were `scratch=1, routed=1`.
- Zero held-out pairs received primitive treatment, so no primitive effect size can be computed.

`routed=1` only says that a task entered the routed pipeline and its eventual answer passed
WebJudge. It does not prove that a primitive was selected. A valid treatment analysis must record
both the answer verdict and `primitive_treatment=true|false`.

### 1.4 Why the primitive metadata gate skipped

The source WebJudge gate and the held-out primitive gate are different:

1. WebJudge decides whether a completed source trajectory is trustworthy enough to learn from.
2. The metadata gate decides whether an existing primitive materially helps the current held-out
   task without inspecting its code.

The metadata gate is instructed to skip when acquiring a primitive's prerequisites is itself the
main work, or when the primitive only provides marginal help. The pilot behaved accordingly:

| Site | Learned capability | Held-out capability | Reason for skip |
| --- | --- | --- | --- |
| Recreation.gov | Navigate to an already identified facility; open a facility detail tab | Search by activity and location to identify a park | Search and entity selection remained the main unresolved work |
| AKC | Dismiss cookies; navigate to an AKC destination | Use breed traits to identify an energetic hairless dog with medium barking | No breed-selector or trait-filter primitive existed |
| BBB | Dismiss recurring overlays | Search dealers, rank the second result, and enumerate all locations | Overlay dismissal was marginal to the core task |

The pilot used completely different source and held-out families. The builder was also required to
find support across multiple admitted source families. Their intersection naturally collapsed to
generic navigation, tabs, and overlay handling. A held-out task from yet another family then had
little reason to select those primitives. The gate is therefore not the main failure; the split and
abstraction target were misaligned with a reuse experiment.

### 1.5 Operational issues found

- Healthline returned CloudFront 403 pages on two source tasks. These are site-infrastructure
  failures, not agent or WebJudge failures.
- Several Webwright child processes stayed alive after writing final artifacts. The pilot had to
  verify the artifact and terminate the waiting parent manually. Batch execution needs an explicit
  post-final exit/timeout policy.
- Routed execution must receive `SKILL_MODEL_ENDPOINT`, `SKILL_MODEL_NAME`, and credentials. A model
  gateway YAML used by the browser agent does not automatically configure the primitive router.
  Without these variables, routing can fall back to the default OpenAI endpoint and fail with 401.
- A routed arm can safely fall back to scratch. Reports must distinguish `routed` from actual
  primitive selection, preferably with `route_stage`, `route_decision`, primitive IDs, and content
  hashes as required fields.
- OM2W's low per-site density makes a statistically useful same-site reuse split difficult. Sites
  with only two or three tasks cannot simultaneously support multiple admitted source families and
  a capability-overlapping held-out set.

## 2. WebVoyager official task set

### 2.1 Dataset and evaluation

The official `data/WebVoyager_data.jsonl` contains exactly 643 tasks. Each record has `web_name`,
`id`, `ques`, and starting `web`. The accompanying `reference_answer.json` contains site-grouped
answers, commonly marked `possible` when multiple or changing answers may be acceptable.
The counts and examples below were computed from official repository commit
`5a7896738c10bfb8b9edccce6bb0e0411f8ae569`.

The original evaluator provides the task, the agent response, and the last *k* screenshots to
GPT-4V. The paper reports 85.3% agreement with human judgments when the full trajectory is used.
The repository explicitly notes that Booking and Google Flights tasks are time-sensitive and that
their dates must be manually updated before execution.

Primary references:

- [WebVoyager official repository and task instructions](https://github.com/MinorJerry/WebVoyager)
- [WebVoyager paper](https://arxiv.org/abs/2401.13919)

### 2.2 Exact site distribution and concrete task families

| Site | Tasks | Dominant task families | Concrete official task examples | Primitive-fit assessment |
| --- | ---: | --- | --- | --- |
| Allrecipes | 45 | Recipe search, multi-constraint filtering, recipe-detail extraction, ingredients/instructions/nutrition | Find vegetarian lasagna with rating/review constraints; find a cauliflower crust under a prep-time threshold and report calories | **High**: repeated search-filter-detail-extract flow |
| Amazon | 41 | Product search, facets, rating/price constraints, product detail, comparison, cart | Find black size-7 running shoes under $50 and add to cart; find an ergonomic keyboard in a price range with 500+ reviews | Medium mechanically, but bot protection, volatile inventory, and cart mutation are major risks |
| Apple | 43 | Product/spec lookup, model comparison, configuration options, pricing, support content | Compare latest MacBook Air prices; inspect keyboard options while configuring a 14-inch MacBook Pro | Medium-high: stable navigation/configuration primitives, but products and prices change |
| ArXiv | 43 | Basic/advanced search, category/date filtering, result counts, paper detail, submission/help pages | Compare quantum-computing result counts in q-ph versus all archives; find the latest statistics ML paper and its abstract | **High**: stable, structured, repeatable query and detail flows |
| BBC News | 42 | Section navigation, latest article, named article lookup, summarization | Find the latest Green Living article; find a named climate guide and extract causal activities | Medium: navigation repeats, but answers and “latest” tasks drift rapidly |
| Booking | 44 | Destination/date/guest entry, amenity filters, rating/sort, price/currency | Find a Paris hotel for two adults with free cancellation; count London hotels after breakfast and fitness filters | Low for a frozen pilot: nearly all supplied dates are stale and availability is volatile |
| Cambridge Dictionary | 43 | Word lookup, UK/US pronunciation, definition, examples, grammar pages | Look up definition and pronunciation of “sustainability”; retrieve UK/US pronunciations and an example for “procrastination” | **High**: dense near-template instances and stable page structure |
| Coursera | 42 | Course search, level/duration/institution filters, course detail, syllabus, review distribution | Find a beginner 3D-printing course lasting 1--3 months; inspect star-rating percentages for a named Stanford course | **High/medium**: strong reusable flows, with some login/UI drift risk |
| ESPN | 44 | Scores, schedules, standings, leaders, team/player detail, sports news | Get current NBA Eastern standings; report the top scorer in the latest completed NBA game | Medium: strong repeated structure, but highly time-sensitive outputs |
| GitHub | 41 | Repository search qualifiers, stars/update/language filters, repository detail, contributors, product docs | Find a Python repository updated in two days with 500+ stars; find a blockchain repository and list its top five contributors | **High**: query syntax and repo-detail primitives are reusable; avoid signup/account tasks |
| Google Flights | 42 | Origin/destination/date entry, trip type, stops/airline filters, cheapest/shortest sorting | Find the cheapest NYC–Tokyo round trip; compare nonstop prices and duration | Low: all dated instances are stale, prices fluctuate, and UI/locale variation is high |
| Google Map | 41 | Place/category search, geographic proximity, rating/open-hours filters, place details, reviews | Find five Seattle salons rated above 4.8; locate a 24-hour lot near Brooklyn Bridge and summarize reviews | Medium-high capability reuse, but consent, localization, and result nondeterminism complicate evaluation |
| Google Search | 43 | Fact lookup, sports/current charts, knowledge panels, broad web search, some account/login tasks | Find a movie release date; find the latest Phoenix Suns score | Low for primitive learning: the website action is shallow and task domains are heterogeneous |
| Huggingface | 43 | Model/dataset/Space search, task/library/language filters, popularity sorting, model-card/docs extraction | Find a sentiment-analysis model updated in March 2023; identify the most downloaded en-zh translation model and report metrics/usage | **High**: repeated structured search-detail-documentation flows |
| Wolfram Alpha | 46 | Submit structured query, inspect result pods, mathematical/scientific computation | Compute a definite integral; request a differential-equation solution; calculate geomagnetic field for a place/date | **High** for query/result primitives, though many tasks test query formulation more than navigation |

Task counts sum to 643. The range is 41--46 tasks per site, consistent with the paper's statement
that each site contains roughly 40--45 tasks (the released Wolfram Alpha group has 46).

### 2.3 Approximate template and cross-template distribution

WebVoyager does not provide template or capability-family labels. The analysis below is therefore an
audit-derived taxonomy, not an official annotation. It uses two views:

1. Manual inspection of the operation skeleton required by every task on the most promising sites.
2. A conservative lexical check: quoted entities and numbers are normalized, common instruction
   words are removed, and each task's maximum token-Jaccard similarity to another task on the same
   site is measured. This lexical score detects obvious near templates but misses semantic templates
   whose entities are unquoted, so it is a lower bound rather than a cluster assignment.

#### Lexical near-template lower bound

| Site | Tasks | Median best-match similarity | Tasks with best match >= 0.35 | Tasks with best match >= 0.50 |
| --- | ---: | ---: | ---: | ---: |
| Allrecipes | 45 | 0.38 | 28 | 7 |
| Amazon | 41 | 0.17 | 0 | 0 |
| Apple | 43 | 0.25 | 12 | 8 |
| ArXiv | 43 | 0.24 | 6 | 0 |
| BBC News | 42 | 0.27 | 6 | 0 |
| Booking | 44 | 0.27 | 7 | 0 |
| Cambridge Dictionary | 43 | 0.57 | 31 | 25 |
| Coursera | 42 | 0.23 | 8 | 2 |
| ESPN | 44 | 0.27 | 16 | 12 |
| GitHub | 41 | 0.38 | 24 | 10 |
| Google Flights | 42 | 0.33 | 18 | 3 |
| Google Map | 41 | 0.22 | 4 | 2 |
| Google Search | 43 | 0.12 | 4 | 0 |
| Hugging Face | 43 | 0.26 | 12 | 4 |
| Wolfram Alpha | 46 | 0.12 | 0 | 0 |

The low Amazon, Booking, Maps, and Wolfram scores do not mean those sites lack templates. Their
entities, locations, dates, or mathematical expressions dominate the words and were not always
quoted, while the browser operation skeleton remains highly repetitive.

#### Manual operation-skeleton assessment

| Distribution type | Sites | Approximate interpretation |
| --- | --- | --- |
| One dominant repeated skeleton | Allrecipes, Amazon, Booking, Google Flights, Google Map, Wolfram Alpha | Roughly three quarters or more of tasks repeat one form/search-result-detail flow with different entities and constraints |
| One dominant family plus small side families | Cambridge Dictionary, Apple, BBC News, ESPN | A majority repeats lookup/detail or section/detail; the remainder covers grammar, configuration, standings, games, support, or marketing pages |
| Several connected families | ArXiv, Coursera, GitHub, Hugging Face | Search/discovery, result filtering, entity detail, and documentation are distinct templates connected by reusable navigation primitives |
| Shared shallow entry point but heterogeneous goals | Google Search | Most tasks share only issuing a search; downstream domains and evidence needs differ substantially |

Approximate dominant-family observations from task-by-task inspection:

- **Allrecipes:** 41 of 45 tasks follow recipe discovery/detail extraction. Output requirements vary
  among ingredients, instructions, time, ratings, reviews, nutrition, storage, and latest review.
  This is primarily a same-template parameterization set, with useful sub-template variation after
  the recipe page is opened.
- **Cambridge Dictionary:** roughly two dozen tasks are direct word lookup plus some combination of
  definition, UK/US pronunciation, IPA, meaning, and example sentences. Eight tasks form a separate
  grammar-page family; translation/thesaurus, quizzes/games, shop, and locale switching form smaller
  families.
- **GitHub:** repository discovery/search is the largest family. Repository inspection then branches
  into contributors, releases, commits, changed files, issues, wiki, README, language, stars, and
  forks. Pricing, Copilot, Skills, customer stories, and signup are separate site-content families.
- **ArXiv:** the largest connected component contains keyword/category/date/author/journal-reference
  search, result counts, latest-category browsing, and paper-detail extraction. Help/policy,
  organization/blog, and store/cart tasks are separate families.
- **Hugging Face:** model search/filter/rank and model-card extraction form the largest component.
  Dataset search/detail, Spaces/inference interaction, documentation, blogs/daily papers, pricing,
  and organization content form additional families.
- **Coursera:** course discovery/filtering and named-course inspection dominate. Course details
  branch into modules, duration, rating histograms, instructors, skills, and reviews. Specialization,
  degree, partner, Plus/Business, and homepage browsing are related but distinct templates.

#### Where genuine cross-template transfer exists

The best cross-template sites are not necessarily those with the most near duplicates. They have a
graph of different task endpoints connected through reusable intermediate browser states:

```text
GitHub repository search
  -> repository page
      -> contributors | releases | commits | issues | wiki | README

ArXiv query/category browse
  -> result list
      -> paper abstract | versions | HTML | PDF-derived inspection

Hugging Face model search/filter
  -> model page
      -> model metadata | model card | metrics | usage | linked Spaces

Coursera course search/filter
  -> course or specialization page
      -> modules | reviews | instructor | skills | included courses
```

These are useful cross-template relationships because the held-out goal differs while a material
intermediate capability remains shared. They are unlike the failed OM2W pilot, where the shared
primitive often ended before the held-out task's main work began.

By contrast:

- Allrecipes and Cambridge Dictionary are excellent **same-template/generalized-parameter** test
  beds, but a random split would be too easy and vulnerable to near-duplicate leakage.
- Booking and Google Flights contain strong repeated templates, but stale dates and volatile live
  results make them poor first experiments.
- Google Search and Wolfram Alpha mostly test query formulation and answer extraction. A primitive
  that only enters a query may reduce steps without demonstrating rich website skill reuse.

### 2.4 What the concrete tasks imply for primitive learning

WebVoyager contains several naturally repeated capabilities:

- **Search/filter/detail:** Allrecipes, Amazon, Coursera, GitHub, Hugging Face.
- **Structured query/result extraction:** ArXiv, Cambridge Dictionary, Wolfram Alpha.
- **Location search/detail/reviews:** Google Maps.
- **Date-driven form filling and sorting:** Booking and Google Flights.
- **Section/latest/detail extraction:** BBC and ESPN.
- **Product selection/configuration:** Apple and Amazon.

This density lets the experiment separate task identity from capability. For example, a GitHub
repository-search primitive can be trained on climate and quantum queries and held out on blockchain
queries. Entities, dates, thresholds, and answers remain unseen, while the reusable capability is
present. This is a stricter and more informative test than random splitting, but less pathological
than holding out a completely unrelated task family.

### 2.5 Data-quality and leakage risks

- Many tasks are near-template paraphrases. A random task split will overstate generalization.
- Reference answers include old ratings, review counts, prices, standings, model metadata, and
  2023/2024 dates. They cannot be treated as immutable gold answers on the live web.
- Booking and Google Flights explicitly require date rewriting. Rewriting must happen before the
  split is frozen and must be recorded in a task-instantiation manifest.
- Cart, signup, login, and account-related tasks should be excluded from an initial read-only pilot.
- “Latest”, “highest rated”, prices, availability, and review-count constraints require trajectory
  evidence and a live judge; string matching against the old reference answer is insufficient.
- Google Search offers many tasks but little common website-operation depth, so it is a poor test of
  a site primitive library even though individual answers may be easy.

## 3. Recommended WebVoyager primitive pilot

### 3.1 Initial sites

Start with five read-only, capability-dense sites:

1. ArXiv
2. Cambridge Dictionary
3. GitHub
4. Hugging Face
5. Allrecipes or Coursera, chosen after a live accessibility smoke test

Keep Wolfram Alpha as the first replacement. Avoid Amazon, Booking, and Google Flights initially.

### 3.2 Split unit and admission rules

Do not randomly split raw tasks. First annotate each task with:

- `site`
- `capability_family`
- `entity_or_query`
- `constraints`
- `read_only`
- `time_sensitive`
- `requires_login`
- `live_validated_at`

For each selected site, target 20 tasks across at least three capability families:

- 12 source/train tasks
- 8 held-out tasks
- at least two source examples and two held-out examples per measured capability
- no identical entity/query, answer, or near-duplicate wording across arms
- capability overlap required, exact template identity not required

Freeze task IDs, rewritten dates if any, family labels, dataset commit, and judge configuration before
running any source or held-out arm.

Use two explicitly separated evaluation tracks:

- **Within-template generalization:** same operation skeleton, disjoint entities and constraints.
  This establishes whether the primitive mechanism works at all.
- **Cross-template transfer:** different task endpoints with a preregistered shared intermediate
  capability, such as GitHub repository discovery followed by held-out release or issue inspection.

Do not combine the two tracks into one headline number. Cross-template transfer is the stronger
claim and should report the exact shared capability expected before the run.

### 3.3 Metrics

Report separate quantities:

- Source WebJudge admission rate.
- Sites/families reaching the minimum admission threshold.
- Primitive build acceptance and rejection counts.
- Primitive gate selection rate.
- Treatment coverage: fraction of held-out tasks with `primitive_treatment=true`.
- Scratch and routed WebJudge success.
- Success conditional on treatment.
- Lift on paired tasks, including regressions and safe skips.
- Calls, tokens, wall-clock time, and site-infrastructure failure rate.

The primary primitive result should be computed only on paired tasks where a primitive was actually
selected. All-task routed success remains useful as a safety/system metric but is not a primitive
effect estimate.

## 4. Decision

Continue supporting OM2W, but move the next primitive-learning pilot to a carefully filtered
WebVoyager subset. The desired evidence chain is:

```text
same-site capability examples
  -> WebJudge-admitted source trajectories
  -> cross-instance primitive
  -> metadata gate selects it on a disjoint held-out instance
  -> paired scratch/routed WebJudge comparison
```

After this chain produces non-zero treatment coverage on WebVoyager, return to OM2W as a sparse,
harder external validation set. If treatment coverage remains zero on a capability-overlapping
WebVoyager split, the problem is then in primitive abstraction or routing rather than benchmark
density.
