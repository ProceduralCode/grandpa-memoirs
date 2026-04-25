"""One-click launcher. Starts the backend if it's not already running and
opens the default browser to the app. Idempotent — double-tap doesn't stack."""
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
SERVER_SCRIPT = PROJECT_ROOT / 'web' / 'server.py'
HOST = '127.0.0.1'
PORT = 8000
URL = f'http://{HOST}:{PORT}/'
HEALTH_URL = f'{URL}api/health'
START_WAIT_SECONDS = 10

def is_port_listening(host, port):
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
		s.settimeout(0.5)
		return s.connect_ex((host, port)) == 0

def health_ok():
	try:
		with urllib.request.urlopen(HEALTH_URL, timeout=1) as res:
			return res.status == 200
	except (urllib.error.URLError, OSError, TimeoutError):
		return False

def start_backend():
	flags = 0
	exe = sys.executable
	if sys.platform == 'win32':
		flags = subprocess.CREATE_NEW_CONSOLE
		# Force a visible console even if launcher was invoked via pythonw
		if exe.lower().endswith('pythonw.exe'):
			exe = exe[:-len('pythonw.exe')] + 'python.exe'
	subprocess.Popen(
		[exe, str(SERVER_SCRIPT)],
		creationflags=flags,
		cwd=str(PROJECT_ROOT),
		close_fds=True,
	)

def wait_for_health(deadline_seconds):
	end = time.time() + deadline_seconds
	while time.time() < end:
		if health_ok():
			return True
		time.sleep(0.3)
	return False

def main():
	if is_port_listening(HOST, PORT) and health_ok():
		print(f"Backend already running on port {PORT}; opening browser.")
	else:
		print(f"Starting backend on port {PORT}...")
		start_backend()
		if not wait_for_health(START_WAIT_SECONDS):
			print(f"Backend didn't come up within {START_WAIT_SECONDS}s. Opening browser anyway; check the server console for errors.")
	webbrowser.open(URL)

if __name__ == '__main__':
	main()
