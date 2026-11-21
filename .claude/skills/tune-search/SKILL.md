---
name: tune-search
description: Fix Lavoro's search when the results are wrong — too few matches, too many, the wrong kind of role, the wrong places, or scores that feel off. Diagnoses where jobs drop out (filter, score, contacts), changes config.yaml with the user's OK, then re-checks the skipped jobs and scores again. Use when the user says "wrong jobs", "no matches", "too few", "too many", "not relevant", "tune my search", "change my roles", or "the scores are off".
---

# Tune the search

Jobs pass through five gates on each run. Find the gate that is wrong before changing anything.

1. **Filter** (no Claude): the title must contain one of `search.titles_include` and none of `search.titles_exclude`; the location must match `search.locations_include` (or the region preset), or the job must be remote in `remote_regions` with `remote_ok: true`; the company must not be in `companies_exclude`; ads from Platsbanken, Hacker News, Arbeitnow and the web search must be younger than `max_age_days` (roles on a company's own board have no age limit while `board_max_age_days` is 0).
2. **Quick check** (Claude, about 40 roles per call, up to `llm.max_jobs_to_triage_per_run` per run; off with `llm.triage: false`): sets aside clearly wrong roles from the title, company, place and the ad's first lines. They get score 0 and a reason starting "Quick check:".
3. **Score** (Claude, one call per role, up to `llm.max_jobs_to_score_per_run` per run): 0 to 10 against `profile.md`.
4. **Threshold**: only jobs at or above `llm.min_score` get a contact lookup and a draft.
5. **Contact**: a job with no email found shows under "Good fit, no email found".

## 1. Look

Run these and read the numbers:

```bash
python -m lavoro stats
```

```bash
python -m lavoro list --min-score 0 --limit 40
```

```bash
python -m lavoro region
```

Then read `config.yaml` (the `search:` and `llm:` sections) and `profile.md`.

## 2. Decide which gate is wrong

| What you see | Likely cause | What to change |
|---|---|---|
| "jobs passed filter" is tiny | Titles or places too narrow | Add title variants to `titles_include` (e.g. "product designer", "ux designer", "ui designer", and local terms such as "UX-designer"). Add spellings to `locations_include` (Göteborg/Gothenburg). Or widen the region. |
| Many passed, few scored | The per-run cap | Raise `llm.max_jobs_to_score_per_run` (each job is one Claude call on the user's plan), or let a few runs catch up. |
| A good role was set aside by the quick check | The quick check was too strict for this profile | Score it in full with `python -m lavoro rescore <key>`. If it keeps happening, ask the user what to make clearer in `profile.md`, or turn the quick check off with `llm.triage: false`. |
| Scored, but all below `min_score` | Bar too high, or profile missing facts | Lower `llm.min_score` by 1, or ask the user for missing facts for `profile.md`. Never invent them. |
| Wrong kind of role scores high | Titles too broad, or profile vague | Add words to `titles_exclude`; ask the user what to make clearer in `profile.md`. |
| Too senior | Seniority words missing | Add "senior", "staff", "principal", "lead", "head of" to `titles_exclude`. |
| A staffing agency keeps showing up | Not excluded | Add its name to `companies_exclude`. |
| Good fits with no email | Contact lookup found nothing | Normal for some companies. The user can apply through the link or add the person by hand on the Tracker. |

## 3. Change, with the user's OK

Show the user the exact lines you want to change in `config.yaml` and why, in one short message. Edit only after they agree. For the region, use the command instead of editing:

```bash
python -m lavoro region <sweden|nordics|europe|asia|worldwide|custom>
```

## 4. Apply

After a filter change (titles, places, companies), send the skipped jobs back through the filter, then filter and score:

```bash
python -m lavoro refilter
```

```bash
python -m lavoro match
```

After a `profile.md` change, score the best open jobs again:

```bash
python -m lavoro rescore
```

Then finish the chain for the jobs that now pass, in the background:

```bash
python -m lavoro run --no-refresh
```

## 5. Report

Say what changed, and compare "jobs passed filter", the number scored and the number at or above `min_score` before and after. Point to http://127.0.0.1:8765.

## Rules

- Never invent facts in `profile.md`. Ask the user.
- Change `config.yaml` only after the user agrees to the exact change.
- Never send an email; Lavoro only drafts.
