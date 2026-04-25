# Task: compose bio.md

You're going to read Grandpa's existing recordings and synthesize a biographical
blurb that will live at `<stories_root>/bio.md`. Every future Claude invocation
in this project will load that file into context, so the goal is: everything
the model needs to know about this person to have a grounded conversation,
nothing more.

## Before you start

Run this to get oriented:
1. Read `<stories_root>/recording-summaries.md` — the one-line-per-recording
   index. Gives you the full shape of what's been captured.
2. Skim representative `<stories_root>/recordings/<id>/data.json` files for
   recordings whose titles suggest biographical content. The transcript segments
   live at `fetched_content["source_transaction:..."]` as a list. Each segment
   has `speaker`, `content`, `start_time` (ms), `end_time` (ms).

Start broad (scan summaries) and only open full transcripts when you need the
detail. You don't need to read all 80+ recordings — sample across eras.

## What bio.md should contain

Write in third person. Neutral, factual, grounded. No fluff, no embellishment.
Organize by era or theme, whichever reads more naturally. Cover:

- **Name** and how he's addressed in the app (Bill Peters / Grandpa / etc.).
- **Core biographical frame**: roughly when and where he was born, grew up,
  lives now; family structure at a high level.
- **Career arc**: the major jobs, employers, fields. He's a physicist / engineer
  with a varied career; his recordings mention specific programs (e.g. Hubble,
  PerkinElmer, Sarajevo aerial monitoring). Get the sequence and context right.
- **Key periods or themes** that recur in the recordings — military service,
  academic pivots, international work, specific projects, important people
  (coworkers, rivals, friends).
- **Voice and manner** — a short paragraph on how he tells stories. Dry? Wry?
  Detailed? Reflective? Claude needs this to respond in register.
- **Topics he's been talking about recently** vs. periods barely touched — so
  Claude knows where the gaps are.

Explicitly DO NOT include:
- Anything you can't ground in a recording or have high confidence in.
- Speculation about feelings, motivations, or private relationships.
- Health / medical information unless he has directly stated it.
- Any personally identifying details beyond what's already in his recordings
  (no street addresses, no phone numbers, no SSNs if somehow mentioned).

## Length and format

Aim for 600–1200 words. Plain markdown. Use short section headers (`##`) if it
helps organization, but prose is fine if the life reads naturally as a story.
No bullet-list dumps — the output should read as prose a human wrote.

When you finish, save to `<stories_root>/bio.md`. Don't overwrite an existing
bio.md without asking — if one exists, read it first and see whether you're
extending it, correcting it, or the existing one is fine as-is.

## After saving

Report: word count, what eras/themes you covered, what gaps you noticed (areas
where the recordings were thin or absent). That gap note is useful on its own —
it tells us what to prompt him to record next.
