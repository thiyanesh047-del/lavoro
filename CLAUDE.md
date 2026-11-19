# Lavoro

Lavoro is a job-search assistant that runs on the user's own computer. Each run it does four things:

1. Pulls new roles from company job boards: Greenhouse, Lever, Ashby, Workable, Recruitee, Teamtailor, SmartRecruiters, Workday, SAP SuccessFactors, and Sweden's Platsbanken, plus a Claude web search and a weekly check for companies that just raised money.
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

## How it works

- Python package `lavoro/`. The command-line entry point is `python -m lavoro <command>`; run `--help` to see the commands.
- The AI steps call the `claude` CLI, using the user's Claude plan login, with a minimal context (see `lavoro/llm.py`). No API key is needed. The paid API is opt-in with `llm.backend: api`.
- Data lives in `data/lavoro.db` (SQLite). Personal files are gitignored: `config.yaml`, `profile.md`, `data/`, `output/`.

## Hard rules

- Never send an email or create one in someone's mailbox. Lavoro only drafts; the user sends.
- Never scrape LinkedIn or log into any site for the user. Use public job feeds, company pages, and web search only.
- Never invent facts in `profile.md` or in an email. Use only what the user gave you.
- Never commit or upload `config.yaml`, `profile.md`, `data/` or `output/`. They hold the user's personal data and the personal data of contacts.
