"""Generate leading questions for the Ideas screen.

Runs a `claude -p` subprocess with the leading-questions prompt (composed from
_system.md + bio + recording-summaries + leading-questions.md). Writes the
model's output to `<stories_root>/leading-questions/current.md`. Called either
manually, from the UI's Regenerate button, or automatically at end of sync.
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sync.sync import load_config
from web.prompts import compose_leading_questions_prompt

CLAUDE_TIMEOUT_SECONDS = 300

def _trim_to_list(text):
	"""Claude sometimes ignores 'no preamble' and writes prose before the list.
	Trim everything before the first markdown list item."""
	lines = text.splitlines()
	for i, line in enumerate(lines):
		stripped = line.lstrip()
		if stripped.startswith('- ') or stripped.startswith('* '):
			return '\n'.join(lines[i:]).rstrip()
		if stripped[:2].isdigit() or (stripped[:1].isdigit() and stripped[1:3] in ('. ', ') ')):
			return '\n'.join(lines[i:]).rstrip()
	return text

def _extract_prior_questions(path):
	"""Collect every markdown list item from prior batches in current.md so we
	can tell Claude not to repeat them. Returns a de-duplicated list preserving
	order of appearance."""
	if not path.exists():
		return []
	try:
		text = path.read_text(encoding='utf-8')
	except OSError:
		return []
	seen = set()
	result = []
	for line in text.splitlines():
		stripped = line.lstrip()
		if stripped.startswith('- '):
			q = stripped[2:].strip()
		elif stripped.startswith('* '):
			q = stripped[2:].strip()
		else:
			continue
		if q and q not in seen:
			seen.add(q)
			result.append(q)
	return result

def find_claude_path(override=None):
	"""Mirror of web/server.py's resolver — kept local so this script has no
	FastAPI dependency."""
	if override and Path(override).exists():
		return override
	which = shutil.which('claude')
	if which:
		return which
	local_appdata = os.environ.get('LOCALAPPDATA')
	if local_appdata:
		for pkg in (Path(local_appdata) / 'Packages').glob('Claude_*'):
			versions_dir = pkg / 'LocalCache' / 'Roaming' / 'Claude' / 'claude-code'
			if not versions_dir.exists():
				continue
			for d in sorted((x for x in versions_dir.iterdir() if x.is_dir()), reverse=True):
				candidate = d / 'claude.exe'
				if candidate.exists():
					return str(candidate)
	return None

def generate(stories_root):
	claude = find_claude_path(load_config().get('claude_path'))
	if not claude:
		raise RuntimeError("Could not locate the claude CLI. Set claude_path in config.json.")
	prompt = compose_leading_questions_prompt(stories_root)

	# Feed prior questions back in as a "don't repeat" list so each regeneration
	# pushes for genuinely new angles rather than rehashing the same obvious ones.
	out_path_preview = stories_root / 'leading-questions' / 'current.md'
	prior = _extract_prior_questions(out_path_preview)
	if prior:
		avoid = [
			'',
			'---',
			'',
			'# Previously-suggested questions — do NOT repeat any of these',
			'',
			'This batch is the Nth regeneration in a running series; Grandpa has already seen the questions below. Produce this round from DIFFERENT angles, eras, people, or sensory details. If the well is genuinely dry in some area, pivot to another era or a less-covered theme rather than rephrasing a question below.',
			'',
		] + [f'- {q}' for q in prior]
		prompt = prompt + '\n' + '\n'.join(avoid)
		print(f"  (feeding back {len(prior)} prior questions to avoid)")

	print(f"Running claude to generate leading questions (~{len(prompt)} chars of context)...")
	# Pipe prompt via stdin to avoid Windows' ~32KB command-line argument limit.
	result = subprocess.run(
		[claude, '-p'],
		cwd=str(stories_root),
		input=prompt,
		capture_output=True,
		text=True,
		timeout=CLAUDE_TIMEOUT_SECONDS,
		encoding='utf-8',
		errors='replace',
	)
	if result.returncode != 0:
		raise RuntimeError(f"claude failed (exit {result.returncode}): {result.stderr[:500]}")
	output = (result.stdout or '').strip()
	if not output:
		raise RuntimeError("claude returned no output")
	output = _trim_to_list(output)

	out_dir = stories_root / 'leading-questions'
	out_dir.mkdir(parents=True, exist_ok=True)
	out_path = out_dir / 'current.md'

	# Prepend the new set as a dated section; keep prior sets below.
	local_now = datetime.now()
	section_header = f"## {local_now.strftime('%b %-d, %Y · %-I:%M %p')}" if sys.platform != 'win32' else \
		f"## {local_now.strftime('%b %#d, %Y · %#I:%M %p')}"
	new_section = f"{section_header}\n\n{output}\n"

	prior = ''
	if out_path.exists():
		try:
			existing = out_path.read_text(encoding='utf-8')
		except OSError:
			existing = ''
		# Drop any legacy HTML comment lines at the top
		lines = existing.splitlines()
		while lines and (not lines[0].strip() or lines[0].lstrip().startswith('<!--')):
			lines.pop(0)
		prior = '\n'.join(lines).strip()

	combined = new_section + ('\n' + prior + '\n' if prior else '')
	out_path.write_text(combined, encoding='utf-8')
	print(f"Wrote {out_path} (+{len(output)} chars, total {len(combined)})")

def main():
	config = load_config()
	stories_root = Path(config['stories_root'])
	generate(stories_root)

if __name__ == '__main__':
	main()
