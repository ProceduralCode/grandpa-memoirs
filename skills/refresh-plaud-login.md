# Skill: refresh-plaud-login

Walk Grandpa through refreshing his Plaud login when sync stops working.

## When to invoke

- Grandpa says sync isn't working, says he's getting "sync error," or asks why
  no new recordings are showing up.
- The sync status indicator at the top of the screen says "sync error" and
  he asks about it.
- It's been more than ~30 days since the last successful sync (the Plaud login
  token expires after ~30 days).

You don't need to run anything yourself — Grandpa runs a script by
double-clicking a file. Your job is to explain what to do, calmly and one step
at a time.

## How to walk him through it

Tell him in plain words:

1. **There's a file called `refresh-plaud.bat` in his project folder
   (`grandpa-memoirs`).** Tell him to open File Explorer, find that folder,
   and double-click `refresh-plaud.bat`. If he has a desktop shortcut for it,
   he can use that instead.
2. **A black window will pop up with instructions.** It will warn him that
   it's about to close all his Chrome windows. He presses any key when ready.
3. **Hands off the keyboard and mouse for about 20 seconds.** A Chrome window
   will pop up and close by itself — that's normal. He should not click
   anything until the script says "Success."
4. **When it says "Success,"** he can close that black window. Then reopen
   the app (the desktop shortcut, or `launch.bat`) and click **Sync**. New
   recordings should pull in.

## If it doesn't work

- If the script says it can't find Chrome profiles, tell him to make sure he's
  signed in to web.plaud.ai in Chrome. He can open Chrome, go to
  `web.plaud.ai`, and confirm his recordings show up. Then close Chrome and
  try the refresh script again.
- If the script says the session expired, tell him to sign in to
  web.plaud.ai once in Chrome, close Chrome, and run the refresh script again.
- If something else goes wrong, suggest he ask his developer (the person who
  set this up for him) to look at `sync.log` in his Stories folder.

Don't run shell commands or kill processes yourself — Grandpa does the
clicking. Your job is to translate what he should do into clear, gentle
instructions, and to listen to what he reports happening.
