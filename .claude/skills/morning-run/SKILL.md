---
name: morning-run
description: Run the Lavoro pipeline (find new startup jobs, score them, find the hiring person, draft emails, build the digest) and report what is ready to send. Use when the user says "morning run", "run the job search", "find me jobs", "any new jobs", or types /morning-run in this project.
---

# Morning run

The pipeline is a Python package in this folder (`lavoro/`). Its AI steps call the `claude` command, which runs on the user's Claude plan. No API key is needed and the user is not billed per token.

## Steps

1. **Check the profile.** If `profile.md` still contains placeholder lines like `- ...` or `(expected 20XX)`, tell the user that scores and emails will be weak until they fill it in. Then carry on.

2. **Run the pipeline.** Run it in the background, since it can take several minutes:

   ```bash
   python -m lavoro run
   ```

   If the user asked for a fresh company list, or it is Monday, add `--discover`. That re-seeds the YC companies and detects their job boards first.

3. **Report.** When the run finishes, read the counts it printed. Then report:
   - New jobs found and how many passed the filter.
   - How many were scored.
   - How many have a contact and a draft ready.

   To get the top jobs, run:

   ```bash
   python -m lavoro list --min-score 7 --limit 10
   ```

4. **Show the site.** Name the top three jobs ready to send, with company, fit score and who the email goes to. Then point to http://127.0.0.1:8765. If the site isn't running, start it in the background:

   ```bash
   python -m lavoro serve --open
   ```

5. **Flag problems.** If the run printed "plan limit reached", say that the AI steps stopped early and will pick up where they left off on the next run.

## Rules

- Never send an email. The tool only drafts.
- Never mark a job as sent unless the user says they sent it. To mark one, run:

  ```bash
  python -m lavoro mark <key> sent
  ```

- Don't edit `config.yaml` or `profile.md` unless asked.
