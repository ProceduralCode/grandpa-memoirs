# Architecture

Why the system is shaped the way it is. The code itself is the spec for *what*
runs; this doc captures the *why* behind the non-obvious choices.

## Plaud ingest: pull from cloud, not device

The Plaud Note device auto-deletes recordings once its companion app uploads
them. Pulling via USB only ever catches unsynced files. The cloud has
everything (audio + transcripts + summaries).

Plaud has no official public API. Several reverse-engineered community tools
exist (`JamesStuder/Plaud_BulkDownloader`, `leonardsellem/plaud-sync-for-obsidian`,
`sergivalverde/plaud-toolkit`, `josephhyatt/plaud-exporter`). We didn't take a
wholesale dependency on any of them — instead we wrote a small client of our
own (`sync/plaud_client.py`, ~150 lines) referencing those projects for the API
patterns. When Plaud changes the unofficial API, we know exactly what to fix.

A local JSON manifest tracks what's been downloaded so subsequent syncs are
incremental.

## Plaud auth: Chrome profile extraction, not email/password

The target user signed into Plaud via Sign-in-with-Google, and Plaud's UI
offers no way to add an email+password login method to an SSO account. So we
work around it:

1. A Chrome profile on the user's machine is signed into the Google account
   that owns the Plaud account.
2. `sync/chrome_token.py` copies that profile to a temp directory (so it can
   run Chrome independently of any running browser instance), launches Chrome
   with `--remote-debugging-port` and `--remote-allow-origins=*`, opens a fresh
   `web.plaud.ai` tab via CDP, and reads the JWT out of
   `localStorage['tokenstr']`.
3. The token is cached at `.plaud-token`.
4. `PlaudClient` is constructed with an `on_token_expired` callback that
   invalidates the cache and re-extracts. The callback runs transparently on
   401/403 responses (or body-level `-401`/`-403`). No time-based polling — the
   refresh is purely reactive.
5. When the Chrome profile's session itself expires, the token-extraction
   script lands on a Google sign-in page and raises a clear error. The user
   re-signs-in to web.plaud.ai in that profile, then runs again.

JWT decoder lives in `plaud_client.py` as `jwt_expiry_seconds` — one source of
truth, used by both the client and the cache.

## Claude Code invocation: per-request subprocess

Each user message → one `claude -p "<prompt>"` subprocess. Conversation history
is managed by us and replayed in the prompt every turn. Simpler than
maintaining a persistent process, easier to debug, more reliable across long
sessions.

The chat endpoint uses `--output-format stream-json --include-partial-messages`
so the backend can forward `text_delta` events to the browser as Server-Sent
Events for live streaming. Without this, `claude -p` buffers stdout until
completion when stdout is a pipe.

`--permission-mode acceptEdits` is set so the model can write memoir files into
the stories dir without blocking on a permission prompt that nobody can
answer in non-interactive mode.

## Prompt composition

Human-written instructions live in `prompts/` (system + task) and `skills/`
(playbooks). Per-machine context (`bio.md`, `recording-summaries.md`) lives in
the user's `stories_root`. The backend's `web/prompts.py` reads all of these
on every turn and inlines them into the prompt — no caching, no symlinks. The
subprocess CWD is the stories dir so Claude can `Read` the actual recordings
and `Write` memoirs there.

Prompt templates are markdown files, not Claude Code slash commands. Easier to
maintain, easier to test, decoupled from Claude Code internals.

## Archival data shape: opt-out, not opt-in

Each recording is stored as `recordings/YYYY-MM-DD_HH-MM-SS/{audio.mp3, data.json}`.

`data.json` is `{detail, fetched_content}`:

- **`detail`** = the raw Plaud `/file/detail/<id>` response verbatim, minus
  two clearly-discardable things: `embeddings` (opaque vectors we can't use
  without Plaud's model) and the `data_link` URLs inside `content_list` entries
  (presigned S3 URLs that expire within hours).
- **`fetched_content`** = dict keyed by `data_id` containing the resolved
  content of every `content_list` entry with `task_status == 1`. Transcript
  segments live at `source_transaction:...`, the AI summary at `auto_sum:...`,
  highlights at `note:...`, etc.

We deliberately *don't* decompose into `transcript.txt`, `summary.md`,
`metadata.json` separate files at ingest time. Future analyses might want
fields we didn't think were important now; an opt-out approach (save everything
that survives URL expiry) preserves optionality. Derived views (plain-text
transcripts, speaker-formatted output) are computed at read time.

## Web app launcher: on-demand, not auto-start

A single shortcut runs `launch.py`, which:

1. Checks if the backend is already listening on port 8000 — if so, skips
   startup, just opens the browser. Idempotent: double-tap doesn't crash.
2. Otherwise starts the FastAPI backend as a detached subprocess in a new
   console.
3. Waits up to 10 seconds for `/api/health` to respond.
4. Opens the default browser to `http://localhost:8000/`.

FastAPI cold-start is ~1–2s, negligible. The backend stays running until
reboot (we have no idle-timeout shutdown — simpler).

Rejected: Windows service (overkill, debug-hostile), startup-folder auto-start
(always-on overhead, more state to manage), uvicorn `--reload` (flaky on
Windows; orphaned multiprocessing workers held the port and served stale code
across taskkill attempts during development). The server is restarted via
`POST /api/shutdown` (graceful, sets `uvicorn.Server.should_exit = True`)
instead of `taskkill /F`.

## Voice input: Web Speech API in-browser

Voice is the headline accessibility feature (shaky-hand users want to minimize
keyboard). We use the browser's built-in Web Speech API rather than a local
Whisper install — zero setup, instant feature, decent quality. Permissions
persist across sessions because we serve from `http://localhost:8000` rather
than `file://`.

Falls back to text input if the browser doesn't support it (mic button is
hidden by feature-detection). Chrome and Edge both support it on Windows.

## Sync ground truth and retry behavior

The Plaud list endpoint's `is_trans` flag is *not* trustworthy in isolation —
some recordings get flagged transcribed but the detail response still has no
fetchable transcript content. The manifest tracks `is_trans_captured` based on
the actual presence of segments in `fetched_content["source_transaction:..."]`,
not the flag.

To avoid hammering the detail endpoint forever for recordings stuck in that
limbo state, the manifest also stores `last_detail_attempt_at`. We back off
re-fetching for 24h after a no-transcript detail call.

A lock file (`sync.lock`) prevents concurrent sync runs from a scheduler firing
overlapping instances. Stale after 30 minutes.

## Risks we know about

- **Plaud unofficial API drift.** Could change without notice. Mitigation: the
  client is small and contained — we'd patch one file.
- **Token revocation outside our control.** Logging out elsewhere kills our
  cached token. Reactive refresh handles it gracefully via the callback.
- **Web Speech API outages.** Sends audio to Google's servers; could fail. Text
  fallback always visible.
- **Backend crash mid-session.** Frontend shows a clear "offline" indicator;
  user re-taps the desktop shortcut to relaunch.
- **Disk fill.** Every MP3 is ~4MB per 15min recording. Not addressed in v1 —
  noted for the user to monitor.

## Conventions

Tabs for indentation. Braces on the same line. Minimize comments — explain
*why* not *what*. All paths flow from `config.json`, never hardcoded. The
Plaud client and Chrome token extractor are isolated in single files for easy
fixes when their unofficial APIs change.
