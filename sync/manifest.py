"""Local manifest tracking which Plaud recordings we've already downloaded.
Lives at <stories_root>/manifest.json. Keyed by Plaud file ID so we can skip
already-synced items cheaply and know when to re-fetch a pending transcript."""
import json
from pathlib import Path

MANIFEST_VERSION = 1

def manifest_path(stories_root):
	return Path(stories_root) / 'manifest.json'

def load_manifest(stories_root):
	p = manifest_path(stories_root)
	if not p.exists():
		return {'version': MANIFEST_VERSION, 'items': {}, 'last_sync': None}
	try:
		with open(p, encoding='utf-8') as f:
			data = json.load(f)
	except (OSError, json.JSONDecodeError):
		return {'version': MANIFEST_VERSION, 'items': {}, 'last_sync': None}
	data.setdefault('version', MANIFEST_VERSION)
	data.setdefault('items', {})
	data.setdefault('last_sync', None)
	return data

def save_manifest(stories_root, manifest):
	p = manifest_path(stories_root)
	p.parent.mkdir(parents=True, exist_ok=True)
	p.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
