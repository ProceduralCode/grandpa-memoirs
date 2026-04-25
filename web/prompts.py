"""Compose full prompts for `claude -p` invocations.

We keep all human-written instructions (system prompt, task prompts, skill
playbooks) as standalone markdown files in `Grandpa/prompts/` and
`Grandpa/skills/`. Claude's CWD is the user's stories root (so it can Read
recordings/*, memoirs/*, etc.) but those source folders are outside that tree
— the backend reads and inlines them into every prompt instead.

Inlined per turn:
  - prompts/_system.md        — system-level orientation
  - prompts/ask.md            — task prompt for the chat flow
  - skills/write-memoir.md    — memoir-writing playbook, always available
  - <stories_root>/bio.md                  — biographical blurb (if present)
  - <stories_root>/recording-summaries.md  — one-line-per-recording index

Plus the conversation history and the new user message.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PROMPTS_DIR = PROJECT_ROOT / 'prompts'
SKILLS_DIR = PROJECT_ROOT / 'skills'

def _read(path, fallback=''):
	try:
		return Path(path).read_text(encoding='utf-8').strip()
	except (OSError, FileNotFoundError):
		return fallback

def _context_blocks(stories_root):
	"""Shared preamble used by both chat and generation prompts."""
	system_md = _read(PROMPTS_DIR / '_system.md')
	memoir_md = _read(SKILLS_DIR / 'write-memoir.md')
	bio_md = _read(stories_root / 'bio.md', '_(bio.md not yet written — ask the user about himself when relevant rather than assuming)_')
	summaries_md = _read(stories_root / 'recording-summaries.md', '_(no recording-summaries.md yet — generate with scripts/generate_summaries.py)_')
	return [
		system_md,
		'',
		'# About the user (bio.md)',
		'',
		bio_md,
		'',
		'# Recording index (recording-summaries.md)',
		'',
		summaries_md,
		'',
		'# Skill: write-memoir',
		'',
		memoir_md,
	]

def compose_chat_prompt(stories_root, conversation, new_user_message):
	"""Build the prompt for one turn of Talk with Claude."""
	ask_md = _read(PROMPTS_DIR / 'ask.md')
	parts = _context_blocks(Path(stories_root)) + [
		'',
		'---',
		'',
		'# Task',
		'',
		ask_md,
	]
	history = conversation.get('messages') or []
	if history:
		parts += ['', '# Conversation so far', '']
		for m in history:
			role = (m.get('role') or 'user').capitalize()
			content = (m.get('content') or '').strip()
			parts.append(f'**{role}:** {content}')
			parts.append('')
	parts += [
		'# New message from user',
		'',
		new_user_message.strip(),
		'',
		'Respond as the assistant.',
	]
	return '\n'.join(parts)

def compose_leading_questions_prompt(stories_root):
	"""Build the prompt for generating leading questions for the Ideas screen."""
	task_md = _read(PROMPTS_DIR / 'leading-questions.md')
	parts = _context_blocks(Path(stories_root)) + [
		'',
		'---',
		'',
		'# Task',
		'',
		task_md,
	]
	return '\n'.join(parts)
