# Host-case redirect loop breaks Magento under concurrency

Context: running original WebArena (`test.raw.json`, evaluator pinned at `dce04686`) against a
self-hosted six-site deployment, driven by the `official-webarena-eval-skill` branch.

## The finding

`resolve_placeholders()` in `skills/official-webarena/scripts/webarena_final_state_eval.py`
lowercases the netloc of every deployment URL it substitutes:

```python
parsed = urlsplit(deployment_url)
if parsed.netloc:
    deployment_url = urlunsplit(parsed._replace(netloc=parsed.netloc.lower()))
```

That is **correct for URLs the evaluator string-compares** and **wrong for URLs the harness
navigates to**, because the two have opposite requirements:

| URL role | Requirement | Why |
|---|---|---|
| compared (`eval.reference_url`) | host must be **lowercase** | `URLEvaluator` compares `netloc + path` literally, and Chromium always reports `page.url` with a lowercased host. An uppercase reference can never match. |
| navigated (`start_url`, `eval.program_html[].url`) | host must be **byte-identical to `base_url`** | Magento compares the request host against its stored `web/unsecure/base_url` literally. On *any* mismatch it 302-redirects to `base_url`; the client normalises that host to lowercase, which mismatches again, and the request loops until the redirect cap. |

So one blanket rule cannot serve both. The same function feeds both roles.

## Reproducing the Magento loop

It does **not** reproduce with a single sequential request — Magento's full-page cache serves
those without reaching the PHP path that performs the base-URL check. You need concurrency
*and* a cache-busting query:

```bash
for h in GCRSANDBOX410 gcrsandbox410; do
  printf "%-14s " "$h"
  seq 30 | xargs -P 30 -I{} curl -s -o /dev/null -w "%{http_code}\n" \
    -L --max-redirs 10 --max-time 40 \
    "http://$h.redmond.corp.microsoft.com:7970/catalogsearch/result/?q=zz{}$RANDOM" \
  | sort | uniq -c | tr '\n' ' '; echo
done
```

Observed (deployment stores `base_url` with an uppercase host):

```
GCRSANDBOX410  30 200
gcrsandbox410  30 302     <- redirect cap hit, search page unusable
```

Only Magento behaves this way. GitLab and Reddit answer 200 for either case.

The trigger is not "lowercase" specifically — it is *any* host that is not byte-identical to
`base_url`. Against an unmodified instance, `localhost` and `127.0.0.1` loop too:

```
localhost                                   20 302(10)
127.0.0.1                                   20 302(10)
GCRSANDBOX410.redmond.corp.microsoft.com    20 200(0)
```

Lowercase is simply the case you always hit in practice, because Chromium lowercases the host
in `page.url` and the agent then reuses it.

Symptom in a run: the agent reports the site "returns infinite 302 self-redirects", search and
category browsing become unusable, and that site's scores collapse. It looks like agent
incompetence in the results, not infrastructure.

## Code change on the branch

Split the two roles instead of applying one rule:

- `resolve_placeholders(..., lowercase_host: bool = True)` — pass `lowercase_host=False`
  wherever the result will be navigated to (all three call sites in `official_webarena.py`,
  and the task resolution inside `evaluate_saved_state`).
- New `lower_host(url)` — lowercases only the netloc, leaving path and query untouched.
- New `normalise_comparison_urls(task)` — applies `lower_host` to `eval.reference_url` only,
  splitting on ` |OR| ` so multi-reference entries are each normalised.

`program_html[].url` therefore keeps the deployment's case (it is navigated to live), while
`reference_url` is lowercased (it is compared against `final_state.final_url`).

Justification: host names are case-insensitive per RFC 3986, so normalising host case for
*string comparison* is a correctness fix, not a scoring relaxation. Paths and queries, which
are case-sensitive, are never touched.

## The code change alone is not sufficient

Handing the agent an uppercase `start_url` does not keep it on uppercase. Chromium reports
`page.url` with a lowercased host, and the agent copies that into subsequent `page.goto()`
calls. In one end-to-end run of task 124 the command history showed **25 lowercase host uses
against 1 uppercase**. The single run still passed because it never hit the cache-miss path;
under 64-way concurrency it would loop.

The run side therefore has to be made case-tolerant in the environment. The minimal change,
verified on a spare instance:

```sql
INSERT INTO core_config_data (scope,scope_id,path,value)
VALUES ('default',0,'web/url/redirect_to_base','0')
ON DUPLICATE KEY UPDATE value='0';
```

then `php bin/magento cache:flush`. This rewrites no URLs — `base_url` keeps its original
value — it only stops Magento from redirecting on a host mismatch. Before/after on the spare
instance, same cache-busting concurrency probe:

```
before   GCRSANDBOX410 20x200    gcrsandbox410 20x302
after    GCRSANDBOX410 20x200    gcrsandbox410 20x200
```

Reverting is setting the value back to `1` and flushing.

## Pointing the harness at localhost does not avoid this

Tempting, since the deployment is on the same host, but it fails for a separate reason: Magento
generates every link from `base_url`. A page fetched over `http://localhost:PORT/` comes back
with all 386 of its links pointing at the FQDN, so the agent is carried off localhost on its
first click and `page.url` becomes the FQDN anyway. Making localhost work would mean rewriting
`base_url` itself, a much larger change than disabling `redirect_to_base`. The latency argument
does not carry it either: median 0.103 s over loopback vs 0.113 s via the FQDN.

## Residual edge case

65 `program_html` targets use `func:` URLs containing `__last_url__`, which the evaluator
expands from `page.url` — always lowercase, so those navigations cannot be held to the
deployment's case. By site: 50 reddit (case-insensitive, harmless) and 5 shopping (would loop
without the `redirect_to_base` change). Another reason the environment-side fix is what
actually closes this.

## Unrelated note on evaluator provenance

`webarena` as installed in some local venvs is a repackaged fork (`377abe06`), not an ancestor
or descendant of official `dce04686`. Scores produced against the two are not comparable and
must not be pooled into one number.
