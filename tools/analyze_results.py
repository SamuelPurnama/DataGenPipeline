import os
import json
from typing import Dict, List, Tuple, Set
from datetime import datetime

# Try to import from config, fallback to default
try:
    from config import RESULTS_DIR
except ImportError:
    # Fallback if config module not found
    RESULTS_DIR = "data/results"

# Cost configuration
COST_PER_1K_TOKENS = 0.003

def analyze_results() -> Tuple[Dict, List[Dict]]:
    """Analyze all results and return summary statistics and incomplete data."""
    total_tasks = 0
    successful_tasks = 0
    tasks_data = []
    incomplete_data = []
    phase_stats = {'phase1': {'total': 0, 'success': 0, 'failed': 0},
                  'phase2': {'total': 0, 'success': 0, 'failed': 0}}
    persona_set: Set[str] = set()
    total_images = 0
    total_steps = 0
    total_steps_success = 0
    total_tokens = 0
    total_tokens_success = 0
    total_runtime_success = 0

    print(f"🔍 Searching for data in: {RESULTS_DIR}")
    
    # Check if directory exists
    if not os.path.exists(RESULTS_DIR):
        print(f"❌ Results directory not found: {RESULTS_DIR}")
        return {
            'total_tasks': 0,
            'successful_tasks': 0,
            'failed_tasks': 0,
            'success_rate': 0,
            'incomplete_tasks': 0,
            'phase_stats': phase_stats
        }, [], []

    # Get all calendar directories
    calendar_dirs = [d for d in os.listdir(RESULTS_DIR) 
                    if os.path.isdir(os.path.join(RESULTS_DIR, d)) 
                    and d.startswith('calendar_')]
    
    print(f"📁 Found {len(calendar_dirs)} calendar directories")
    
    for calendar_dir in calendar_dirs:
        dir_path = os.path.join(RESULTS_DIR, calendar_dir)
        files = os.listdir(dir_path)
        metadata_path = os.path.join(dir_path, 'metadata.json')
        
        if 'metadata.json' in files:
            total_tasks += 1
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                # Persona
                persona = metadata.get('persona', None)
                if persona:
                    persona_set.add(persona)
                # Images (count files in images subfolder)
                images_dir = os.path.join(dir_path, 'images')
                if os.path.exists(images_dir):
                    total_images += len([img for img in os.listdir(images_dir) if os.path.isfile(os.path.join(images_dir, img))])
                # Update phase statistics
                phase_num = metadata.get('phase', 0)
                phase_key = f'phase{phase_num}'
                if phase_key in phase_stats:
                    phase_stats[phase_key]['total'] += 1
                    if metadata.get('success', False):
                        phase_stats[phase_key]['success'] += 1
                        successful_tasks += 1
                    else:
                        phase_stats[phase_key]['failed'] += 1
                # Steps, tokens, runtime
                steps = metadata.get('total_steps', 0)
                tokens = metadata.get('total_tokens', 0)
                total_steps += steps
                total_tokens += tokens
                is_success = metadata.get('success', False)
                if is_success:
                    total_steps_success += steps
                    total_tokens_success += tokens
                    total_runtime_success += metadata.get('runtime_sec', 0)
                # Add task data
                task_info = {
                    'uuid': metadata['eps_name'],
                    'goal': metadata['goal'],
                    'total_steps': steps,
                    'success': is_success,
                    'total_tokens': tokens,
                    'phase': f'Phase {metadata["phase"]}',
                    'runtime_sec': metadata['runtime_sec']
                }
                tasks_data.append(task_info)
                # Check for incomplete data
                missing_files = []
                required_files = ['trajectory.json', 'trajectory.html']
                for file in required_files:
                    if file not in files:
                        missing_files.append(file)
                if missing_files:
                    incomplete_data.append({
                        'uuid': metadata['eps_name'],
                        'missing_files': missing_files,
                        'goal': metadata['goal']
                    })
            except Exception as e:
                incomplete_data.append({
                    'uuid': calendar_dir,
                    'error': f"Error reading metadata: {str(e)}"
                })
    # Calculate statistics
    avg_steps_success = total_steps_success / successful_tasks if successful_tasks else 0
    avg_tokens = total_tokens / total_tasks if total_tasks else 0
    avg_cost_success = (total_tokens_success / 1000 * COST_PER_1K_TOKENS) / successful_tasks if successful_tasks else 0
    avg_cost_all = (total_tokens / 1000 * COST_PER_1K_TOKENS) / total_tasks if total_tasks else 0
    avg_runtime_success = total_runtime_success / successful_tasks if successful_tasks else 0
    stats = {
        'total_tasks': total_tasks,
        'successful_tasks': successful_tasks,
        'failed_tasks': total_tasks - successful_tasks,
        'success_rate': (successful_tasks / total_tasks * 100) if total_tasks > 0 else 0,
        'incomplete_tasks': len(incomplete_data),
        'phase_stats': phase_stats,
        'avg_steps_success': avg_steps_success,
        'total_personas': len(persona_set),
        'total_images': total_images,
        'avg_tokens': avg_tokens,
        'avg_cost_success': avg_cost_success,
        'avg_cost_all': avg_cost_all,
        'avg_runtime_success': avg_runtime_success
    }
    print(f"\n📈 Final Statistics:")
    for k, v in stats.items():
        print(f"{k}: {v}")
    return stats, tasks_data, incomplete_data

def generate_html_report(stats: Dict, tasks_data: List[Dict], incomplete_data: List[Dict]) -> str:
    """Generate HTML report with analysis results."""
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trajectory Generation Results Analysis</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1, h2 {{ color: #333; }}
        .stats, .advstats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }}
        .stat-card, .advstat-card {{ background-color: #fff; padding: 15px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stat-card h3, .advstat-card h3 {{ margin: 0; color: #666; }}
        .stat-card p, .advstat-card p {{ margin: 10px 0 0; font-size: 24px; font-weight: bold; color: #4b2e83; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f8f9fa; cursor: pointer; user-select: none; }}
        th:hover {{ background-color: #e9ecef; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .success {{ color: #4CAF50; }}
        .failure {{ color: #f44336; }}
        .incomplete {{ color: #ff9800; }}
        .sort-icon {{ margin-left: 5px; }}
        a {{ color: #4b2e83; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .table-controls {{ margin: 20px 0; display: flex; gap: 20px; align-items: center; }}
        .search-box {{ padding: 8px; border: 1px solid #ddd; border-radius: 4px; width: 200px; }}
        .sort-select {{ padding: 8px; border: 1px solid #ddd; border-radius: 4px; }}
        .phase-stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 20px 0; }}
        .phase-card {{ background-color: #fff; padding: 15px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .phase-card h3 {{ margin: 0; color: #666; }}
        .phase-card p {{ margin: 10px 0; }}
        .progress-bar {{ width: 100%; height: 20px; background-color: #f0f0f0; border-radius: 10px; overflow: hidden; margin: 5px 0; }}
        .progress-fill {{ height: 100%; background-color: #4b2e83; transition: width 0.3s ease; }}
    </style>
    <script>
        function filterTable(tableId) {{
            const table = document.getElementById(tableId);
            const searchBox = document.getElementById(tableId + 'Search');
            const searchText = searchBox.value.toLowerCase();
            const rows = table.getElementsByTagName('tr');
            let visibleCount = 0;
            for (let i = 1; i < rows.length; i++) {{
                const row = rows[i];
                const cells = row.getElementsByTagName('td');
                let found = false;
                for (let j = 0; j < cells.length; j++) {{
                    const cell = cells[j];
                    if (cell.textContent.toLowerCase().indexOf(searchText) > -1) {{
                        found = true;
                        break;
                    }}
                }}
                if (found) {{
                    row.style.display = '';
                    visibleCount++;
                }} else {{
                    row.style.display = 'none';
                }}
            }}
            // Update the count display if this is the tasks table
            if (tableId === 'tasksTable') {{
                const countSpan = document.getElementById('tasksTableCount');
                if (countSpan) {{
                    countSpan.textContent = 'Showing ' + visibleCount + ' trajectories';
                }}
            }}
        }}
        function sortTable(table, column, type) {{
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const header = table.querySelector('th:nth-child(' + (column + 1) + ')');
            const currentDirection = header.getAttribute('data-sort') || 'asc';
            const newDirection = currentDirection === 'asc' ? 'desc' : 'asc';
            table.querySelectorAll('th').forEach(th => {{
                th.setAttribute('data-sort', '');
                th.innerHTML = th.innerHTML.replace(' ↑', '').replace(' ↓', '');
            }});
            header.setAttribute('data-sort', newDirection);
            header.innerHTML += newDirection === 'asc' ? ' ↑' : ' ↓';
            rows.sort((a, b) => {{
                let aVal = a.cells[column].textContent;
                let bVal = b.cells[column].textContent;
                if (type === 'number') {{
                    aVal = parseFloat(aVal) || 0;
                    bVal = parseFloat(bVal) || 0;
                }} else if (type === 'boolean') {{
                    aVal = aVal.toLowerCase() === 'true';
                    bVal = bVal.toLowerCase() === 'true';
                }}
                if (aVal < bVal) return newDirection === 'asc' ? -1 : 1;
                if (aVal > bVal) return newDirection === 'asc' ? 1 : -1;
                return 0;
            }});
            rows.forEach(row => tbody.appendChild(row));
        }}
    </script>
</head>
<body>
    <div class="container">
        <h1>Trajectory Generation Results Analysis</h1>
        <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <h2>Summary Statistics</h2>
        <div class="stats">
            <div class="stat-card"><h3>Total Tasks</h3><p>{stats['total_tasks']}</p></div>
            <div class="stat-card"><h3>Successful Tasks</h3><p class="success">{stats['successful_tasks']}</p></div>
            <div class="stat-card"><h3>Failed Tasks</h3><p class="failure">{stats['failed_tasks']}</p></div>
            <div class="stat-card"><h3>Success Rate</h3><p>{stats['success_rate']:.1f}%</p></div>
        </div>
        <h2>Advanced Statistics</h2>
        <div class="advstats">
            <div class="advstat-card"><h3>Average Steps/Successful Trajectory</h3><p>{stats['avg_steps_success']:.2f}</p></div>
            <div class="advstat-card"><h3>Total Images</h3><p>{stats['total_images']}</p></div>
            <div class="advstat-card"><h3>Average Tokens/Trajectory</h3><p>{stats['avg_tokens']:.2f}</p></div>
            <div class="advstat-card"><h3>Average Cost/All Trajectories</h3><p>${stats['avg_cost_all']:.5f}</p></div>
            <div class="advstat-card"><h3>Average Cost/Successful Trajectory</h3><p>${stats['avg_cost_success']:.5f}</p></div>
            <div class="advstat-card"><h3>Average Running Time/Successful Trajectory</h3><p>{stats['avg_runtime_success']:.2f} sec</p></div>
        </div>
        <h2>Phase Distribution</h2>
        <div class="phase-stats">
            {''.join(f"""
            <div class="phase-card">
                <h3>{phase.upper()}</h3>
                <p>Total Tasks: {stats['phase_stats'][phase]['total']}</p>
                <p>Successful: {stats['phase_stats'][phase]['success']}</p>
                <p>Failed: {stats['phase_stats'][phase]['failed']}</p>
                <p>Success Rate: {f"{(stats['phase_stats'][phase]['success'] / stats['phase_stats'][phase]['total'] * 100):.1f}" if stats['phase_stats'][phase]['total'] > 0 else "0.0"}%</p>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {f"{(stats['phase_stats'][phase]['success'] / stats['phase_stats'][phase]['total'] * 100):.1f}" if stats['phase_stats'][phase]['total'] > 0 else "0.0"}%"></div>
                </div>
            </div>
            """ for phase in ['phase1', 'phase2'])}
        </div>
        <h2>Task Details</h2>
        <div class="table-controls">
            <input type="text" id="tasksTableSearch" class="search-box" placeholder="Search tasks..." onkeyup="filterTable('tasksTable')">
            <span id="tasksTableCount" style="margin-left: 16px; font-weight: bold; color: #4b2e83;">Showing {len(tasks_data)} trajectories</span>
        </div>
        <table id="tasksTable">
            <tr>
                <th onclick="sortTable(this.parentElement.parentElement, 0, 'string')">UUID</th>
                <th onclick="sortTable(this.parentElement.parentElement, 1, 'string')">Goal</th>
                <th onclick="sortTable(this.parentElement.parentElement, 2, 'number')">Total Steps</th>
                <th onclick="sortTable(this.parentElement.parentElement, 3, 'boolean')">Success</th>
                <th onclick="sortTable(this.parentElement.parentElement, 4, 'number')">Total Tokens</th>
                <th onclick="sortTable(this.parentElement.parentElement, 5, 'string')">Phase</th>
                <th onclick="sortTable(this.parentElement.parentElement, 6, 'number')">Runtime (sec)</th>
            </tr>
            {''.join(f"""
            <tr>
                <td><a href="{task['uuid']}/trajectory.html" target="_blank">{task['uuid']}</a></td>
                <td>{task['goal']}</td>
                <td>{task['total_steps']}</td>
                <td class="{'success' if task['success'] else 'failure'}">{task['success']}</td>
                <td>{task['total_tokens']}</td>
                <td>{task['phase']}</td>
                <td>{task['runtime_sec']:.1f}</td>
            </tr>
            """ for task in tasks_data)}
        </table>
        <h2>Incomplete Data</h2>
        <div class="table-controls">
            <input type="text" id="incompleteTableSearch" class="search-box" placeholder="Search incomplete data..." onkeyup="filterTable('incompleteTable')">
        </div>
        <table id="incompleteTable">
            <tr>
                <th onclick="sortTable(this.parentElement.parentElement, 0, 'string')">UUID</th>
                <th onclick="sortTable(this.parentElement.parentElement, 1, 'string')">Goal</th>
                <th onclick="sortTable(this.parentElement.parentElement, 2, 'string')">Missing Files/Issues</th>
            </tr>
            {''.join(f"""
            <tr>
                <td><a href="{item['uuid']}/trajectory.html" target="_blank">{item['uuid']}</a></td>
                <td>{item.get('goal', 'N/A')}</td>
                <td>{', '.join(item.get('missing_files', [item.get('error', 'Unknown issue')]))}</td>
            </tr>
            """ for item in incomplete_data)}
        </table>
    </div>
</body>
</html>"""
    return html_content

def main():
    # Analyze results
    stats, tasks_data, incomplete_data = analyze_results()
    
    # Generate HTML report
    html_content = generate_html_report(stats, tasks_data, incomplete_data)
    
    # Save report
    report_path = os.path.join(RESULTS_DIR, 'analysis_report.html')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ Analysis report generated: {report_path}")

if __name__ == "__main__":
    main() 