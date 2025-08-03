#!/usr/bin/env python3
"""
Simple UI - Just starts recorderSystem.py with a button click
"""

import asyncio
import subprocess
import sys
import webbrowser
from aiohttp import web
import aiohttp_cors

class SimpleUI:
    def __init__(self):
        self.recorder_process = None
        
    async def index_handler(self, request):
        """Serve the main HTML page"""
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Action Recorder</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            padding: 40px;
            width: 95%;
            max-width: 600px;
            text-align: center;
        }
        .logo {
            margin-bottom: 20px;
            text-align: center;
        }
        .logo img {
            width: 80px;
            height: 80px;
            object-fit: contain;
            border-radius: 10px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        .title {
            font-size: 2rem;
            color: #333;
            margin-bottom: 10px;
            font-weight: 600;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 1.1rem;
        }
        .form-group {
            margin-bottom: 25px;
            text-align: left;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
        }
        input[type="url"] {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e1e5e9;
            border-radius: 10px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input[type="url"]:focus {
            outline: none;
            border-color: #667eea;
        }
        .button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
            margin: 10px;
            min-width: 120px;
        }
        .button:hover {
            transform: translateY(-2px);
        }
        .button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        .button.stop {
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
        }
        .status {
            margin-top: 20px;
            padding: 15px;
            border-radius: 10px;
            font-weight: 500;
        }
        .status.running {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .status.stopped {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .info {
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
            text-align: left;
            font-size: 14px;
        }
        .session-list {
            margin-top: 20px;
            padding: 20px;
            background: #e9ecef;
            border-radius: 10px;
            text-align: left;
            font-size: 14px;
        }
        .session-list h3 {
            margin-bottom: 15px;
            color: #333;
            text-align: center;
        }
        .session-selector {
            margin-bottom: 15px;
        }
        .session-selector label {
            display: block;
            margin-bottom: 5px;
            color: #333;
            font-weight: 500;
        }
        .session-selector select {
            width: 100%;
            padding: 8px 12px;
            border: 2px solid #e1e5e9;
            border-radius: 6px;
            font-size: 14px;
            background: white;
        }
        .session-selector select:focus {
            outline: none;
            border-color: #667eea;
        }
        .session-info p {
            margin-bottom: 5px;
            color: #555;
        }
        .button.delete {
            background: linear-gradient(135deg, #dc3545 0%, #c82333 100%); /* Red gradient for delete */
            color: white;
            margin-top: 10px;
        }
        .button.delete:hover {
            transform: translateY(-2px);
        }
        .button.view {
            background: linear-gradient(135deg, #17a2b8 0%, #138496 100%); /* Blue gradient for view */
            color: white;
            margin-top: 10px;
            margin-left: 10px;
        }
        .button.view:hover {
            transform: translateY(-2px);
        }
        
        /* Modal styles */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
        }
        
        .modal-content {
            background-color: white;
            margin: 5% auto;
            padding: 0;
            border-radius: 10px;
            width: 90%;
            max-width: 800px;
            max-height: 80vh;
            overflow: hidden;
            box-shadow: 0 20px 40px rgba(0,0,0,0.3);
        }
        
        .modal-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .modal-header h3 {
            margin: 0;
            font-size: 1.2rem;
        }
        
        .close {
            color: white;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            line-height: 1;
        }
        
        .close:hover {
            opacity: 0.7;
        }
        
        .modal-body {
            padding: 20px;
            max-height: 60vh;
            overflow-y: auto;
        }
        
        .modal-body pre {
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 5px;
            padding: 15px;
            font-size: 12px;
            line-height: 1.4;
            white-space: pre-wrap;
            word-wrap: break-word;
            max-height: 50vh;
            overflow-y: auto;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <img src="/ai2logo.png" alt="AI2 Logo">
        </div>
        <h1 class="title">Action Recorder</h1>
        <p class="subtitle">Click to start recording - same as running python recorderSystem.py</p>
        
        <form id="recorderForm">
            <div class="form-group">
                <label for="url">Website URL:</label>
                <input type="url" id="url" name="url" value="https://calendar.google.com"
                       placeholder="Enter website URL to record">
            </div>
            <button type="submit" class="button" id="startBtn">🚀 Start Recording</button>
            <button type="button" class="button stop" id="stopBtn" disabled>⏹️ Stop Recording</button>
        </form>
        
        <div id="status" class="status stopped">
            <span id="statusText">Ready to start recording</span>
        </div>
        
        <div class="info">
            <strong>How it works:</strong><br>
            • Click "Start Recording" to run <code>python recorderSystem.py --url [your-url]</code><br>
            • Browser will open and start recording<br>
            • All logs, screenshots, and data saved to <code>data/interaction_logs/</code><br>
            • Press Ctrl+C in terminal or click "Stop Recording" to stop
        </div>
        
        <div id="sessionList" class="session-list">
            <h3>📁 Available Recording Sessions</h3>
            <div class="session-selector">
                <label for="sessionDropdown">Select Session:</label>
                <select id="sessionDropdown" onchange="loadSessionInfo()">
                    <option value="">Choose a session...</option>
                </select>
            </div>
            <div id="sessionDetails"></div>
            <button type="button" class="button delete" id="deleteBtn" onclick="deleteSession()" style="display: none;">🗑️ Delete Session</button>
            <button type="button" class="button view" id="viewTrajectoryBtn" onclick="viewTrajectory()" style="display: none;">📄 View Trajectory</button>
        </div>
        
        <!-- Trajectory Modal -->
        <div id="trajectoryModal" class="modal" style="display: none;">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>📄 Trajectory Data</h3>
                    <span class="close" onclick="closeTrajectoryModal()">&times;</span>
                </div>
                <div class="modal-body">
                    <pre id="trajectoryContent"></pre>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let isRecording = false;
        let currentSession = null;
        let allSessions = [];
        
        async function startRecording() {
            const url = document.getElementById('url').value;
            if (!url) {
                alert('Please enter a URL');
                return;
            }
            
            try {
                const response = await fetch('/api/start', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ url })
                });
                const result = await response.json();
                if (result.success) {
                    isRecording = true;
                    updateUI();
                    alert('🎯 Recording started! Check your terminal for output.');
                } else {
                    alert(`❌ Failed to start recording: ${result.error}`);
                }
            } catch (error) {
                alert(`❌ Error: ${error.message}`);
            }
        }
        
        async function stopRecording() {
            try {
                const response = await fetch('/api/stop', {
                    method: 'POST'
                });
                const result = await response.json();
                if (result.success) {
                    isRecording = false;
                    updateUI();
                    alert('⏹️ Recording stopped');
                    
                    // Reload sessions after recording stops
                    await loadAllSessions();
                } else {
                    alert(`❌ Failed to stop recording: ${result.error}`);
                }
            } catch (error) {
                alert(`❌ Error: ${error.message}`);
            }
        }
        
        async function loadAllSessions() {
            try {
                const response = await fetch('/api/sessions');
                const result = await response.json();
                if (result.success) {
                    allSessions = result.sessions;
                    populateSessionDropdown();
                }
            } catch (error) {
                console.error('Error loading sessions:', error);
            }
        }
        
        function populateSessionDropdown() {
            const dropdown = document.getElementById('sessionDropdown');
            dropdown.innerHTML = '<option value="">Choose a session...</option>';
            
            if (allSessions.length === 0) {
                const option = document.createElement('option');
                option.value = "";
                option.textContent = "No sessions found";
                option.disabled = true;
                dropdown.appendChild(option);
                return;
            }
            
            allSessions.forEach(session => {
                const option = document.createElement('option');
                option.value = session.name;
                option.textContent = `${session.name} (${session.interactions} interactions, ${session.screenshots} screenshots)`;
                dropdown.appendChild(option);
            });
        }
        
        async function loadSessionInfo() {
            const dropdown = document.getElementById('sessionDropdown');
            const selectedSession = dropdown.value;
            
            if (!selectedSession) {
                document.getElementById('sessionDetails').innerHTML = '';
                document.getElementById('deleteBtn').style.display = 'none';
                document.getElementById('viewTrajectoryBtn').style.display = 'none';
                currentSession = null;
                return;
            }
            
            // Find the selected session
            const session = allSessions.find(s => s.name === selectedSession);
            if (session) {
                currentSession = session;
                showSessionInfo(session);
                document.getElementById('deleteBtn').style.display = 'inline-block';
                document.getElementById('viewTrajectoryBtn').style.display = 'inline-block';
            }
        }
        
        function showSessionInfo(session) {
            const sessionDetails = document.getElementById('sessionDetails');
            
            sessionDetails.innerHTML = `
                <p><strong>📁 Folder:</strong> ${session.name}</p>
                <p><strong>📊 Interactions:</strong> ${session.interactions || 0}</p>
                <p><strong>📸 Screenshots:</strong> ${session.screenshots || 0}</p>
                <p><strong>🎯 Action Types:</strong> ${session.actionTypes || 'N/A'}</p>
                <p><strong>📁 Path:</strong> <code>${session.path}</code></p>
                <p><strong>📅 Created:</strong> ${session.created || 'N/A'}</p>
                <button type="button" class="button view" onclick="openHtmlReport('${session.name}')" style="margin-top: 10px;">🌐 Open HTML Report</button>
            `;
        }
        
        async function deleteSession() {
            if (!currentSession) {
                alert('No session to delete');
                return;
            }
            
            if (!confirm(`Are you sure you want to delete the session "${currentSession.name}"? This cannot be undone.`)) {
                return;
            }
            
            try {
                const response = await fetch('/api/delete-session', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ sessionName: currentSession.name })
                });
                const result = await response.json();
                if (result.success) {
                    alert('🗑️ Session deleted successfully');
                    document.getElementById('sessionDetails').innerHTML = '';
                    document.getElementById('deleteBtn').style.display = 'none';
                    document.getElementById('viewTrajectoryBtn').style.display = 'none';
                    currentSession = null;
                    await loadAllSessions(); // Reload sessions after deletion
                } else {
                    alert(`❌ Failed to delete session: ${result.error}`);
                }
            } catch (error) {
                alert(`❌ Error: ${error.message}`);
            }
        }

        async function viewTrajectory() {
            if (!currentSession) {
                alert('No session selected to view trajectory.');
                return;
            }

            const trajectoryModal = document.getElementById('trajectoryModal');
            const trajectoryContent = document.getElementById('trajectoryContent');

            try {
                const response = await fetch(`/api/trajectory/${currentSession.name}`);
                const result = await response.json();

                if (result.success) {
                    trajectoryContent.textContent = JSON.stringify(result.trajectory, null, 2);
                    trajectoryModal.style.display = 'block';
                } else {
                    trajectoryContent.textContent = `Error loading trajectory for session "${currentSession.name}": ${result.error}`;
                    trajectoryModal.style.display = 'block';
                }
            } catch (error) {
                trajectoryContent.textContent = `❌ Error loading trajectory: ${error.message}`;
                trajectoryModal.style.display = 'block';
            }
        }

        function closeTrajectoryModal() {
            document.getElementById('trajectoryModal').style.display = 'none';
        }
        
        async function openHtmlReport(sessionName) {
            try {
                // Check if HTML report exists first
                const response = await fetch(`/api/html-report/${sessionName}`);
                
                if (response.ok) {
                    // Open the HTML report in a new tab
                    window.open(`/api/html-report/${sessionName}`, '_blank');
                } else {
                    alert(`❌ HTML report not found for session "${sessionName}"`);
                }
            } catch (error) {
                alert(`❌ Error opening HTML report: ${error.message}`);
            }
        }
        
        // Close modal when clicking outside
        window.onclick = function(event) {
            const modal = document.getElementById('trajectoryModal');
            if (event.target === modal) {
                closeTrajectoryModal();
            }
        }
        
        // Close modal with Escape key
        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') {
                closeTrajectoryModal();
            }
        });
        
        function updateUI() {
            const startBtn = document.getElementById('startBtn');
            const stopBtn = document.getElementById('stopBtn');
            const status = document.getElementById('status');
            const statusText = document.getElementById('statusText');
            
            if (isRecording) {
                startBtn.disabled = true;
                stopBtn.disabled = false;
                status.className = 'status running';
                statusText.textContent = 'Recording in progress...';
            } else {
                startBtn.disabled = false;
                stopBtn.disabled = true;
                status.className = 'status stopped';
                statusText.textContent = 'Ready to start recording';
            }
        }
        
        // Event listeners
        document.getElementById('recorderForm').addEventListener('submit', function(e) {
            e.preventDefault();
            startRecording();
        });
        
        document.getElementById('stopBtn').addEventListener('click', stopRecording);
        
        // Load sessions when page loads
        window.addEventListener('load', function() {
            loadAllSessions();
        });
    </script>
</body>
</html>
        """
        return web.Response(text=html, content_type='text/html')
    
    async def logo_handler(self, request):
        """Serve the AI2 logo"""
        try:
            from pathlib import Path
            logo_path = Path("ai2logo.png")
            if logo_path.exists():
                with open(logo_path, 'rb') as f:
                    logo_data = f.read()
                return web.Response(body=logo_data, content_type='image/png')
            else:
                return web.Response(status=404, text="Logo not found")
        except Exception as e:
            return web.Response(status=500, text=f"Error serving logo: {e}")
    
    async def start_recorder_api(self, request):
        """API endpoint to start the recorder"""
        try:
            data = await request.json()
            url = data.get('url', 'https://calendar.google.com')
            
            print(f"🎯 Starting recorder for URL: {url}")
            
            # Start recorderSystem.py as subprocess
            cmd = [sys.executable, 'recorderSystem.py', '--url', url]
            self.recorder_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            print(f"✅ Process started with PID: {self.recorder_process.pid}")
            print("💡 Check your terminal for recorder output")
            
            return web.json_response({
                'success': True,
                'message': 'Recorder started successfully'
            })
        except Exception as e:
            print(f"❌ Error starting recorder: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            })
    
    async def stop_recorder_api(self, request):
        """API endpoint to stop the recorder"""
        try:
            if self.recorder_process:
                print("⏹️ Stopping recorder process...")
                
                # Send SIGTERM for graceful shutdown
                self.recorder_process.terminate()
                
                try:
                    # Give the process time to save its data (up to 5 seconds)
                    print("⏳ Waiting for recorder to save data...")
                    self.recorder_process.wait(timeout=5)
                    print("✅ Recorder process stopped gracefully")
                except subprocess.TimeoutExpired:
                    print("⚠️ Process didn't stop gracefully, forcing termination...")
                    # Force kill if it doesn't stop gracefully
                    self.recorder_process.kill()
                    try:
                        self.recorder_process.wait(timeout=2)
                        print("✅ Recorder process force-killed")
                    except subprocess.TimeoutExpired:
                        print("❌ Could not terminate process")
                
                self.recorder_process = None
                
                # Wait a moment for file system to sync
                import asyncio
                await asyncio.sleep(1)
                
                # Generate trajectory.json from the recorded data
                print("📊 Generating trajectory.json from recorded data...")
                await self.generate_trajectory_json()
                
                return web.json_response({
                    'success': True,
                    'message': 'Recorder stopped successfully and trajectory.json generated'
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': 'No recorder process running'
                })
        except Exception as e:
            print(f"❌ Error stopping recorder: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            })
    
    async def generate_trajectory_json(self):
        """Generate trajectory.json from the recorded interaction logs"""
        try:
            import json
            import os
            from pathlib import Path
            from datetime import datetime
            
            # Find the most recent interaction_logs session
            interaction_logs_dir = Path("data/interaction_logs")
            if not interaction_logs_dir.exists():
                print("⚠️ No interaction_logs directory found")
                return
            
            # Get the most recent session directory
            session_dirs = [d for d in interaction_logs_dir.iterdir() if d.is_dir() and d.name.startswith("session_")]
            if not session_dirs:
                print("⚠️ No session directories found")
                return
            
            # Sort by modification time to get the most recent
            latest_session = max(session_dirs, key=lambda x: x.stat().st_mtime)
            print(f"📁 Processing session: {latest_session.name}")
            
            # Check if trajectory.json already exists
            trajectory_file = latest_session / "trajectory.json"
            metadata_file = latest_session / "metadata.json"
            
            if trajectory_file.exists():
                print(f"✅ Trajectory.json found: {trajectory_file}")
                
                # Read and display trajectory info
                with open(trajectory_file, 'r') as f:
                    trajectory_data = json.load(f)
                
                print(f"📈 Steps recorded: {len(trajectory_data)}")
                
                # Show some stats
                action_types = {}
                for step_data in trajectory_data.values():
                    action_name = step_data.get('action', {}).get('action_output', {}).get('action_name', 'unknown')
                    action_types[action_name] = action_types.get(action_name, 0) + 1
                
                print(f"🎯 Action types: {action_types}")
                
                # Check for metadata
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    print(f"📊 Session info: {metadata.get('total_interactions', 0)} interactions")
                    print(f"📸 Screenshots: {metadata.get('screenshots_count', 0)}")
                else:
                    print("⚠️ No metadata.json found, but trajectory.json exists")
                
            else:
                print("⚠️ Trajectory.json not found")
                
                # Check what files exist in the session
                files = list(latest_session.iterdir())
                print(f"📁 Files in session: {[f.name for f in files]}")
                
                # Check if metadata exists
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    print(f"📊 Session info: {metadata.get('total_interactions', 0)} interactions")
                    print(f"📸 Screenshots: {metadata.get('screenshots_count', 0)}")
                else:
                    print("⚠️ No metadata.json found - recorder may not have finished properly")
                
        except Exception as e:
            print(f"❌ Error generating trajectory.json: {e}")
            import traceback
            traceback.print_exc()
    
    async def get_session_api(self, request):
        """API endpoint to get the most recent session info"""
        try:
            import json
            from pathlib import Path
            
            # Find the most recent interaction_logs session
            interaction_logs_dir = Path("data/interaction_logs")
            if not interaction_logs_dir.exists():
                return web.json_response({
                    'success': False,
                    'error': 'No interaction_logs directory found'
                })
            
            # Get the most recent session directory
            session_dirs = [d for d in interaction_logs_dir.iterdir() if d.is_dir() and d.name.startswith("session_")]
            if not session_dirs:
                return web.json_response({
                    'success': False,
                    'error': 'No session directories found'
                })
            
            # Sort by modification time to get the most recent
            latest_session = max(session_dirs, key=lambda x: x.stat().st_mtime)
            
            # Get session info
            session_info = {
                'name': latest_session.name,
                'path': str(latest_session),
                'interactions': 0,
                'screenshots': 0,
                'actionTypes': 'N/A'
            }
            
            # Check for trajectory.json
            trajectory_file = latest_session / "trajectory.json"
            if trajectory_file.exists():
                with open(trajectory_file, 'r') as f:
                    trajectory_data = json.load(f)
                session_info['interactions'] = len(trajectory_data)
                
                # Count action types
                action_types = {}
                for step_data in trajectory_data.values():
                    action_name = step_data.get('action', {}).get('action_output', {}).get('action_name', 'unknown')
                    action_types[action_name] = action_types.get(action_name, 0) + 1
                session_info['actionTypes'] = ', '.join([f"{k}({v})" for k, v in action_types.items()])
            
            # Check for metadata.json
            metadata_file = latest_session / "metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                session_info['screenshots'] = metadata.get('screenshots_count', 0)
            
            # Count screenshots in images directory
            images_dir = latest_session / "images"
            if images_dir.exists():
                screenshot_count = len(list(images_dir.glob("*.png")))
                session_info['screenshots'] = screenshot_count
            
            return web.json_response({
                'success': True,
                'session': session_info
            })
            
        except Exception as e:
            print(f"❌ Error getting session info: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            })
    
    async def get_all_sessions_api(self, request):
        """API endpoint to get all available sessions"""
        try:
            import json
            from pathlib import Path
            from datetime import datetime
            
            # Find all interaction_logs sessions
            interaction_logs_dir = Path("data/interaction_logs")
            if not interaction_logs_dir.exists():
                return web.json_response({
                    'success': True,
                    'sessions': []
                })
            
            # Get all session directories
            session_dirs = [d for d in interaction_logs_dir.iterdir() if d.is_dir() and d.name.startswith("session_")]
            if not session_dirs:
                return web.json_response({
                    'success': True,
                    'sessions': []
                })
            
            # Sort by modification time (newest first)
            session_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            sessions = []
            for session_dir in session_dirs:
                session_info = {
                    'name': session_dir.name,
                    'path': str(session_dir),
                    'interactions': 0,
                    'screenshots': 0,
                    'actionTypes': 'N/A',
                    'created': datetime.fromtimestamp(session_dir.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                }
                
                # Check for trajectory.json
                trajectory_file = session_dir / "trajectory.json"
                if trajectory_file.exists():
                    with open(trajectory_file, 'r') as f:
                        trajectory_data = json.load(f)
                    session_info['interactions'] = len(trajectory_data)
                    
                    # Count action types
                    action_types = {}
                    for step_data in trajectory_data.values():
                        action_name = step_data.get('action', {}).get('action_output', {}).get('action_name', 'unknown')
                        action_types[action_name] = action_types.get(action_name, 0) + 1
                    session_info['actionTypes'] = ', '.join([f"{k}({v})" for k, v in action_types.items()])
                
                # Count screenshots in images directory
                images_dir = session_dir / "images"
                if images_dir.exists():
                    screenshot_count = len(list(images_dir.glob("*.png")))
                    session_info['screenshots'] = screenshot_count
                
                # Check for metadata.json
                metadata_file = session_dir / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    if session_info['screenshots'] == 0:  # Only use metadata if we didn't count from images
                        session_info['screenshots'] = metadata.get('screenshots_count', 0)
                
                sessions.append(session_info)
            
            return web.json_response({
                'success': True,
                'sessions': sessions
            })
            
        except Exception as e:
            print(f"❌ Error getting all sessions: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            })
    
    async def delete_session_api(self, request):
        """API endpoint to delete a session"""
        try:
            from pathlib import Path
            import shutil
            
            data = await request.json()
            session_name = data.get('sessionName')
            
            if not session_name:
                return web.json_response({
                    'success': False,
                    'error': 'No session name provided'
                })
            
            # Find the session directory
            interaction_logs_dir = Path("interaction_logs")
            session_dir = interaction_logs_dir / session_name
            
            if not session_dir.exists():
                return web.json_response({
                    'success': False,
                    'error': f'Session "{session_name}" not found'
                })
            
            # Delete the session directory
            shutil.rmtree(session_dir)
            
            print(f"🗑️ Deleted session: {session_name}")
            
            return web.json_response({
                'success': True,
                'message': f'Session "{session_name}" deleted successfully'
            })
            
        except Exception as e:
            print(f"❌ Error deleting session: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            })
    
    async def get_trajectory_api(self, request):
        """API endpoint to get trajectory.json content for a specific session"""
        try:
            from pathlib import Path
            import json
            
            session_name = request.match_info['session_name']
            
            # Find the session directory
            interaction_logs_dir = Path("data/interaction_logs")
            session_dir = interaction_logs_dir / session_name
            
            if not session_dir.exists():
                return web.json_response({
                    'success': False,
                    'error': f'Session "{session_name}" not found'
                })
            
            # Check for trajectory.json
            trajectory_file = session_dir / "trajectory.json"
            if not trajectory_file.exists():
                return web.json_response({
                    'success': False,
                    'error': f'Trajectory.json not found for session "{session_name}"'
                })
            
            # Read and return trajectory data
            with open(trajectory_file, 'r') as f:
                trajectory_data = json.load(f)
            
            return web.json_response({
                'success': True,
                'trajectory': trajectory_data
            })
            
        except Exception as e:
            print(f"❌ Error getting trajectory: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            })
    
    async def get_html_report_api(self, request):
        """Serve HTML report for a specific session"""
        try:
            from pathlib import Path
            
            session_name = request.match_info['session_name']
            
            # Find the session directory
            interaction_logs_dir = Path("data/interaction_logs")
            session_dir = interaction_logs_dir / session_name
            html_file = session_dir / 'trajectory_report.html'
            
            if not html_file.exists():
                return web.json_response({'success': False, 'error': 'HTML report not found'})
            
            # Return the HTML file as a response
            with open(html_file, 'r') as f:
                html_content = f.read()
            
            return web.Response(text=html_content, content_type='text/html')
            
        except Exception as e:
            print(f"❌ Error serving HTML report: {e}")
            return web.json_response({'success': False, 'error': str(e)})
    
    async def get_screenshot_api(self, request):
        """Serve screenshot images for a specific session and step"""
        try:
            from pathlib import Path
            
            session_name = request.match_info['session_name']
            step_num = request.match_info['step_num']
            
            # Find the screenshot file
            interaction_logs_dir = Path("data/interaction_logs")
            session_dir = interaction_logs_dir / session_name
            screenshot_file = session_dir / "images" / f"screenshot_{step_num.zfill(3)}.png"
            
            print(f"🔍 Looking for screenshot: {screenshot_file}")
            print(f"🔍 Session name: {session_name}")
            print(f"🔍 Step num: {step_num}")
            print(f"🔍 Session dir exists: {session_dir.exists()}")
            print(f"🔍 Images dir exists: {(session_dir / 'images').exists()}")
            
            if not screenshot_file.exists():
                print(f"❌ Screenshot not found: {screenshot_file}")
                return web.Response(status=404, text="Screenshot not found")
            
            print(f"✅ Screenshot found: {screenshot_file}")
            
            # Return the image file
            with open(screenshot_file, 'rb') as f:
                image_data = f.read()
            
            return web.Response(body=image_data, content_type='image/png')
            
        except Exception as e:
            print(f"❌ Error serving screenshot: {e}")
            return web.Response(status=500, text=f"Error serving screenshot: {e}")

async def main():
    """Main function to start the web server"""
    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    
    ui = SimpleUI()
    app.router.add_get('/', ui.index_handler)
    app.router.add_get('/ai2logo.png', ui.logo_handler) # Added this line
    app.router.add_post('/api/start', ui.start_recorder_api)
    app.router.add_post('/api/stop', ui.stop_recorder_api)
    app.router.add_get('/api/session', ui.get_session_api)
    app.router.add_get('/api/sessions', ui.get_all_sessions_api) # Added this line
    app.router.add_post('/api/delete-session', ui.delete_session_api)
    app.router.add_get('/api/trajectory/{session_name}', ui.get_trajectory_api) # Added this line
    app.router.add_get('/api/html-report/{session_name}', ui.get_html_report_api) # Added this line
    app.router.add_get('/api/screenshot/{session_name}/{step_num}', ui.get_screenshot_api) # Added this line
    
    for route in list(app.router.routes()):
        cors.add(route)
    
    port = 8080
    print(f"🎯 Simple Recorder UI starting on http://localhost:{port}")
    print("🌐 Opening browser...")
    webbrowser.open(f'http://localhost:{port}')
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', port)
    await site.start()
    
    print(f"✅ Server running at http://localhost:{port}")
    print("💡 Use Ctrl+C to stop the server")
    
    try:
        await asyncio.sleep(float('inf'))
    except KeyboardInterrupt:
        print("\n⏹️ Stopping server...")
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 