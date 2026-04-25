"""Dev-only: wipe the local stories folder and pull a diversified sample of
recordings from Plaud. Grabs a mix of transcribed and untranscribed items
from different points in the timeline, not just the latest batch.

Usage:
    python Grandpa/scripts/sample_sync.py [N]    # default 8
"""
import json
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sync.chrome_token import build_authed_plaud_client
from sync.manifest import load_manifest, save_manifest
from sync.sync import (
	CONFIG_PATH,
	DEFAULT_CONFIG,
	TOKEN_CACHE_PATH,
	now_iso,
	sync_one,
)

def pick_sample(recs, n):
	trans = [r for r in recs if r.get('is_trans')]
	not_trans = [r for r in recs if not r.get('is_trans')]
	n_trans = min(len(trans), max(1, int(n * 0.75)))
	n_not = min(len(not_trans), n - n_trans)
	sample = random.sample(trans, n_trans) + random.sample(not_trans, n_not) if not_trans else random.sample(trans, n_trans + n_not)
	return sample

def main():
	n = int(sys.argv[1]) if len(sys.argv) > 1 else 8

	if CONFIG_PATH.exists():
		with open(CONFIG_PATH, encoding='utf-8') as f:
			cfg = {**DEFAULT_CONFIG, **json.load(f)}
	else:
		cfg = dict(DEFAULT_CONFIG)

	stories_root = Path(cfg['stories_root'])
	recordings_root = stories_root / 'recordings'

	print(f"Wiping: {recordings_root}")
	if recordings_root.exists():
		shutil.rmtree(recordings_root)
	for fname in ('manifest.json', 'sync-status.json', 'sync.lock'):
		p = stories_root / fname
		if p.exists():
			p.unlink()
	recordings_root.mkdir(parents=True, exist_ok=True)

	client, source = build_authed_plaud_client(
		cache_path=TOKEN_CACHE_PATH,
		email_hint=cfg.get('chrome_profile_email'),
		profile_dirname=cfg.get('chrome_profile_dirname'),
		region=cfg.get('region'),
	)
	print(f"Token source: {source}")

	recs = client.list_recordings()
	trans_count = sum(1 for r in recs if r.get('is_trans'))
	print(f"Remote: {len(recs)} total, {trans_count} transcribed, {len(recs) - trans_count} pending")

	random.seed(42)
	sample = pick_sample(recs, n)
	sample.sort(key=lambda r: r.get('start_time', 0))
	print(f"Sampled {len(sample)}:")
	for r in sample:
		print(f"  - {r.get('filename')} (trans={r.get('is_trans')})")

	manifest = load_manifest(stories_root)
	for r in sample:
		result, detail = sync_one(client, r, recordings_root, manifest)
		print(f"  {result}: {detail or ''}")
	manifest['last_sync'] = now_iso()
	save_manifest(stories_root, manifest)

	print("\nDone.")

if __name__ == '__main__':
	main()
