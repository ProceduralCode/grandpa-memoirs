"""Pull new Plaud recordings + metadata to the local filesystem.

Intended to run as a scheduled task every ~30 minutes. Idempotent — safe to
run repeatedly. Skips recordings whose MP3 and fully-transcribed JSON we
already have. Re-fetches detail for recordings whose transcript wasn't ready
on a prior run but is now.

Layout produced under <stories_root>/recordings/:

  2026-04-14_18-40-28/
    audio.mp3
    data.json        <- {'detail': ..., 'fetched_content': ...}

Plus:
  <stories_root>/manifest.json       <- tracks what we have
  <stories_root>/sync-status.json    <- read by the web UI status indicator
  <stories_root>/sync.lock           <- prevents concurrent runs
"""
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sync.chrome_token import build_authed_plaud_client
from sync.manifest import load_manifest, save_manifest

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / 'config.json'
TOKEN_CACHE_PATH = PROJECT_ROOT / '.plaud-token'
LOCK_STALE_SECONDS = 30 * 60  # if older, assume previous sync died

DEFAULT_CONFIG = {
	'stories_root': str(Path.home() / 'Documents' / 'Grandpa Stories'),
	'chrome_profile_email': None,
	'chrome_profile_dirname': None,
	'region': 'us',
	'claude_path': None,
}

def load_config():
	if not CONFIG_PATH.exists():
		return dict(DEFAULT_CONFIG)
	with open(CONFIG_PATH, encoding='utf-8') as f:
		user = json.load(f)
	return {**DEFAULT_CONFIG, **user}

def now_iso():
	return datetime.now(timezone.utc).isoformat(timespec='seconds')

def recording_dirname(start_time_ms):
	if not start_time_ms:
		return None
	dt = datetime.fromtimestamp(start_time_ms / 1000)
	return dt.strftime('%Y-%m-%d_%H-%M-%S')

def acquire_lock(stories_root):
	lock = stories_root / 'sync.lock'
	if lock.exists():
		try:
			age = time.time() - lock.stat().st_mtime
		except OSError:
			age = 0
		if age < LOCK_STALE_SECONDS:
			return None
	lock.write_text(str(int(time.time())), encoding='utf-8')
	return lock

def release_lock(lock_path):
	if lock_path and lock_path.exists():
		try:
			lock_path.unlink()
		except OSError:
			pass

def write_status(stories_root, status):
	path = stories_root / 'sync-status.json'
	path.write_text(json.dumps(status, indent=2), encoding='utf-8')

def sync_one(client, rec, recordings_root, manifest):
	plaud_id = rec.get('id') or rec.get('file_id')
	if not plaud_id:
		return 'error', 'missing id'
	start_time = rec.get('start_time') or 0
	dirname = recording_dirname(start_time) or f'unknown-time_{plaud_id}'
	rec_dir = recordings_root / dirname
	rec_dir.mkdir(parents=True, exist_ok=True)
	mp3_path = rec_dir / 'audio.mp3'
	json_path = rec_dir / 'data.json'

	item = manifest['items'].get(plaud_id, {})
	actions = []

	if not mp3_path.exists():
		client.download_audio(plaud_id, mp3_path)
		item['mp3_downloaded_at'] = now_iso()
		actions.append('mp3')

	is_trans_remote = bool(rec.get('is_trans'))
	have_transcribed_json = json_path.exists() and item.get('is_trans_captured')
	# Back off on re-fetch if we've tried recently — handles the edge case
	# where Plaud's list flags a recording as transcribed but the detail
	# response has no fetchable transcript content
	recently_attempted = False
	last_attempt = item.get('last_detail_attempt_at')
	if last_attempt:
		try:
			dt = datetime.fromisoformat(last_attempt)
			age_seconds = (datetime.now(timezone.utc) - dt).total_seconds()
			recently_attempted = age_seconds < 24 * 60 * 60
		except (ValueError, TypeError):
			pass
	need_detail = not json_path.exists() or (is_trans_remote and not have_transcribed_json and not recently_attempted)

	if need_detail:
		blob = client.get_recording_detail(plaud_id)
		json_path.write_text(json.dumps(blob, indent=2, default=str), encoding='utf-8')
		# Ground truth for "we captured a transcript": there's a transaction
		# entry in fetched_content with actual segments. The list endpoint's
		# is_trans flag is unreliable (sometimes True with no fetchable content).
		item['is_trans_captured'] = any(
			k.startswith('source_transaction:') and isinstance(v, list) and v
			for k, v in blob.get('fetched_content', {}).items()
		)
		item['json_updated_at'] = now_iso()
		item['last_detail_attempt_at'] = now_iso()
		actions.append('json+tx' if item['is_trans_captured'] else 'json')

	item['dirname'] = dirname
	manifest['items'][plaud_id] = item
	return ('updated', ', '.join(actions)) if actions else ('skipped', None)

def sync():
	config = load_config()
	stories_root = Path(config['stories_root'])
	stories_root.mkdir(parents=True, exist_ok=True)
	recordings_root = stories_root / 'recordings'
	recordings_root.mkdir(parents=True, exist_ok=True)

	print(f"Stories root: {stories_root}")
	status = {'started_at': now_iso(), 'error': None}

	lock = acquire_lock(stories_root)
	if lock is None:
		status['error'] = 'Another sync already in progress (sync.lock held)'
		status['completed_at'] = now_iso()
		write_status(stories_root, status)
		print(status['error'])
		return

	try:
		client, token_source = build_authed_plaud_client(
			cache_path=TOKEN_CACHE_PATH,
			email_hint=config.get('chrome_profile_email'),
			profile_dirname=config.get('chrome_profile_dirname'),
			region=config.get('region'),
		)
		print(f"Token source: {token_source}")

		recs = client.list_recordings()
		total_remote = len(recs)
		print(f"Remote: {total_remote} recordings")

		limit = os.environ.get('GRANDPA_SYNC_LIMIT')
		if limit:
			recs = recs[:int(limit)]
			print(f"(limited to first {len(recs)} for this run)")

		manifest = load_manifest(stories_root)

		counts = {'new_mp3': 0, 'new_json': 0, 'with_transcript': 0, 'skipped': 0, 'errors': 0}
		for rec in recs:
			try:
				result, detail = sync_one(client, rec, recordings_root, manifest)
				plaud_id = rec.get('id')
				if result == 'skipped':
					counts['skipped'] += 1
				elif result == 'updated':
					if 'mp3' in (detail or ''):
						counts['new_mp3'] += 1
					if 'json' in (detail or ''):
						counts['new_json'] += 1
					if 'tx' in (detail or ''):
						counts['with_transcript'] += 1
					print(f"  {rec.get('start_time') and recording_dirname(rec['start_time']) or plaud_id}: {detail}")
			except Exception as e:
				counts['errors'] += 1
				print(f"  ! {rec.get('id')}: {e}")
				traceback.print_exc()

		manifest['last_sync'] = now_iso()
		save_manifest(stories_root, manifest)

		# Regenerate the one-line-per-recording index that Claude sees in context
		try:
			from scripts.generate_summaries import generate as generate_summaries
			generate_summaries(stories_root)
		except Exception as e:
			print(f"  ! summary generation failed: {e}")

		# Refresh the Ideas screen if this sync brought new recording content
		brought_new = counts['new_mp3'] > 0 or counts['with_transcript'] > 0
		if brought_new:
			try:
				from scripts.generate_leading_questions import generate as generate_ideas
				generate_ideas(stories_root)
			except Exception as e:
				print(f"  ! leading-questions generation failed: {e}")

		status.update({
			'completed_at': now_iso(),
			'total_remote': total_remote,
			**counts,
		})
		print(f"Done: {counts}")
	except Exception as e:
		status['error'] = f"{type(e).__name__}: {e}"
		status['completed_at'] = now_iso()
		traceback.print_exc()
		raise
	finally:
		write_status(stories_root, status)
		release_lock(lock)

if __name__ == '__main__':
	sync()
