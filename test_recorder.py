#!/usr/bin/env python3
"""
Test Recorder - Run recorderSystem.py directly to see output
"""

import subprocess
import sys
import time

def main():
    print("🧪 Testing Recorder Output")
    print("=" * 50)
    
    # Test command
    cmd = [sys.executable, 'recorderSystem.py', '--url', 'https://docs.google.com']
    print(f"📝 Testing command: {' '.join(cmd)}")
    print("=" * 50)
    
    try:
        # Run the process and capture output in real-time
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        print(f"✅ Process started with PID: {process.pid}")
        print("=" * 50)
        print("📥 OUTPUT:")
        print("-" * 50)
        
        # Read output in real-time
        while process.poll() is None:
            # Read stdout
            line = process.stdout.readline()
            if line:
                line = line.strip()
                if line:
                    print(f"📥 STDOUT: {line}")
            
            # Read stderr
            line = process.stderr.readline()
            if line:
                line = line.strip()
                if line:
                    print(f"❌ STDERR: {line}")
            
            time.sleep(0.1)
        
        # Read any remaining output
        stdout, stderr = process.communicate()
        if stdout:
            print("📥 FINAL STDOUT:")
            print(stdout)
        if stderr:
            print("❌ FINAL STDERR:")
            print(stderr)
        
        print("=" * 50)
        print(f"✅ Process finished with return code: {process.returncode}")
        
    except KeyboardInterrupt:
        print("\n⏹️ Stopping test...")
        if process:
            process.terminate()
            process.wait(timeout=5)
        print("✅ Test stopped")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main() 