"""FastAPI backend for the Grandpa web UI.

Endpoints:
  GET  /api/health                             liveness check
  GET  /api/status                             sync-status.json contents
  GET  /api/conversations                      list (id, title, updated_at, count)
  POST /api/conversations                      create; returns the new conversation
  GET  /api/conversations/{id}                 full conversation with messages
  POST /api/conversations/{id}/messages        send user message; SSE streams response
  DELETE /api/conversations/{id}               delete

Claude invocations:
  - Spawned as subprocess of `claude -p <prompt>` with CWD = stories_root.
  - Prompt is built fresh each turn from the conversation's history (claude -p is
    stateless), via conversations.build_prompt.
  - Response is streamed to the client as Server-Sent Events; the full assistant
    message is appended to the conversation only after the stream completes.
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from sync.sync import load_config
from web import conversations as convo
from web.prompts import compose_chat_prompt

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
CLAUDE_TIMEOUT_SECONDS = 300

def find_claude_path(override=None):
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

_CLAUDE_PATH = None

def claude_path():
	global _CLAUDE_PATH
	if _CLAUDE_PATH is None:
		_CLAUDE_PATH = find_claude_path(load_config().get('claude_path'))
	return _CLAUDE_PATH

def stories_root():
	root = Path(load_config()['stories_root'])
	root.mkdir(parents=True, exist_ok=True)
	return root

app = FastAPI(title='Grandpa Backend')
app.add_middleware(
	CORSMiddleware,
	allow_origins=['*'],
	allow_methods=['*'],
	allow_headers=['*'],
)

class CreateConvRequest(BaseModel):
	title: Optional[str] = None

class MessageRequest(BaseModel):
	content: str

@app.get('/api/health')
def health():
	return {'ok': True}

@app.post('/api/shutdown')
def shutdown():
	"""Graceful shutdown — used instead of taskkill. Tells the running uvicorn
	Server to exit its loop after the current request; the event loop winds
	down normally. No orphaned workers, no zombie sockets."""
	server = getattr(app.state, 'uvicorn_server', None)
	if server is None:
		return {'status': 'no_server_reference'}
	server.should_exit = True
	return {'status': 'shutting_down'}

@app.get('/api/status')
def status():
	path = stories_root() / 'sync-status.json'
	if not path.exists():
		return {'has_status': False}
	try:
		with open(path, encoding='utf-8') as f:
			return {'has_status': True, **json.load(f)}
	except (OSError, json.JSONDecodeError) as e:
		return {'has_status': False, 'error': str(e)}

SYNC_LOCK_STALE_SECONDS = 30 * 60
SYNC_SCRIPT = PROJECT_ROOT / 'sync' / 'sync.py'
IDEAS_SCRIPT = PROJECT_ROOT / 'scripts' / 'generate_leading_questions.py'

@app.post('/api/sync')
def trigger_sync():
	"""Kick off sync.py as a detached subprocess. Returns immediately.
	The sync writes progress to sync-status.json which the UI polls."""
	root = stories_root()
	lock = root / 'sync.lock'
	if lock.exists():
		try:
			age = time.time() - lock.stat().st_mtime
		except OSError:
			age = 0
		if age < SYNC_LOCK_STALE_SECONDS:
			return {'status': 'already_running'}
	log_path = root / 'sync.log'
	flags = 0
	exe = sys.executable
	if sys.platform == 'win32':
		flags = subprocess.CREATE_NO_WINDOW
		if exe.lower().endswith('pythonw.exe'):
			exe = exe[:-len('pythonw.exe')] + 'python.exe'
	log_file = open(log_path, 'ab')
	subprocess.Popen(
		[exe, str(SYNC_SCRIPT)],
		cwd=str(PROJECT_ROOT),
		stdout=log_file,
		stderr=subprocess.STDOUT,
		creationflags=flags,
	)
	return {'status': 'started'}

def safe_subpath(subdir_name, recording_or_memoir_id):
	"""Return the filesystem path for a user-provided id, rejecting anything
	that would escape the intended directory via path traversal."""
	if not recording_or_memoir_id or '/' in recording_or_memoir_id or '\\' in recording_or_memoir_id or '..' in recording_or_memoir_id:
		raise HTTPException(status_code=400, detail='invalid id')
	return stories_root() / subdir_name / recording_or_memoir_id

def _find_transcript_segments(blob):
	for k, v in (blob.get('fetched_content') or {}).items():
		if k.startswith('source_transaction:') and isinstance(v, list) and v:
			return v
	return []

def _find_summary_markdown(blob):
	for k, v in (blob.get('fetched_content') or {}).items():
		if k.startswith('auto_sum:') and isinstance(v, str) and v:
			return v
	return ''

@app.get('/api/recordings')
def list_recordings():
	"""List all locally-archived recordings, most recent first."""
	root = stories_root() / 'recordings'
	items = []
	if not root.exists():
		return items
	for d in sorted(root.iterdir(), reverse=True):
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
		items.append({
			'id': d.name,
			'title': detail.get('file_name') or d.name,
			'duration_ms': detail.get('duration') or 0,
			'start_time_ms': detail.get('start_time') or 0,
			'has_transcript': bool(_find_transcript_segments(blob)),
			'has_audio': (d / 'audio.mp3').exists(),
		})
	return items

@app.get('/api/recordings/{recording_id}')
def get_recording(recording_id: str):
	rec_dir = safe_subpath('recordings', recording_id)
	data_path = rec_dir / 'data.json'
	if not data_path.exists():
		raise HTTPException(status_code=404, detail='recording not found')
	with open(data_path, encoding='utf-8') as f:
		blob = json.load(f)
	detail = blob.get('detail') or {}
	return {
		'id': recording_id,
		'title': detail.get('file_name') or recording_id,
		'duration_ms': detail.get('duration') or 0,
		'start_time_ms': detail.get('start_time') or 0,
		'transcript_segments': _find_transcript_segments(blob),
		'summary_markdown': _find_summary_markdown(blob),
		'has_audio': (rec_dir / 'audio.mp3').exists(),
	}

@app.get('/api/recordings/{recording_id}/audio')
def get_recording_audio(recording_id: str):
	rec_dir = safe_subpath('recordings', recording_id)
	audio_path = rec_dir / 'audio.mp3'
	if not audio_path.exists():
		raise HTTPException(status_code=404, detail='audio not found')
	return FileResponse(str(audio_path), media_type='audio/mpeg')

def _split_frontmatter(text):
	"""Split '---\\nkey: val\\n...\\n---\\nbody' into (meta_dict, body_str).
	If the file has no frontmatter, returns ({}, original_text)."""
	if not text.startswith('---'):
		return {}, text
	try:
		_, fm, body = text.split('---', 2)
		meta = yaml.safe_load(fm) or {}
		if not isinstance(meta, dict):
			meta = {}
		return meta, body.lstrip('\n')
	except (ValueError, yaml.YAMLError):
		return {}, text

def _memoir_summary_from_meta_or_body(meta, body):
	"""Prefer the summary from frontmatter; else take the first prose line."""
	s = meta.get('summary')
	if s:
		return str(s)
	for raw in body.splitlines():
		line = raw.strip()
		if not line or line.startswith('#') or line.startswith('---'):
			continue
		return line[:200]
	return ''

@app.get('/api/ideas')
def get_ideas():
	"""Read the latest leading-questions/current.md for the Ideas screen."""
	path = stories_root() / 'leading-questions' / 'current.md'
	if not path.exists():
		return {'exists': False, 'content': '', 'updated_at': None}
	try:
		content = path.read_text(encoding='utf-8')
	except OSError as e:
		raise HTTPException(status_code=500, detail=str(e))
	return {
		'exists': True,
		'content': content,
		'updated_at': datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec='seconds'),
	}

def _split_ideas_sections(text):
	"""Break current.md into sections that mirror what the UI renders.
	Section 0 is everything before the first '## ' line (the pre-header intro
	or a legacy un-headered batch); sections 1..N are each '## ' block.
	Returns a list of strings. Empty leading section is included only if it has
	any content beyond whitespace/comments."""
	lines = text.splitlines(keepends=True)
	sections = []
	current = []
	for line in lines:
		if line.startswith('## '):
			if current:
				sections.append(''.join(current))
				current = []
		current.append(line)
	if current:
		sections.append(''.join(current))
	# Drop a leading section that's empty or comment-only — it isn't rendered either
	if sections and not sections[0].lstrip().startswith('## '):
		meaningful = any(
			line.strip() and not line.lstrip().startswith('<!--')
			for line in sections[0].splitlines()
		)
		if not meaningful:
			sections = sections[1:]
	return sections

@app.delete('/api/ideas/sections/{index}')
def delete_idea_section(index: int):
	"""Remove one section from leading-questions/current.md. Sections are
	numbered top-down (newest first, matching the UI render order)."""
	path = stories_root() / 'leading-questions' / 'current.md'
	if not path.exists():
		raise HTTPException(status_code=404, detail='no ideas file')
	text = path.read_text(encoding='utf-8')
	sections = _split_ideas_sections(text)
	if index < 0 or index >= len(sections):
		raise HTTPException(status_code=404, detail=f'section {index} out of range ({len(sections)} sections)')
	sections.pop(index)
	path.write_text(''.join(sections).rstrip() + '\n' if sections else '', encoding='utf-8')
	return {'deleted': index, 'remaining': len(sections)}

@app.post('/api/ideas/regenerate')
def regenerate_ideas():
	"""Spawn the leading-questions generator as a detached subprocess. Returns
	immediately; UI polls /api/ideas to pick up the new content when it lands."""
	root = stories_root()
	log_path = root / 'ideas.log'
	flags = 0
	exe = sys.executable
	if sys.platform == 'win32':
		flags = subprocess.CREATE_NO_WINDOW
		if exe.lower().endswith('pythonw.exe'):
			exe = exe[:-len('pythonw.exe')] + 'python.exe'
	log_file = open(log_path, 'ab')
	subprocess.Popen(
		[exe, str(IDEAS_SCRIPT)],
		cwd=str(PROJECT_ROOT),
		stdout=log_file,
		stderr=subprocess.STDOUT,
		creationflags=flags,
	)
	return {'status': 'started'}

@app.get('/api/memoirs')
def list_memoirs():
	root = stories_root() / 'memoirs'
	root.mkdir(parents=True, exist_ok=True)
	items = []
	for f in sorted(root.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True):
		try:
			text = f.read_text(encoding='utf-8')
		except OSError:
			continue
		meta, body = _split_frontmatter(text)
		items.append({
			'id': f.name,
			'title': meta.get('title') or f.stem.replace('-', ' ').replace('_', ' '),
			'summary': _memoir_summary_from_meta_or_body(meta, body),
			'era': meta.get('era'),
			'topics': meta.get('topics') or [],
			'date_written': str(meta.get('date_written')) if meta.get('date_written') else None,
			'updated_at': datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(timespec='seconds'),
		})
	return items

@app.get('/api/memoirs/{memoir_id}')
def get_memoir(memoir_id: str):
	if not memoir_id.endswith('.md'):
		memoir_id = memoir_id + '.md'
	path = safe_subpath('memoirs', memoir_id)
	if not path.exists() or not path.is_file():
		raise HTTPException(status_code=404, detail='memoir not found')
	text = path.read_text(encoding='utf-8')
	meta, body = _split_frontmatter(text)
	return {
		'id': memoir_id,
		'title': meta.get('title') or path.stem.replace('-', ' ').replace('_', ' '),
		'summary': _memoir_summary_from_meta_or_body(meta, body),
		'era': meta.get('era'),
		'topics': meta.get('topics') or [],
		'date_written': str(meta.get('date_written')) if meta.get('date_written') else None,
		'source_recordings': meta.get('source_recordings') or [],
		'content': body,
		'updated_at': datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec='seconds'),
	}

@app.get('/api/conversations')
def list_conversations():
	return convo.list_all(stories_root())

@app.post('/api/conversations')
def create_conversation(req: CreateConvRequest):
	return convo.create(stories_root(), title=req.title)

@app.get('/api/conversations/{conv_id}')
def get_conversation(conv_id: str):
	c = convo.load(stories_root(), conv_id)
	if not c:
		raise HTTPException(status_code=404, detail='conversation not found')
	return c

@app.delete('/api/conversations/{conv_id}')
def delete_conversation(conv_id: str):
	ok = convo.delete(stories_root(), conv_id)
	if not ok:
		raise HTTPException(status_code=404, detail='conversation not found')
	return {'deleted': conv_id}

def sse(event_type, content):
	return f'data: {json.dumps({"type": event_type, "content": content})}\n\n'

@app.post('/api/conversations/{conv_id}/messages')
async def send_message(conv_id: str, req: MessageRequest):
	if not req.content.strip():
		raise HTTPException(status_code=400, detail='empty message')
	claude = claude_path()
	if not claude:
		raise HTTPException(status_code=500, detail="claude CLI not found; set claude_path in config.json")
	conv = convo.load(stories_root(), conv_id)
	if not conv:
		raise HTTPException(status_code=404, detail='conversation not found')

	# Build prompt from existing history before appending the new user message;
	# compose_chat_prompt concatenates system + bio + recording index + skill +
	# task + conversation so far + new user message.
	prompt = compose_chat_prompt(stories_root(), conv, req.content)
	conv['messages'].append({
		'role': 'user',
		'content': req.content,
		'timestamp': convo.now_iso(),
	})
	conv['updated_at'] = convo.now_iso()
	convo.save(stories_root(), conv)

	async def event_stream():
		# Claude Code's default `-p` output is buffered — the full response arrives
		# only after the prompt completes. For real streaming we use the
		# stream-json format, which emits one JSON event per line: message_start,
		# content_block_start, content_block_delta (text/thinking/tool/signature),
		# content_block_stop, message_stop. We forward only text_delta content to
		# the client; other deltas (thinking, tool use) are ignored for now.
		proc = None
		try:
			proc = await asyncio.create_subprocess_exec(
				claude, '-p', prompt,
				'--output-format', 'stream-json',
				'--include-partial-messages',
				'--verbose',
				'--permission-mode', 'acceptEdits',
				cwd=str(stories_root()),
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.PIPE,
			)
			full = []
			text_blocks_seen = 0
			while True:
				raw_line = await proc.stdout.readline()
				if not raw_line:
					break
				try:
					event = json.loads(raw_line.decode('utf-8', errors='replace'))
				except json.JSONDecodeError:
					continue
				if event.get('type') != 'stream_event':
					continue
				inner = event.get('event') or {}
				inner_type = inner.get('type')
				if inner_type == 'content_block_start':
					# Each Claude turn can have multiple text blocks separated by
					# tool_use blocks. Without a separator the second text block runs
					# straight onto the first ("Sure, let me…Done — saved.").
					block = inner.get('content_block') or {}
					if block.get('type') == 'text':
						text_blocks_seen += 1
						if text_blocks_seen > 1:
							full.append('\n\n')
							yield sse('text', '\n\n')
					continue
				if inner_type != 'content_block_delta':
					continue
				delta = inner.get('delta') or {}
				if delta.get('type') == 'text_delta':
					text = delta.get('text') or ''
					if text:
						full.append(text)
						yield sse('text', text)
			await proc.wait()
			if proc.returncode != 0:
				err = (await proc.stderr.read()).decode(errors='replace')[:500]
				yield sse('error', f'claude exit {proc.returncode}: {err}')
				return
			conv['messages'].append({
				'role': 'assistant',
				'content': ''.join(full),
				'timestamp': convo.now_iso(),
			})
			conv['updated_at'] = convo.now_iso()
			convo.save(stories_root(), conv)
			yield sse('done', '')
		except Exception as e:
			yield sse('error', f'{type(e).__name__}: {e}')
		finally:
			if proc and proc.returncode is None:
				try:
					proc.kill()
				except ProcessLookupError:
					pass

	return StreamingResponse(event_stream(), media_type='text/event-stream')

# Static files mount MUST come after the API routes so those match first.
# html=True makes `/` serve index.html.
app.mount('/', StaticFiles(directory=str(Path(__file__).parent / 'static'), html=True), name='static')

if __name__ == '__main__':
	import uvicorn
	# We intentionally don't use uvicorn's --reload: it's flaky on Windows and
	# has spawned orphaned workers that kept stale code serving on the port.
	# Restart the process after code changes — or POST /api/shutdown for a
	# graceful exit.
	config = uvicorn.Config(app, host='127.0.0.1', port=8000, log_level='info')
	server = uvicorn.Server(config)
	app.state.uvicorn_server = server
	server.run()
