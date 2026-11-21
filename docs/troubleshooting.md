# Troubleshooting

Each problem below starts with what you see, then what to do. Claude Code reads this page when something goes wrong, so you can also just say "Lavoro is broken" in this folder.

## Claude does not answer

**You see:** `no Claude: the claude command was not found on PATH`, or scores that say "rough keyword score".

1. Install [Claude Code](https://claude.com/claude-code) and sign in with your Claude account.
2. Close and reopen the terminal, so the `claude` command is on PATH.
3. Check:

   ```bash
   python -m lavoro ai-check
   ```

Lavoro still runs without Claude, but it only gives keyword scores and template emails. To use the paid API instead, set `llm.backend: api` in `config.yaml` and put your key in the `ANTHROPIC_API_KEY` environment variable.

## The plan limit was reached

**You see:** `Claude plan limit reached, stopping AI steps for this run`.

Nothing is lost. Jobs that were not scored or drafted stay in the queue, and the next run picks them up once your plan's limit resets. To use less per run, lower `llm.max_jobs_to_score_per_run` and `contacts.max_jobs_per_run` in `config.yaml`.

## "Another Lavoro run is already going"

Only one run can go at a time. The lock is released as soon as the run's process ends, even if it crashed.

1. Wait a few minutes: a first run, or a run after `--discover`, is long (see below).
2. If you started it from the site, the **Find new jobs** button shows the step it is on.
3. If you are sure no run is going, look for a leftover `python` process (Windows: Task Manager; macOS/Linux: `ps aux | grep lavoro`) and end it. Don't delete `data/run.lock` while a run might still be going.

## The first run is slow

The first run (or a run with `--discover`) builds the company list and then reads every job board: about 6,900 boards, from the Y Combinator list and the bundled startup list. Reading them took 7 minutes in a test (418 seconds for 6,926 boards on a home connection); the first run also finds job boards for new companies and scores roles, so expect 15 minutes or more. Later runs are quicker: boards where no role has ever passed your filter are read once every 3 days (`search.quiet_boards_every_days`), a third of them each day, while companies you follow and boards with roles that fit are read every run. `python -m lavoro fetch --all` reads every board now. Run it in the background, or on a schedule (see the README).

To keep the bundled list out of a new setup, turn it off in `config.yaml` before the first run. Companies already added stay in your list.

```yaml
search:
  startups:
    enabled: false
```

## The site does not open

**You see:** `Port 8765 is already in use`.

The site is probably already running. Open http://127.0.0.1:8765. To run a second copy, use another port:

```bash
python -m lavoro serve --port 8766
```

If the page shows old content after an update, stop every running copy of the site (close its terminal, or end its `python` process) and start it again.

## "database is locked"

The site and a run share `data/lavoro.db`. Lavoro waits up to a minute for the other side to finish writing. If the message keeps coming, a run or a script is still holding the database: let it finish, or end that process.

## A company shows no roles

- Its job board may be one Lavoro cannot read. It reads Greenhouse, Lever, Ashby, Workable, Recruitee, Teamtailor, SmartRecruiters, Workday and SAP SuccessFactors.
- Workday and SuccessFactors boards cannot be guessed from a name. Paste the careers link:

  ```bash
  python -m lavoro add https://company.wd3.myworkdayjobs.com/Careers
  ```

## Logos are missing

Logos are fetched at the end of each run for companies with open roles. To fetch the missing ones now:

```bash
python -m lavoro logos
```

A company keeps its first letter when no logo can be found on its own website.

## Too few or the wrong matches

Say "tune my search" to Claude in this folder. The `tune-search` skill finds where jobs drop out and suggests what to change. In short:

- After changing titles or places in `config.yaml`: `python -m lavoro refilter`, then `python -m lavoro match`.
- After changing `profile.md`: `python -m lavoro rescore`.

## Gmail drafts are not created

`email.gmail_drafts: true` needs `pip install -r requirements-gmail.txt` and a `credentials.json` from Google Cloud in this folder (see `lavoro/gmail.py`). Without it, open each draft with **Open in Gmail** on the site.
