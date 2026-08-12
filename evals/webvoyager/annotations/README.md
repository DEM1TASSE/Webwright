# WebVoyager task annotations

This directory contains a preliminary machine annotation of all 643 official
WebVoyager tasks. It is intended for human review before freezing same-template
or cross-template pilot splits; it is not ground truth.

The WebArena-granularity third pass is in `webvoyager_annotations.strict_v3.csv`;
this is the recommended file for human review. It preserves the v2 template, the
strict template, the review decision, confidence, and rationale. Edit `review_status`
to `approved`
or `edited`. Prioritize rows with low `confidence`, high live-web risk, login
requirements, or broad families/templates. Same-template membership is defined
by equal site and `template`; cross-template candidates must have unequal
templates and share a substantive capability (not merely opening the homepage
or typing into a generic search box).

The current first pass includes family, template, ordered capabilities, slots,
interaction/output type, login/live risk, confidence, and notes. During review,
add an explicit `primitive_target` for selected pilot tasks: the continuous,
reusable subworkflow expected to transfer. This should be frozen before runs.

Regenerate merged files with:

```bash
python evals/webvoyager/annotations/build_review_files.py
```
