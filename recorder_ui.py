#!/usr/bin/env python3
"""
Simple Recorder UI - Start recorderSystem.py with a web interface
"""

import asyncio
import subprocess
import sys
import webbrowser
from aiohttp import web
import aiohttp_cors

class RecorderUI:
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
    <title>Web Recorder</title>
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
            font-size: 3rem;
            color: #667eea;
            margin-bottom: 20px;
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
        
        .features {
            margin-top: 20px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        
        .feature {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        
        .feature-icon {
            font-size: 2rem;
            margin-bottom: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">🎯</div>
        <h1 class="title">Web Recorder</h1>
        <p class="subtitle">Record web interactions and generate Playwright automation scripts</p>
        
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
        
        <div class="features">
            <div class="feature">
                <div class="feature-icon">🖱️</div>
                <strong>Clicks</strong><br>
                Capture all mouse clicks
            </div>
            <div class="feature">
                <div class="feature-icon">⌨️</div>
                <strong>Typing</strong><br>
                Record form inputs
            </div>
            <div class="feature">
                <div class="feature-icon">📸</div>
                <strong>Screenshots</strong><br>
                Auto-capture screenshots
            </div>
            <div class="feature">
                <div class="feature-icon">🎭</div>
                <strong>Playwright</strong><br>
                Generate automation code
            </div>
        </div>
        
        <div class="info">
            <strong>How it works:</strong><br>
            • Click "Start Recording" to run <code>python recorderSystem.py --url [your-url]</code><br>
            • Browser will open and start recording<br>
            • All logs, screenshots, and data saved to <code>interaction_logs/</code><br>
            • Press Ctrl+C in terminal or click "Stop Recording" to stop<br>
            • Check terminal for real-time logs
        </div>
    </div>
    
    <script>
        let isRecording = false;
        
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
                } else {
                    alert(`❌ Failed to stop recording: ${result.error}`);
                }
            } catch (error) {
                alert(`❌ Error: ${error.message}`);
            }
        }
        
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
        
        document.getElementById('recorderForm').addEventListener('submit', function(e) {
            e.preventDefault();
            startRecording();
        });
        
        document.getElementById('stopBtn').addEventListener('click', stopRecording);
    </script>
</body>
</html>
        """
        return web.Response(text=html, content_type='text/html')
    
    async def start_recorder_api(self, request):
        """API endpoint to start the recorder"""
        try:
            data = await request.json()
            url = data.get('url', 'https://calendar.google.com')
            
            if self.recorder_process and self.recorder_process.poll() is None:
                return web.json_response({'success': False, 'error': 'Recorder is already running'})
            
            # Start recorderSystem.py as subprocess
            cmd = [sys.executable, 'recorderSystem.py', '--url', url]
            self.recorder_process = subprocess.Popen(
                cmd,
                stdout=None,  # Direct to terminal
                stderr=None,  # Direct to terminal
                text=True
            )
            
            return web.json_response({'success': True})
            
        except Exception as e:
            return web.json_response({'success': False, 'error': str(e)})
    
    async def stop_recorder_api(self, request):
        """API endpoint to stop the recorder"""
        try:
            if self.recorder_process and self.recorder_process.poll() is None:
                self.recorder_process.terminate()
                self.recorder_process.wait(timeout=5)
                return web.json_response({'success': True})
            else:
                return web.json_response({'success': False, 'error': 'No recorder running'})
                
        except Exception as e:
            return web.json_response({'success': False, 'error': str(e)})

async def main():
    """Start the web server"""
    ui = RecorderUI()
    
    app = web.Application()
    
    # Add CORS middleware
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })
    
    # Add routes
    app.router.add_get('/', ui.index_handler)
    app.router.add_post('/api/start', ui.start_recorder_api)
    app.router.add_post('/api/stop', ui.stop_recorder_api)
    
    # Add CORS to all routes
    for route in list(app.router.routes()):
        cors.add(route)
    
    # Start server
    port = 8080
    print(f"🌐 Web Recorder UI starting on http://localhost:{port}")
    print("💡 Open your browser to start recording!")
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', port)
    await site.start()
    
    # Open browser
    webbrowser.open(f'http://localhost:{port}')
    
    print("🚀 Server started! Press Ctrl+C to stop.")
    
    try:
        await asyncio.Future()  # Run forever
    except KeyboardInterrupt:
        print("\n⏹️  Shutting down...")
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 