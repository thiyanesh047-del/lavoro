---
name: lavoro-setup
description: First-time setup of Lavoro on this computer — install, write the user's profile from their CV, set target roles and locations, build the company list, do a first run and open the local site. Use when the user says "set up Lavoro", "install this", "get started", or when config.yaml or profile.md is missing.
---

# Set up Lavoro

**The easy path.** After installing (step 1), start the site in the background:

```bash
python -m lavoro serve --open
```

Then tell the user to open http://127.0.0.1:8765. Its welcome screen does steps 2–5 for them: they drop a CV or paste a portfolio link, check the suggested roles and places, and press **Find my first jobs**.

Use the steps below when the user would rather do it here in chat, or when the browser isn't an option.

Work through these steps in order. Ask the user only what you can't find out yourself. Keep each question short.

## 1. Install

1. Check the Python version:

   ```bash
   python --version
   ```

   It needs Python 3.10 or newer.

2. Install the packages:

   ```bash
   pip install -r requirements.txt
   ```

3. Check that the `claude` command is on PATH and signed in. This runs one tiny call on the user's Claude plan:

   ```bash
   python -m lavoro ai-check
   ```

If the check fails, tell the user to install Claude Code and sign in, or to set `llm.backend: api` with an `ANTHROPIC_API_KEY`. Lavoro still runs without Claude, but it only gives rough keyword scores and template emails.

## 2. Profile (`profile.md`)

1. Ask the user for one of these:
   - their CV, as a file path in this folder;
   - pasted text from LinkedIn (profile → More → Save to PDF);
   - a few lines about themselves.

   Read any file they point to. Never fetch or scrape LinkedIn yourself.

2. Fill `profile.md`, using the headings in `profile.example.md`. Use only facts the user gave you. If something important is missing, ask once and leave it out if they skip it. Missing items:
   - years of experience;
   - languages spoken;
   - work permit or visa status.

## 3. Search settings (`config.yaml`)

The first command creates `config.yaml` from the example if it doesn't exist. Ask in one round, with the structured question tool if you have it:

- **Target roles.** Fill `titles_include` with common variants. For "ML engineer", that means "machine learning", "ml engineer", "ai engineer".
- **Seniority.** Fill `titles_exclude`. A junior or graduate keeps "senior", "staff", "lead", "head of". A senior removes "senior".
- **Locations.** Fill `locations_include`, including local spellings (Göteborg/Gothenburg, München/Munich). Also ask whether remote is fine, and in which regions (`remote_regions`).
- **Country.** If it's Sweden, set `jobtech.enabled: true`, set its `queries` to the target roles (Swedish terms too, such as "dataanalytiker"), and set `regions` (01 = Stockholm, 14 = Västra Götaland, 12 = Skåne). Set `yc.regions` to match the user's country and remote preference.
- **Their name and LinkedIn URL.** Fill `me.name` and `me.linkedin`.

## 4. Company list

These take a few minutes, so run them in the background:

```bash
python -m lavoro seed-yc
```

```bash
python -m lavoro seed-startups
```

```bash
python -m lavoro detect --limit 1000
```

Ask which companies the user would love to work at. Add each one:

```bash
python -m lavoro add <company website>
```

or

```bash
python -m lavoro probe "<name>"
```

## 5. First run and the site

1. Start a run in the background:

   ```bash
   python -m lavoro run
   ```

2. Once it finishes, start the site in the background:

   ```bash
   python -m lavoro serve --open
   ```

3. Give the user http://127.0.0.1:8765. Explain the buttons:
   - **Open in Gmail** opens a prefilled draft. The user sends it.
   - **Mark as sent** and **Not for me** save to the local database.
   - **Find new jobs** runs a fresh search.

4. Summarize what the run found: roles matched, ready emails, and the top three.

## 6. Every morning (optional)

Offer one of these:

- **Windows:** Task Scheduler runs `run_daily.bat` daily.
- **macOS/Linux:** run `chmod +x run_daily.sh`, then add this line with `crontab -e`:

  ```
  30 7 * * * <folder>/run_daily.sh
  ```

- **In Claude:** the user types `/morning-run`.

Only set up a schedule if the user says yes.

## When something goes wrong

Read `docs/troubleshooting.md` and follow it. To fix bad or missing matches, follow the `tune-search` skill.

## Rules

- Never send an email. Lavoro only drafts.
- `config.yaml`, `profile.md`, `data/` and `output/` are private and gitignored. Never commit or upload them.
- An address marked "Guessed" must be checked by the user before sending. Say so.
