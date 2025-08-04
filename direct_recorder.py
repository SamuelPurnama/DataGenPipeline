#!/usr/bin/env python3
"""
Direct Recorder - Runs recorderSystem.py and shows output immediately
"""

import subprocess
import sys
import time
import threading
from datetime import datetime

def main():
    print("🎯 Direct Recorder - Shows output immediately")
    print("=" * 60)
    
    # Get URL from user
    url = input("Enter URL to record (default: https://docs.google.com): ").strip()
    if not url:
        url = "https://docs.google.com"
    
    print(f"🌐 Recording on: {url}")
    print("=" * 60)
    
    # Start the recorder process with direct output
    cmd = [sys.executable, 'recorderSystem.py', '--url', url]
    print(f"📝 Command: {' '.join(cmd)}")
    print("=" * 60)
    
    try:
        # Run the process with direct output to terminal
        print("🚀 Starting recorder...")
        print("-" * 60)
        
        # Use subprocess.run with real-time output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        print(f"✅ Process started with PID: {process.pid}")
        print("📥 OUTPUT:")
        print("-" * 60)
        
        # Monitor output in real-time
        def monitor_output():
            while process.poll() is None:
                # Read stdout
                line = process.stdout.readline()
                if line:
                    line = line.strip()
                    if line:
                        print(f"📥 {line}")
                
                # Read stderr
                line = process.stderr.readline()
                if line:
                    line = line.strip()
                    if line:
                        print(f"❌ ERROR: {line}")
                
                time.sleep(0.1)
        
        # Start monitoring in a separate thread
        monitor_thread = threading.Thread(target=monitor_output, daemon=True)
        monitor_thread.start()
        
        print("🎯 Recorder is running! Press Ctrl+C to stop.")
        print("💡 Interact with the browser that opens...")
        print("-" * 60)
        
        # Wait for the process to finish
        process.wait()
        
        print("-" * 60)
        print(f"✅ Process finished with return code: {process.returncode}")
        
    except KeyboardInterrupt:
        print("\n⏹️ Stopping recorder...")
        if process:
            process.terminate()
            process.wait(timeout=5)
        print("✅ Recorder stopped")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main() 