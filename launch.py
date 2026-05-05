"""One-click launcher.

Self-healing: detects stuck backends from prior runs and cleans them up.
Source of truth is "what's actually listening on port 8000," verified to be a
python.exe process so we never kill anything unrelated.
"""
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

def pid_on_port(port):
	"""Return the PID listening on the given port, or None."""
	try:
		result = subprocess.run(
			['netstat', '-ano', '-p', 'tcp'],
			capture_output=True, text=True, timeout=5,
		)
	except (subprocess.TimeoutExpired, OSError):
		return None
	needle = f':{port}'
	for line in result.stdout.splitlines():
		if needle in line and 'LISTENING' in line:
			parts = line.split()
			if parts and parts[-1].isdigit():
				return int(parts[-1])
	return None

def process_image_name(pid):
	"""Return tasklist's image name for the PID (e.g. 'python.exe'), or None
	if the process doesn't exist."""
	try:
		result = subprocess.run(
			['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
			capture_output=True, text=True, timeout=5,
		)
	except (subprocess.TimeoutExpired, OSError):
		return None
	line = (result.stdout or '').strip()
	if not line or line.startswith('INFO:'):
		return None
	# CSV: "image","pid","session","sess#","mem"
	first = line.split(',', 1)[0].strip().strip('"')
	return first or None

def kill_pid(pid):
	try:
		subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True, timeout=5)
		return True
	except (subprocess.TimeoutExpired, OSError):
		return False

def reclaim_port_if_orphan(port):
	"""If something's listening on `port` but not responding to /api/health,
	verify it's a python.exe (i.e. our server) and kill it. Returns True if
	the port is now free (or already was), False if held by something we
	shouldn't touch."""
	pid = pid_on_port(port)
	if pid is None:
		return True
	if health_ok():
		return False  # healthy server, nothing to reclaim
	name = process_image_name(pid)
	if not name:
		return True  # PID disappeared between checks
	if name.lower() != 'python.exe':
		print(f"Port {port} is held by '{name}' (PID {pid}). That's not our backend; refusing to touch it.")
		return False
	print(f"Stale backend on port {port} (PID {pid}, {name}). Killing it.")
	kill_pid(pid)
	time.sleep(1.5)  # let the OS release the socket
	return True

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
		webbrowser.open(URL)
		return

	if not reclaim_port_if_orphan(PORT):
		print("Cannot start: port held by an unrelated process. Aborting.")
		return

	print(f"Starting backend on port {PORT}...")
	start_backend()
	if not wait_for_health(START_WAIT_SECONDS):
		print(f"Backend didn't come up within {START_WAIT_SECONDS}s. Opening browser anyway; check the server console for errors.")
	webbrowser.open(URL)

if __name__ == '__main__':
	main()
