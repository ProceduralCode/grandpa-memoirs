"""Manual rescue: free port 8000 if a stuck backend is holding it.

Same logic as launch.py's auto-recovery, packaged as a standalone tool. Use
this if the launcher gets confused or if you want to explicitly clean up
before relaunching."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from launch import (
	PORT,
	health_ok,
	kill_pid,
	pid_on_port,
	process_image_name,
)

def main():
	pid = pid_on_port(PORT)
	if pid is None:
		print(f"Nothing listening on port {PORT}. Already clean.")
		return
	if health_ok():
		print(f"Backend on port {PORT} (PID {pid}) is healthy — leaving it alone.")
		print("If you want to stop it, POST /api/shutdown or close its console window.")
		return
	name = process_image_name(pid)
	if not name:
		print(f"PID {pid} disappeared between checks. Probably already gone.")
		return
	if name.lower() != 'python.exe':
		print(f"Port {PORT} held by '{name}' (PID {pid}) — that's not our backend, leaving it alone.")
		return
	print(f"Stale backend on port {PORT}: PID {pid} ({name}). Killing...")
	if kill_pid(pid):
		print("Killed. You can relaunch the app now.")
	else:
		print("Kill failed. May need admin privileges.")

if __name__ == '__main__':
	main()
