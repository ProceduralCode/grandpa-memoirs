"""Generate <stories_root>/recording-summaries.md — one-line-per-recording index
that's always in Claude's context. Uses Plaud's auto-generated file_name (often
a pretty title) plus a snippet of the summary markdown when available.

Called automatically at the end of sync.py, but can also be run standalone:
    python Grandpa/scripts/generate_summaries.py
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sync.sync import load_config

SUMMARY_SNIPPET_MAX = 180  # chars per line after the title

def _find_summary_markdown(blob):
	for k, v in (blob.get('fetched_content') or {}).items():
		if k.startswith('auto_sum:') and isinstance(v, str):
			return v
	return ''

def _clean_summary_snippet(markdown):
	"""Pull a readable first-sentence-or-two out of Plaud's summary markdown.
	The summaries start with an ![PLAUD NOTE](...) image embed, then some
	headers, then prose. We skip image embeds, headers, and code, and grab the
	first substantive paragraph."""
	if not markdown:
		return ''
	lines = markdown.splitlines()
	for raw in lines:
		line = raw.strip()
		if not line:
			continue
		# Skip image embeds, headers, horizontal rules, code fences
		if line.startswith('![') or line.startswith('#') or line.startswith('---') or line.startswith('```'):
			continue
		# Strip simple markdown inline syntax (bold/italic/links)
		line = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
		line = re.sub(r'\*(.+?)\*', r'\1', line)
		line = re.sub(r'\[(.+?)\]\([^)]+\)', r'\1', line)
		line = line.strip()
		if len(line) < 10:
			continue
		if len(line) > SUMMARY_SNIPPET_MAX:
			line = line[:SUMMARY_SNIPPET_MAX].rsplit(' ', 1)[0] + '…'
		return line
	return ''

def generate(stories_root):
	recordings_dir = stories_root / 'recordings'
	if not recordings_dir.exists():
		print(f"No recordings directory at {recordings_dir}")
		return
	entries = []
	for d in sorted(recordings_dir.iterdir()):
		if not d.is_dir():
			continue
		data_path = d / 'data.json'
		if not data_path.exists():
			continue
		try:
			with open(data_path, encoding='utf-8') as f:
				blob = json.load(f)
		except (OSError, json.JSONDecodeError):
			continue
		detail = blob.get('detail') or {}
		start_ms = detail.get('start_time') or 0
		date_str = datetime.fromtimestamp(start_ms / 1000).strftime('%Y-%m-%d') if start_ms else d.name[:10]
		title = (detail.get('file_name') or d.name).strip()
		snippet = _clean_summary_snippet(_find_summary_markdown(blob))
		rec_id = d.name
		if snippet:
			entries.append(f'- `{rec_id}` · {date_str} · **{title}** — {snippet}')
		else:
			entries.append(f'- `{rec_id}` · {date_str} · **{title}**')

	out_path = stories_root / 'recording-summaries.md'
	header = (
		'# Recording index\n\n'
		'Every recording Grandpa has made so far, oldest first. Each line has:\n'
		'recording id (folder name) · date · title · short summary snippet.\n\n'
	)
	out_path.write_text(header + '\n'.join(entries) + '\n', encoding='utf-8')
	print(f"Wrote {len(entries)} entries to {out_path}")

def main():
	config = load_config()
	stories_root = Path(config['stories_root'])
	generate(stories_root)

if __name__ == '__main__':
	main()
