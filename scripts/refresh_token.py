"""Manual Plaud token refresh.

Use this when sync errors out because the cached token expired (~30 days) or
because Chrome had a file lock when sync tried to extract one. Close all
Chrome windows first, then run this. It launches Chrome briefly (for the
extraction), reads the JWT, caches it to .plaud-token, and exits.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sync.sync import load_config, TOKEN_CACHE_PATH
from sync.chrome_token import (
	ChromeTokenError,
	invalidate_token_cache,
	resolve_plaud_token,
)

def main():
	config = load_config()
	print("Refreshing Plaud token...")
	invalidate_token_cache(TOKEN_CACHE_PATH)
	try:
		_, source = resolve_plaud_token(
			cache_path=TOKEN_CACHE_PATH,
			email_hint=config.get('chrome_profile_email'),
			profile_dirname=config.get('chrome_profile_dirname'),
			force_fresh=True,
		)
	except ChromeTokenError as e:
		print()
		print(f"FAILED: {e}")
		print()
		print("Common fixes:")
		print("  - Close all Chrome windows (and check tray/Task Manager)")
		print("  - Make sure that Chrome profile is signed in to web.plaud.ai")
		print("  - If the session expired, sign in to web.plaud.ai again, then retry")
		sys.exit(1)
	print()
	print(f"Success — new token cached (source: {source}).")
	print("You can reopen the app and click Sync.")

if __name__ == '__main__':
	main()
