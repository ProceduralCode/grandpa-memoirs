"""Persistent chat conversations, one file per conversation.

Conversations live at <stories_root>/conversations/<id>.json. Each file holds
the full message history; we build a new prompt from it on every turn because
`claude -p` is stateless. No database, no index file — list operations just
scan the directory.
"""
import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

def conversations_dir(stories_root):
	d = Path(stories_root) / 'conversations'
	d.mkdir(parents=True, exist_ok=True)
	return d

def now_iso():
	return datetime.now(timezone.utc).isoformat(timespec='seconds')

def new_id():
	"""Timestamp-prefixed ID sorts chronologically and is unique."""
	return f"conv-{int(time.time())}-{secrets.token_hex(3)}"

def conv_path(stories_root, conv_id):
	return conversations_dir(stories_root) / f'{conv_id}.json'

def load(stories_root, conv_id):
	p = conv_path(stories_root, conv_id)
	if not p.exists():
		return None
	try:
		with open(p, encoding='utf-8') as f:
			return json.load(f)
	except (OSError, json.JSONDecodeError):
		return None

def save(stories_root, conv):
	p = conv_path(stories_root, conv['id'])
	p.write_text(json.dumps(conv, indent=2), encoding='utf-8')

def create(stories_root, title=None):
	conv_id = new_id()
	now = now_iso()
	conv = {
		'id': conv_id,
		'title': title or 'New conversation',
		'created_at': now,
		'updated_at': now,
		'messages': [],
	}
	save(stories_root, conv)
	return conv

def list_all(stories_root):
	"""Return conversations sorted by updated_at desc."""
	results = []
	for f in conversations_dir(stories_root).glob('conv-*.json'):
		try:
			with open(f, encoding='utf-8') as fh:
				data = json.load(fh)
		except (OSError, json.JSONDecodeError):
			continue
		results.append({
			'id': data.get('id'),
			'title': data.get('title'),
			'created_at': data.get('created_at'),
			'updated_at': data.get('updated_at'),
			'message_count': len(data.get('messages', [])),
		})
	results.sort(key=lambda r: r.get('updated_at') or '', reverse=True)
	return results

def delete(stories_root, conv_id):
	p = conv_path(stories_root, conv_id)
	if p.exists():
		p.unlink()
		return True
	return False

def build_prompt(conv, new_user_content):
	"""Format the full prompt to send to claude -p for the next turn.

	Structure: a single text prompt that lays out prior messages as role-tagged
	blocks, then the new user message. Claude's instruction-following handles
	this reliably without any special session-format magic."""
	lines = []
	prior = conv.get('messages') or []
	if prior:
		lines.append('[Prior conversation in this session]')
		for m in prior:
			role = m.get('role', 'user').capitalize()
			content = (m.get('content') or '').strip()
			lines.append(f'{role}: {content}')
			lines.append('')
	lines.append('[New message from user]')
	lines.append(new_user_content.strip())
	lines.append('')
	lines.append('Respond as the assistant. Be concise and conversational.')
	return '\n'.join(lines)
