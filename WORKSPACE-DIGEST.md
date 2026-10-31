# Personal Workspace daily digest (Draft integration)

This repository is **public**. The new `docs/daily-digest.json` is therefore public when it is published. It must contain only article categories, source labels, concise AI summaries, HTTPS source links, stable hashes and generation metadata. It must **never** contain mail addresses, app tokens, prompts, full feed bodies, health records or user profile data.

## Producer

`rss_digest.py` keeps the existing email workflow and creates a plain-text JSON file from the **same** summarization results (without additional LLM calls). The JSON producer refuses non-HTTPS links and unknown categories, limits record lengths and count, deduplicates by hashed URL, writes atomically and retains the previous successful snapshot when no valid entries exist. Email sending is not gated on the export's success.

The scheduled job runs the public-contract tests, then sends the existing digests. Only on `main` it commits `docs/daily-digest.json` (no other generated RSS, logs or files). Running a branch's workflow manually does **not** publish to `main`. The repository's Actions permissions must permit `GITHUB_TOKEN` to write contents; branch rules can also block the push. A green scheduled run must be checked for its **Publish public workspace digest** step, not only its email step.

## Consumer and limits

After the publication PR is reviewed and merged, Personal Workspace reads this **public URL**, without a token:

`https://raw.githubusercontent.com/fayeyifan-coder/RSS-GPT/main/docs/daily-digest.json`

`schemaVersion: 1`, `sourceApp: "RSS-GPT"`, UTC `generatedAt`, Beijing `reportDate`, `timeZone`, and an array of `{id, category, source, title, summary, url}` records form the bounded contract. The workspace separately validates, caches, and marks outdated or unavailable snapshots. `generatedAt` is **export time**, not proof an individual article was published that day.

## Verification and rollback

- Run `python -m unittest discover -s tests -v` before deployment.
- Use `workflow_dispatch` on this branch to check that email behavior still works while no source commit is published.
- After explicit approval and merge, verify a scheduled run updates only the intended JSON, the URL returns a valid snapshot and the workspace shows its real generation date.
- Rollback: revert this PR; keep the last published file until reviewed deletion. The workspace then shows cached content as old, rather than inventing a fresh headline.

This PR must remain Draft until the above review and explicit approval. No API key, token, public-file visibility change or external deployment is requested here.
