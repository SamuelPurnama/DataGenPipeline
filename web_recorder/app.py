#!/usr/bin/env python3
"""
Web Recorder - Desktop GUI App
A simple desktop application for recording browser interactions
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import sys
import os
import json
import threading
import time
from pathlib import Path
from datetime import datetime
import webbrowser
import shutil


def resolve_recorder_path():
    """Return path to recorderSystem.py, handling both development and bundled scenarios"""
    # Get the base directory (where the app is running from)
    if getattr(sys, 'frozen', False):
        # Running as bundled app
        base_dir = Path(sys._MEIPASS)
    else:
        # Running in development
        base_dir = Path(__file__).parent
    
    # Check multiple possible locations
    possible_paths = [
        base_dir / "recorderSystem.py",  # Same directory as app
        base_dir / "_internal" / "recorderSystem.py",  # PyInstaller internal directory
        base_dir.parent / "recorderSystem.py",  # Parent directory
        Path("recorderSystem.py"),  # Current working directory
        Path("../recorderSystem.py"),  # Relative to current directory
    ]
    
    for path in possible_paths:
        if path.exists():
            print(f"✅ Found recorderSystem.py at: {path}")
            return path
    
    # If not found, try to copy from parent directory
    parent_path = Path(__file__).parent.parent / "recorderSystem.py"
    if parent_path.exists():
        try:
            local_path = Path(__file__).parent / "recorderSystem.py"
            shutil.copyfile(parent_path, local_path)
            print(f"📄 Copied recorderSystem.py to: {local_path}")
            return local_path
        except Exception as e:
            print(f"⚠️ Could not copy recorderSystem.py: {e}")
            return parent_path
    
    # Return the expected local path even if it doesn't exist
    return Path(__file__).parent / "recorderSystem.py"


class WebRecorderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Web Recorder - Action Recorder")
        self.root.geometry("700x600")
        self.root.resizable(True, True)
        
        # Set up the main frame
        main_frame = ttk.Frame(root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="🎯 Web Recorder", font=("Arial", 18, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # URL input
        ttk.Label(main_frame, text="Website URL:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        self.url_var = tk.StringVar(value="https://calendar.google.com")
        url_entry = ttk.Entry(main_frame, textvariable=self.url_var, width=50)
        url_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=(0, 20))
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=(0, 20))
        
        self.start_button = ttk.Button(button_frame, text="🚀 Start Recording", command=self.start_recording)
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_button = ttk.Button(button_frame, text="⏹️ Stop Recording", command=self.stop_recording, state="disabled")
        self.stop_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.open_folder_button = ttk.Button(button_frame, text="📁 Open Output Folder", command=self.open_output_folder)
        self.open_folder_button.pack(side=tk.LEFT)
        
        # Status
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 20))
        
        self.status_var = tk.StringVar(value="Ready to start recording")
        status_label = ttk.Label(status_frame, textvariable=self.status_var)
        status_label.pack()
        
        # Progress bar
        self.progress = ttk.Progressbar(status_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(10, 0))
        
        # Sessions frame
        sessions_frame = ttk.LabelFrame(main_frame, text="📁 Recent Sessions", padding="10")
        sessions_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 20))
        
        # Configure sessions frame to expand
        main_frame.rowconfigure(4, weight=1)
        sessions_frame.columnconfigure(0, weight=1)
        sessions_frame.rowconfigure(1, weight=1)
        
        # Sessions list
        self.sessions_listbox = tk.Listbox(sessions_frame, height=8)
        self.sessions_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        # Sessions scrollbar
        sessions_scrollbar = ttk.Scrollbar(sessions_frame, orient=tk.VERTICAL, command=self.sessions_listbox.yview)
        sessions_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.sessions_listbox.configure(yscrollcommand=sessions_scrollbar.set)
        
        # Session buttons
        session_button_frame = ttk.Frame(sessions_frame)
        session_button_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E))
        
        self.view_session_button = ttk.Button(session_button_frame, text="📄 View", command=self.view_session)
        self.view_session_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.delete_session_button = ttk.Button(session_button_frame, text="🗑️ Delete", command=self.delete_session)
        self.delete_session_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.open_html_button = ttk.Button(session_button_frame, text="🌐 HTML Report", command=self.open_html_report)
        self.open_html_button.pack(side=tk.LEFT)
        
        # Refresh button
        self.refresh_button = ttk.Button(session_button_frame, text="🔄 Refresh", command=self.refresh_sessions)
        self.refresh_button.pack(side=tk.RIGHT)
        
        # Initialize variables
        self.recorder_process = None
        self.sessions = []
        
        # Validate recorderSystem.py
        self.validate_recorder_system()
        
        # Load initial sessions
        self.refresh_sessions()
        
        # Bind double-click to view session
        self.sessions_listbox.bind('<Double-Button-1>', lambda e: self.view_session())
        
        # Set up periodic refresh
        self.setup_periodic_refresh()
    
    def validate_recorder_system(self):
        """Validate that recorderSystem.py exists and is accessible"""
        recorder_path = resolve_recorder_path()
        if recorder_path.exists():
            print(f"✅ Found recorderSystem.py at: {recorder_path}")
            self.status_var.set("✅ Ready to start recording")
        else:
            print(f"⚠️ recorderSystem.py not found at: {recorder_path}")
            self.status_var.set("⚠️ recorderSystem.py not found - recording may fail")
            messagebox.showwarning("Warning", 
                                 f"recorderSystem.py not found at:\n{recorder_path}\n\n"
                                 "Please ensure recorderSystem.py is available.")
    
    def check_playwright_browsers(self):
        """Check if Playwright browsers are installed"""
        try:
            import subprocess
            result = subprocess.run([sys.executable, "-m", "playwright", "install", "--dry-run"], 
                                  capture_output=True, text=True)
            if "chromium" not in result.stdout:
                return False
            return True
        except:
            return False
    
    def install_playwright_browsers(self):
        """Install Playwright browsers"""
        try:
            import subprocess
            print("📦 Installing Playwright browsers...")
            subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
            print("✅ Playwright browsers installed")
            return True
        except Exception as e:
            print(f"❌ Failed to install browsers: {e}")
            return False
    
    def setup_periodic_refresh(self):
        """Set up periodic refresh of sessions list"""
        def refresh_periodic():
            if not self.recorder_process:  # Only refresh when not recording
                self.refresh_sessions()
            self.root.after(5000, refresh_periodic)  # Refresh every 5 seconds
        
        self.root.after(5000, refresh_periodic)
    
    def start_recording(self):
        """Start the recording process"""
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL")
            return
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Check for Playwright browsers
        if not self.check_playwright_browsers():
            result = messagebox.askyesno("Browser Installation", 
                                       "Playwright browsers are not installed.\n\n"
                                       "Would you like to install them now?\n\n"
                                       "This may take a few minutes.")
            if result:
                self.status_var.set("📦 Installing browsers...")
                self.progress.start()
                self.root.update()
                
                if self.install_playwright_browsers():
                    self.status_var.set("✅ Browsers installed successfully")
                    messagebox.showinfo("Success", "Playwright browsers installed successfully!")
                else:
                    self.status_var.set("❌ Failed to install browsers")
                    messagebox.showerror("Error", "Failed to install Playwright browsers.\n\n"
                                                "Please install them manually:\n"
                                                "python3 -m playwright install chromium")
                    self.progress.stop()
                    return
                self.progress.stop()
            else:
                return
        
        try:
            # Resolve recorderSystem.py
            recorder_path = resolve_recorder_path()
            
            if not recorder_path.exists():
                messagebox.showerror("Error", f"recorderSystem.py not found at: {recorder_path}\n\nPlease ensure recorderSystem.py is available.")
                return
            
            print(f"🎯 Using recorderSystem.py at: {recorder_path}")
            
            # Start the recorder process
            cmd = [sys.executable, str(recorder_path), "--url", url]
            
            self.recorder_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Update UI
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
            self.status_var.set("🎯 Recording in progress...")
            self.progress.start()
            
            # Start monitoring thread
            self.monitor_thread = threading.Thread(target=self.monitor_process, daemon=True)
            self.monitor_thread.start()
            
            messagebox.showinfo("Recording Started", 
                              f"Recording started for {url}\n\n"
                              "A new browser window will open. Interact with the page to record actions.\n\n"
                              "Click 'Stop Recording' when done.")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start recording: {str(e)}")
            self.stop_recording()
    
    def monitor_process(self):
        """Monitor the recorder process"""
        try:
            # Wait for process to complete
            stdout, stderr = self.recorder_process.communicate()
            
            # Print output for debugging
            if stdout:
                print("📤 Recorder stdout:", stdout)
            if stderr:
                print("📤 Recorder stderr:", stderr)
            
            # Update UI on main thread
            self.root.after(0, self.on_process_complete, stdout, stderr)
            
        except Exception as e:
            print(f"❌ Process monitoring error: {e}")
            self.root.after(0, lambda: messagebox.showerror("Error", f"Process monitoring error: {str(e)}"))
            self.root.after(0, self.stop_recording)
    
    def on_process_complete(self, stdout, stderr):
        """Handle process completion"""
        if self.recorder_process:
            return_code = self.recorder_process.returncode
            self.recorder_process = None
            
            print(f"📊 Process completed with return code: {return_code}")
            
            if return_code == 0:
                self.status_var.set("✅ Recording completed successfully")
                messagebox.showinfo("Recording Complete", "Recording completed successfully!")
            else:
                self.status_var.set("❌ Recording failed")
                error_msg = stderr if stderr else "Unknown error"
                print(f"❌ Recording failed with error: {error_msg}")
                messagebox.showerror("Recording Failed", f"Recording failed:\n{error_msg}")
            
            self.stop_recording()
    
    def stop_recording(self):
        """Stop the recording process"""
        if self.recorder_process:
            try:
                # Try to terminate gracefully
                self.recorder_process.terminate()
                
                # Wait for graceful termination
                try:
                    self.recorder_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't stop gracefully
                    self.recorder_process.kill()
                    self.recorder_process.wait(timeout=2)
                
            except Exception as e:
                print(f"Error stopping process: {e}")
            finally:
                self.recorder_process = None
        
        # Update UI
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.status_var.set("Ready to start recording")
        self.progress.stop()
        
        # Refresh sessions after a short delay
        self.root.after(2000, self.refresh_sessions)
    
    def open_output_folder(self):
        """Open the output folder"""
        output_dir = Path("data") / "interaction_logs"
        if output_dir.exists():
            if sys.platform == "darwin":  # macOS
                subprocess.run(["open", str(output_dir)])
            elif sys.platform == "win32":  # Windows
                subprocess.run(["explorer", str(output_dir)])
            else:  # Linux
                subprocess.run(["xdg-open", str(output_dir)])
        else:
            messagebox.showinfo("Info", "No output folder found yet. Start a recording first.")
    
    def refresh_sessions(self):
        """Refresh the sessions list"""
        try:
            output_dir = Path("data") / "interaction_logs"
            if not output_dir.exists():
                self.sessions = []
                self.sessions_listbox.delete(0, tk.END)
                self.sessions_listbox.insert(tk.END, "No sessions found")
                return
            
            # Get all session directories
            session_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("session_")]
            
            if not session_dirs:
                self.sessions = []
                self.sessions_listbox.delete(0, tk.END)
                self.sessions_listbox.insert(tk.END, "No sessions found")
                return
            
            # Sort by modification time (newest first)
            session_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            self.sessions = []
            self.sessions_listbox.delete(0, tk.END)
            
            for session_dir in session_dirs:
                session_info = self.get_session_info(session_dir)
                self.sessions.append(session_info)
                
                # Create display text
                display_text = f"{session_dir.name} ({session_info['interactions']} interactions, {session_info['screenshots']} screenshots)"
                self.sessions_listbox.insert(tk.END, display_text)
            
            if not self.sessions:
                self.sessions_listbox.insert(tk.END, "No sessions found")
                
        except Exception as e:
            print(f"Error refreshing sessions: {e}")
            self.sessions_listbox.delete(0, tk.END)
            self.sessions_listbox.insert(tk.END, f"Error loading sessions: {str(e)}")
    
    def get_session_info(self, session_dir):
        """Get information about a session"""
        session_info = {
            'name': session_dir.name,
            'path': str(session_dir),
            'interactions': 0,
            'screenshots': 0,
            'created': datetime.fromtimestamp(session_dir.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Check for trajectory.json
        trajectory_file = session_dir / "trajectory.json"
        if trajectory_file.exists():
            try:
                with open(trajectory_file, 'r') as f:
                    trajectory_data = json.load(f)
                session_info['interactions'] = len(trajectory_data)
            except:
                pass
        
        # Count screenshots
        images_dir = session_dir / "images"
        if images_dir.exists():
            screenshot_count = len(list(images_dir.glob("*.png")))
            session_info['screenshots'] = screenshot_count
        
        return session_info
    
    def get_selected_session(self):
        """Get the currently selected session"""
        selection = self.sessions_listbox.curselection()
        if selection and selection[0] < len(self.sessions):
            return self.sessions[selection[0]]
        return None
    
    def view_session(self):
        """View the selected session"""
        session = self.get_selected_session()
        if not session:
            messagebox.showwarning("Warning", "Please select a session to view")
            return
        
        # Open the session folder
        session_path = Path(session['path'])
        if session_path.exists():
            if sys.platform == "darwin":  # macOS
                subprocess.run(["open", str(session_path)])
            elif sys.platform == "win32":  # Windows
                subprocess.run(["explorer", str(session_path)])
            else:  # Linux
                subprocess.run(["xdg-open", str(session_path)])
        else:
            messagebox.showerror("Error", f"Session folder not found: {session_path}")
    
    def delete_session(self):
        """Delete the selected session"""
        session = self.get_selected_session()
        if not session:
            messagebox.showwarning("Warning", "Please select a session to delete")
            return
        
        # Confirm deletion
        result = messagebox.askyesno("Confirm Delete", 
                                   f"Are you sure you want to delete the session '{session['name']}'?\n\n"
                                   "This action cannot be undone.")
        if not result:
            return
        
        try:
            import shutil
            session_path = Path(session['path'])
            if session_path.exists():
                shutil.rmtree(session_path)
                messagebox.showinfo("Success", f"Session '{session['name']}' deleted successfully")
                self.refresh_sessions()
            else:
                messagebox.showerror("Error", f"Session folder not found: {session_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete session: {str(e)}")
    
    def open_html_report(self):
        """Open HTML report for the selected session"""
        session = self.get_selected_session()
        if not session:
            messagebox.showwarning("Warning", "Please select a session to view HTML report")
            return
        
        html_file = Path(session['path']) / "trajectory_report.html"
        if html_file.exists():
            webbrowser.open(f"file://{html_file.absolute()}")
        else:
            messagebox.showinfo("Info", "No HTML report found for this session.\n\n"
                              "HTML reports are generated automatically when recording completes.")


def main():
    """Main function"""
    try:
        root = tk.Tk()
        app = WebRecorderApp(root)
        
        # Center the window
        root.update_idletasks()
        x = (root.winfo_screenwidth() // 2) - (root.winfo_width() // 2)
        y = (root.winfo_screenheight() // 2) - (root.winfo_height() // 2)
        root.geometry(f"+{x}+{y}")
        
        # Start the GUI
        root.mainloop()
    except Exception as e:
        print(f"❌ Error starting GUI: {e}")
        messagebox.showerror("Error", f"Failed to start GUI: {str(e)}")


if __name__ == "__main__":
    main() 