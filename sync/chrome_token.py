"""
Extract a Plaud JWT from a Chrome profile that is signed in to web.plaud.ai.

Approach: launch a fresh Chrome process with the chosen profile and the remote
debugging port enabled, navigate to web.plaud.ai, then use the Chrome DevTools
Protocol (CDP) to evaluate JS in the page that pulls the JWT out of localStorage
or sessionStorage. The launched Chrome closes itself when we're done.

Requires Chrome to NOT already be running with the same profile (file lock).
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from websocket import create_connection

from .plaud_client import PlaudClient, jwt_expiry_seconds

# Small safety margin against clock skew; otherwise we rely on API rejection
TOKEN_CLOCK_SKEW_SECONDS = 30

def is_token_fresh(token):
	"""Token is 'fresh' if its JWT exp is in the future. We don't pad this with
	a large buffer — expiry is reactive, handled by retrying on API 401/403."""
	if not token:
		return False
	exp = jwt_expiry_seconds(token)
	return exp > 0 and time.time() + TOKEN_CLOCK_SKEW_SECONDS < exp

def invalidate_token_cache(cache_path):
	p = Path(cache_path)
	if p.exists():
		try:
			p.unlink()
		except OSError:
			pass

def load_cached_token(cache_path):
	"""Return token string if cache exists and is still fresh, else None."""
	p = Path(cache_path)
	if not p.exists():
		return None
	try:
		token = p.read_text(encoding='utf-8').strip()
	except OSError:
		return None
	if is_token_fresh(token):
		return token
	return None

def save_cached_token(cache_path, token):
	p = Path(cache_path)
	p.parent.mkdir(parents=True, exist_ok=True)
	p.write_text(token, encoding='utf-8')

CHROME_CANDIDATE_PATHS_WIN = [
	r"C:\Program Files\Google\Chrome\Application\chrome.exe",
	r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

EXTRACT_JS = r"""
(function() {
	const re = /eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/;
	function scan(storage, label) {
		for (let i = 0; i < storage.length; i++) {
			const k = storage.key(i);
			const v = storage.getItem(k);
			if (!v) continue;
			const m = v.match(re);
			if (m) return { source: label, key: k, token: m[0] };
		}
		return null;
	}
	return scan(localStorage, 'localStorage') || scan(sessionStorage, 'sessionStorage');
})()
"""

class ChromeTokenError(Exception):
	pass

def find_chrome():
	for p in CHROME_CANDIDATE_PATHS_WIN:
		if Path(p).exists():
			return p
	for p in os.environ.get('PATH', '').split(os.pathsep):
		candidate = Path(p) / 'chrome.exe'
		if candidate.exists():
			return str(candidate)
	return None

def default_user_data_dir():
	local = os.environ.get('LOCALAPPDATA')
	if not local:
		return None
	return Path(local) / 'Google' / 'Chrome' / 'User Data'

def list_profiles(user_data_dir):
	"""Returns [(dir_name, display_name, emails, full_path), ...]."""
	results = []
	if not user_data_dir or not user_data_dir.exists():
		return results
	for child in sorted(user_data_dir.iterdir()):
		if not child.is_dir():
			continue
		if child.name != 'Default' and not child.name.startswith('Profile '):
			continue
		display = child.name
		emails = []
		prefs = child / 'Preferences'
		if prefs.exists():
			try:
				data = json.loads(prefs.read_text(encoding='utf-8'))
				display = data.get('profile', {}).get('name') or child.name
				for acct in data.get('account_info', []) or []:
					e = acct.get('email')
					if e:
						emails.append(e)
			except Exception:
				pass
		results.append((child.name, display, emails, child))
	return results

def find_profile_by_email(user_data_dir, query):
	"""Substring-match any signed-in email across all profiles. Returns the
	profile path if exactly one matches, else None."""
	q = query.lower()
	matches = []
	for dirname, display, emails, path in list_profiles(user_data_dir):
		if any(q in e.lower() for e in emails):
			matches.append((dirname, display, emails, path))
	if len(matches) == 1:
		return matches[0][3]
	return None

def _safe_rmtree(path):
	"""Only rmtree paths that live under the system temp dir — guards against
	any bug that might otherwise repoint our cleanup at a real user directory."""
	path = Path(path).resolve()
	temp_root = Path(tempfile.gettempdir()).resolve()
	if path.is_relative_to(temp_root) and path != temp_root:
		shutil.rmtree(path, ignore_errors=True)

PROFILE_FILES_TO_COPY = [
	'Cookies',
	'Cookies-journal',
	'Local Storage',
	'Session Storage',
	'IndexedDB',
	'Preferences',
	'Secure Preferences',
]

def _copy_profile_to_temp(profile_path):
	"""Copy the essential bits of a Chrome profile into a fresh temp user-data-dir.
	We launch Chrome against the copy so it runs as an independent process and
	doesn't get forwarded to the user's existing Chrome instance."""
	temp_root = Path(tempfile.mkdtemp(prefix='plaud-chrome-'))
	# Local State lives at the User Data root and holds the encrypted cookie key
	src_local_state = profile_path.parent / 'Local State'
	if src_local_state.exists():
		try:
			shutil.copy2(src_local_state, temp_root / 'Local State')
		except (PermissionError, OSError):
			pass

	temp_profile = temp_root / 'Default'
	temp_profile.mkdir()
	missing_critical = False
	for name in PROFILE_FILES_TO_COPY:
		src = profile_path / name
		if not src.exists():
			continue
		dst = temp_profile / name
		try:
			if src.is_dir():
				shutil.copytree(src, dst)
			else:
				shutil.copy2(src, dst)
		except (PermissionError, OSError) as e:
			# If the profile is currently active in a running Chrome window, LevelDB
			# locks prevent reading. Local Storage is the critical one for JWTs.
			if name in ('Local Storage', 'Cookies'):
				missing_critical = True
			print(f"  ! couldn't copy '{name}': {e}")

	if missing_critical:
		_safe_rmtree(temp_root)
		raise ChromeTokenError(
			"Couldn't read the profile's Local Storage or Cookies — this usually means "
			"that profile is currently active in an open Chrome window. Switch that window "
			"to a different profile (or close all Chrome windows for it), then try again."
		)
	return temp_root

def extract_token(profile_path, chrome_path=None, port=9222, page_settle_seconds=5):
	chrome = chrome_path or find_chrome()
	if not chrome:
		raise ChromeTokenError("Chrome not found. Install Chrome or pass chrome_path explicitly.")

	temp_user_data = _copy_profile_to_temp(profile_path)
	print(f"  -> profile copied to temp dir for isolated launch")

	proc = subprocess.Popen([
		chrome,
		f'--remote-debugging-port={port}',
		'--remote-allow-origins=*',
		f'--user-data-dir={temp_user_data}',
		'--no-first-run',
		'--no-default-browser-check',
	])
	try:
		# Wait for the debugging port to come up
		deadline = time.time() + 10
		port_alive = False
		while time.time() < deadline:
			try:
				requests.get(f'http://localhost:{port}/json/version', timeout=1)
				port_alive = True
				break
			except Exception:
				time.sleep(0.3)
		if not port_alive:
			raise ChromeTokenError(
				"Chrome started but the debugging port never opened. "
				"Likely cause: another Chrome instance is already running with this profile. "
				"Close all Chrome windows for this profile and try again."
			)

		# Open a fresh tab directly at web.plaud.ai. This bypasses any session-restore
		# behavior that might otherwise reopen the user's old tabs and ignore our URL.
		new_tab = requests.put(
			f'http://localhost:{port}/json/new?https://web.plaud.ai',
			timeout=5,
		).json()
		target_id = new_tab.get('id')
		if not target_id:
			raise ChromeTokenError(f"Failed to open a new tab at web.plaud.ai: {new_tab}")

		# Wait for the tab to actually navigate to plaud.ai (and allow redirects to settle).
		deadline = time.time() + 30
		target = None
		while time.time() < deadline:
			tabs = requests.get(f'http://localhost:{port}/json').json()
			target = next((t for t in tabs if t.get('id') == target_id), None)
			if target and 'plaud.ai' in target.get('url', ''):
				break
			if target and ('accounts.google.com' in target.get('url', '') or 'appleid.apple.com' in target.get('url', '')):
				raise ChromeTokenError(
					"Plaud redirected to a Google/Apple sign-in page. The profile's saved "
					"session for web.plaud.ai has expired. Open Chrome with the real profile, "
					"sign in to web.plaud.ai manually, close Chrome, and run this script again."
				)
			time.sleep(0.5)

		if not target or 'plaud.ai' not in target.get('url', ''):
			current = target.get('url') if target else '(no tab)'
			raise ChromeTokenError(f"Tab never navigated to plaud.ai. Current URL: {current}")

		print(f"  -> found tab: {target.get('url')}")
		time.sleep(page_settle_seconds)  # let the SPA finish loading and writing tokens

		ws = create_connection(target['webSocketDebuggerUrl'])
		try:
			ws.send(json.dumps({
				'id': 1,
				'method': 'Runtime.evaluate',
				'params': { 'expression': EXTRACT_JS, 'returnByValue': True },
			}))
			result = json.loads(ws.recv())
		finally:
			ws.close()

		value = result.get('result', {}).get('result', {}).get('value')
		if not value:
			raise ChromeTokenError(
				"No JWT found in the Plaud page's storage. "
				"Likely cause: the profile is signed out of Plaud, or the session expired. "
				"Open Chrome with this profile, sign in to web.plaud.ai, then run this again."
			)
		return value  # { source, key, token }
	finally:
		proc.terminate()
		try:
			proc.wait(timeout=3)
		except subprocess.TimeoutExpired:
			proc.kill()
		_safe_rmtree(temp_user_data)

def build_authed_plaud_client(cache_path, email_hint=None, profile_dirname=None, region=None):
	"""Build a PlaudClient wired up with automatic token refresh.

	Resolves an initial token (env → cache → Chrome extract), and registers an
	on_token_expired callback so the client can reactively re-extract from
	Chrome if the API rejects the token mid-session. Returns (client, source)
	where source is 'env' | 'cache' | 'extracted'.
	"""
	token, source = resolve_plaud_token(
		cache_path=cache_path,
		email_hint=email_hint,
		profile_dirname=profile_dirname,
	)

	def _refresh():
		invalidate_token_cache(cache_path)
		new_token, _ = resolve_plaud_token(
			cache_path=cache_path,
			email_hint=email_hint,
			profile_dirname=profile_dirname,
			force_fresh=True,
		)
		return new_token

	region = region or os.environ.get('PLAUD_REGION', 'us')
	client = PlaudClient(token=token, region=region, on_token_expired=_refresh)
	return client, source

def resolve_plaud_token(cache_path, email_hint=None, profile_dirname=None, env_token=None, force_fresh=False):
	"""Single entry point for obtaining a Plaud JWT.

	Resolution order:
	  1. env_token arg (or PLAUD_TOKEN env var) — use directly, don't cache
	  2. Cached token at cache_path whose JWT exp is still in the future
	  3. Extract from a Chrome profile (by dirname, then by email substring,
	     then interactive picker) — cache the result on success

	Set force_fresh=True to skip steps 1 and 2 (used by callers reacting to an
	API auth rejection).
	"""
	if not force_fresh:
		token = env_token or os.environ.get('PLAUD_TOKEN')
		if token:
			return token, 'env'

		cached = load_cached_token(cache_path)
		if cached:
			return cached, 'cache'

	user_data_dir = default_user_data_dir()
	profile_path = None
	if profile_dirname and user_data_dir:
		candidate = user_data_dir / profile_dirname
		if candidate.exists():
			profile_path = candidate
	if not profile_path and email_hint and user_data_dir:
		profile_path = find_profile_by_email(user_data_dir, email_hint)
	if not profile_path:
		profile_path = choose_profile_interactively(user_data_dir)

	print(f"Extracting token from Chrome profile: {profile_path.name}")
	result = extract_token(profile_path)
	token = result['token']
	save_cached_token(cache_path, token)
	return token, 'extracted'

def choose_profile_interactively(user_data_dir=None):
	user_data_dir = user_data_dir or default_user_data_dir()
	profiles = list_profiles(user_data_dir)
	if not profiles:
		raise ChromeTokenError(f"No Chrome profiles found under {user_data_dir}")
	print("\nChrome profiles found:")
	for i, (dirname, display, emails, _) in enumerate(profiles):
		email_str = f"  [{', '.join(emails)}]" if emails else ""
		print(f"  [{i}] {display}  ({dirname}){email_str}")
	idx = int(input("Pick profile #: ").strip())
	return profiles[idx][3]
