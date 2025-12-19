#!/usr/bin/env python3
"""
Production runner for Telegram Bot.
This ensures only ONE process runs using a PID file.
"""
import os
import sys
import time
import subprocess

PID_FILE = "/tmp/telegrambot.pid"

def kill_existing():
    """Kill any existing uvicorn processes."""
    try:
        subprocess.run(["pkill", "-9", "-f", "uvicorn webhook_server"], check=False)
        time.sleep(2)
        print("Killed existing processes")
    except Exception as e:
        print(f"Error killing processes: {e}")

def check_pid_file():
    """Check if another instance is running."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            # Check if process is still running
            os.kill(old_pid, 0)
            print(f"Another instance is running (PID: {old_pid}). Killing it...")
            os.kill(old_pid, 9)
            time.sleep(2)
        except (OSError, ValueError):
            # Process doesn't exist, remove stale PID file
            os.remove(PID_FILE)

def write_pid_file():
    """Write current PID to file."""
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

def main():
    # Kill any existing processes
    kill_existing()
    
    # Check PID file
    check_pid_file()
    
    # Write our PID
    write_pid_file()
    
    # Change to bot directory
    os.chdir("/home/ubuntu/telegrambot")
    
    # Run uvicorn directly with Python (NO reload, NO workers)
    os.execvp("python3", [
        "python3",
        "-m", "uvicorn",
        "webhook_server:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--log-level", "warning",
        "--no-access-log",
        "--no-use-colors"
    ])

if __name__ == "__main__":
    main()

