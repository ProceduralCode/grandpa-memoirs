# Skill: write-memoir

Compose and save a memoir — a cleanly-written markdown essay woven from one or more of Grandpa's recordings.

## When to invoke

- Grandpa explicitly asks ("write me a memoir about X", "can you capture that as a memoir?").
- A conversational thread has produced enough material that a memoir would preserve it well, and Grandpa agrees when offered.
- Emerson (the developer) asks you to write one.

Never write a memoir unprompted. Never overwrite an existing memoir — multiple memoirs on the same topic can coexist; each has its own timestamp.

## Scope

The memoir can be anchored on:
- A topic ("my time in the Navy")
- A person ("stories about my brother John")
- An era ("childhood in Oklahoma")
- A specific recording or set of recordings
- A theme drawn from the conversation you've just had

If the scope is ambiguous, ask one clarifying question before writing. Don't guess.

## How to write it

1. Use the recording summaries to find recordings in scope.
2. Read the relevant full transcripts from `recordings/<id>/data.json`. Transcript segments live at `fetched_content["source_transaction:..."]` as a list.
3. Weave them into a coherent narrative. Do not paste transcript verbatim — rewrite in clean prose while staying faithful to the voice, facts, names, and sequence Grandpa gave.
4. First person. It's his memoir, in his voice.
5. Never invent details. If something's unclear, omit it or leave it unclear — don't smooth over gaps with plausible fiction.
6. If two recordings cover the same event differently, reconcile where possible; note the discrepancy where not.
7. Plain readable prose. `##` subsections are fine for longer memoirs. No bullet lists in the body unless the content is genuinely a list.

## Output format

Save to `memoirs/<timestamp>_<slug>.md` inside the current working directory.

- Filename: `YYYY-MM-DD_HH-MM-SS_short-slug.md` using the current timestamp. (No colons — not valid on Windows filesystems.)
- Slug: lowercase, hyphen-separated, derived from the title. Short — 3-5 words max.

Body format:

```
---
title: "Human-readable title"
date_written: YYYY-MM-DD
era: childhood
topics: [family, fishing]
source_recordings:
  - 2025-08-14_09-30-12
  - 2025-08-20_14-15-33
summary: One-sentence summary shown in the memoir list.
---

# Human-readable title

Memoir body in first person...
```

Frontmatter fields:

- `title` — required. Title-case, reads well.
- `date_written` — required. Today's date.
- `era` — optional. One of: `childhood`, `youth`, `army`, `career`, `family`, `later`. Omit if it spans eras.
- `topics` — optional. Short tags for filtering.
- `source_recordings` — required. List of recording IDs (folder names like `2025-08-14_09-30-12`) you drew from.
- `summary` — required. One sentence. This shows in the memoir list view, so it needs to read well on its own.

## After saving

Tell Grandpa (or Emerson) you've saved it and give the filename. Briefly describe what's in it — one or two sentences. Don't dump the full text into chat; he can read it on the Memoirs screen.
