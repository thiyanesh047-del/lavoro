# Lavoro

Lavoro is a job-search assistant that runs on the user's own computer. Each run it does four things:

1. Pulls new roles from company job boards: Greenhouse, Lever, Ashby, Workable, Recruitee, Teamtailor, SmartRecruiters, Workday, SAP SuccessFactors, and Sweden's Platsbanken, plus a Claude web search, a weekly check for companies that just raised money, and a bundled list of about 6,800 startups that are hiring (`lavoro/lists/startups.csv`).
2. Scores each role against the user's `profile.md`.
3. Finds the person who leads hiring for each good match.
4. Drafts a short email to that person.

Everything shows on a local site at http://127.0.0.1:8765.

## What the user probably wants

| The user says | Do this |
|---|---|
| "set up Lavoro", "install this", "get started", or `profile.md` / `config.yaml` is missing | Follow the `lavoro-setup` skill. |
| "run it", "find jobs", "morning run" | Follow the `morning-run` skill. |
| "open the site", "show me" | Run `python -m lavoro serve --open` in the background, then give the URL. |
| "add Spotify", "watch this company" | `python -m lavoro add <website, careers link or name>`. A careers link is the surest; Workday and SuccessFactors boards need one. |
| "search all of Europe", "only Sweden" | `python -m lavoro region <sweden\|nordics\|europe\|asia\|worldwide\|custom>`. The next run re-checks jobs the old region skipped. |
| "wrong jobs", "too few matches", "too many", "tune my search" | Follow the `tune-search` skill. |
| "why did this job score 4?" | Find its key with `python -m lavoro list --limit 50`. The site's email card lists what fits, what is missing and what rules it out; the same is in `jobs.fit_detail` and `jobs.score_reason`. Explain from those. |
| "I updated my profile", "score them again" | `python -m lavoro rescore` (the best-scored open jobs) or `python -m lavoro rescore <key> <key>`. Each job is one Claude call on the user's plan. |
| "make this email shorter", "mention my thesis" | `python -m lavoro redraft <key> --note "<what to change>"`, then show the new draft. It never touches a job marked sent. |
| "I sent it" | Only when the user says they sent it: `python -m lavoro mark <key> sent`, or **Mark as sent** on the site. The role moves to Emailed on the Tracker with a follow-up a week later. |
| "who should I follow up with?" | The Tracker page (`/tracker`) and Today list follow-ups that are due; **Write follow-up** drafts one. |
| "export these roles to Word" | `python -m lavoro export <words>`, e.g. `python -m lavoro export volvo graduate`. |
| an error, a stuck run, "it's slow" | Read `docs/troubleshooting.md` and follow it. |

## How it works

- Python package `lavoro/`. The command-line entry point is `python -m lavoro <command>`; run `--help` to see the commands.
- The AI steps call the `claude` CLI, using the user's Claude plan login, with a minimal context (see `lavoro/llm.py`). No API key is needed. The paid API is opt-in with `llm.backend: api`.
- Data lives in `data/lavoro.db` (SQLite). Personal files are gitignored: `config.yaml`, `profile.md`, `data/`, `output/`.

## Hard rules

- Never send an email or create one in someone's mailbox. Lavoro only drafts; the user sends.
- Never scrape LinkedIn or log into any site for the user. Use public job feeds, company pages, and web search only.
- Never invent facts in `profile.md` or in an email. Use only what the user gave you.
- Never commit or upload `config.yaml`, `profile.md`, `data/` or `output/`. They hold the user's personal data and the personal data of contacts.
