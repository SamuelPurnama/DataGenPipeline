# Trajectory Generation Pipeline with Graphiti Integration

This repository contains a comprehensive pipeline for generating and executing web automation instructions based on different personas, with integrated knowledge graph capabilities using Graphiti. The system uses GPT-4 to generate and augment instructions, executes them using Playwright, and can build knowledge graphs from the trajectory data.

## 🚀 Quick Start

1. **Activate the virtual environment** (already set up):
   ```bash
   source .venv/bin/activate
   ```

2. **Set up environment variables**:
   ```bash
   cp .env.template .env
   # Edit .env with your actual API keys and database credentials
   ```

3. **Start Neo4j database** (for Graphiti):
   ```bash
   docker run --name neo4j-graphiti -p 7474:7474 -p 7687:7687 -d \
     --env NEO4J_AUTH=neo4j/your_password neo4j:latest
   ```

4. **Test Graphiti integration**:
   ```bash
   python test_graphiti.py
   ```

## 📁 Project Structure

```
pipeline_2/
├── 📋 Core Pipeline
│   ├── pipeline_instruction.py          # Instruction generation
│   ├── pipeline_trajectory_generation.py # Trajectory execution
│   ├── generate_trajectory.py           # Individual trajectory runner
│   └── config.py                       # Global configuration
│
├── 🧠 AI & Knowledge
│   ├── test_graphiti.py                # Graphiti integration test
│   ├── prompts.py                      # AI prompts and templates
│   ├── text_augmentation_prompt.py     # Text augmentation logic
│   └── prompt_augmentation.py          # Prompt enhancement
│
├── 🛠️ Tools & Utilities
│   ├── tools/
│   │   ├── count_roles.py              # Role analysis
│   │   └── delete_failed_trajectories.py # Cleanup utilities
│   ├── augmentation/                   # Data augmentation tools
│   └── analyze_results.py              # Results analysis
│
├── 📊 Data & Results
│   ├── sample_data/                    # Example trajectory data
│   │   ├── calendar/                   # Calendar app trajectories
│   │   ├── scholar/                    # Google Scholar trajectories
│   │   ├── maps/                       # Maps app trajectories
│   │   └── flights/                    # Flight search trajectories
│   ├── results/                        # Generated outputs
│   └── browser_sessions/               # Persistent browser sessions
│
└── 📋 Configuration
    ├── requirements.txt                # Python dependencies
    ├── .env.template                   # Environment variables template
    ├── .venv/                         # Virtual environment
    └── README.md                       # This file
```

## 🔧 Setup & Installation

### Prerequisites

- **Python 3.13** (already configured in `.venv/`)
- **Docker** (for Neo4j database)
- **Chrome/Chromium** browser
- **OpenAI API key**
- **Neo4j database** (local or cloud)

### 1. Environment Setup

The virtual environment is already set up with all dependencies. Just activate it:

```bash
source .venv/bin/activate
```

**Installed packages include:**
- ✅ `graphiti-core` (v0.17.4) - Knowledge graph framework
- ✅ `openai` (v1.96.1) - GPT API client  
- ✅ `playwright` - Web automation
- ✅ `neo4j` (v5.28.1) - Graph database driver
- ✅ `pydantic` (v2.11.7) - Data validation
- ✅ And more (see `requirements.txt`)

### 2. Environment Variables

```bash
# Copy template and edit with your values
cp .env.template .env
```

Required variables in `.env`:
```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o

# Neo4j Database (for Graphiti)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# Chrome Browser
CHROME_EXECUTABLE_PATH=/path/to/chrome/executable
```

### 3. Neo4j Database Setup

**Option A: Docker (Recommended)**
```bash
docker run \
    --name neo4j-graphiti \
    -p 7474:7474 -p 7687:7687 \
    -d \
    -v $HOME/neo4j/data:/data \
    --env NEO4J_AUTH=neo4j/your_password \
    neo4j:latest
```

**Option B: Neo4j Aura (Cloud)**
1. Go to https://neo4j.com/cloud/aura/
2. Create free instance
3. Use provided URI and credentials in `.env`

**Option C: Neo4j Desktop**
1. Download from https://neo4j.com/download/
2. Create database with password
3. Use `bolt://localhost:7687`

## 🎯 Core Components

### 1. Trajectory Generation Pipeline

The main pipeline for generating web automation trajectories:

#### **Pipeline Instruction Generator** (`pipeline_instruction.py`)
- Generates contextual instructions for different personas
- Uses GPT-4 for intelligent instruction creation
- Supports multi-phase instruction generation
- Distributes workload across multiple Google accounts

#### **Pipeline Trajectory Generator** (`pipeline_trajectory_generation.py`)
- Executes instructions using Playwright automation
- Creates detailed execution trajectories
- Captures screenshots and interaction logs
- Handles authentication and session management

### 2. Graphiti Knowledge Graph Integration

#### **Knowledge Graph Builder** (`test_graphiti.py`)
- Converts trajectory data into knowledge graphs
- Extracts entities and relationships from web interactions
- Provides temporal tracking of user behaviors
- Enables advanced querying and analysis

**Key features:**
- 🕒 **Temporal tracking** - Track when interactions occurred
- 🔍 **Entity extraction** - Identify users, actions, and web elements
- 🌐 **Relationship mapping** - Connect related interactions and behaviors
- 📊 **Semantic search** - Query trajectories by meaning, not just text

## 🚦 Usage Guide

### Traditional Pipeline Usage

#### Step 1: Configure Parameters
Edit `config.py` to define global settings:

```python
PERSONAS_PER_ACCOUNT = 2        # Number of personas each account will process
PHASE1_NUM_INSTRUCTIONS = 5     # Number of instructions per persona in Phase 1
PHASE2_NUM_INSTRUCTIONS = 5     # Number of instructions per persona in Phase 2
RESULTS_DIR = "results"         # Folder to store outputs
URL = "https://calendar.google.com"  # Target website

# Google Accounts Configuration
ACCOUNTS = [
    {
        "email": "example1@gmail.com",
        "password": "password1",
        "user_data_dir": "example1",  # Folder name for browser session storage
        "start_idx": 0,
        "end_idx": 5
    },
    {
        "email": "example2@gmail.com",
        "password": "password2",
        "user_data_dir": "example2",
        "start_idx": 5,
        "end_idx": 10
    }
]
```

#### Step 2: Generate Phase 1 Instructions
```bash
python pipeline_instruction.py
```

This generates instructions for personas and saves to `results/instructions_phase1.json`.

#### Step 3: Generate Phase 1 Trajectories
Configure `pipeline_trajectory_generation.py`:
```python
PHASE = 1
MODE = 0  # 0: Automatic execution, 1: Interactive mode
```

Then run:
```bash
python pipeline_trajectory_generation.py
```

#### Step 4-5: Repeat for Phase 2
Update `PHASE = 2` in both scripts and repeat the process.

### Graphiti Knowledge Graph Usage

#### Basic Knowledge Graph Creation
```python
from graphiti_core import Graphiti, EpisodeType
from graphiti_core.llm_client import OpenAIClient, LLMConfig
from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig

# Initialize Graphiti (see test_graphiti.py for full example)
graphiti = Graphiti(
    neo4j_uri="bolt://localhost:7687",
    neo4j_user="neo4j", 
    neo4j_password="your_password",
    llm_client=llm_client,
    embedder=embedder
)

# Add trajectory data to knowledge graph
await graphiti.add_episode(
    name="User Calendar Interaction",
    episode_body="User searched for meetings and created a new event",
    source=EpisodeType.text,
    reference_time=datetime.now(timezone.utc),
    group_id="trajectory_001"
)
```

#### Advanced: Process Trajectory Files
```python
import json
from pathlib import Path

# Process all trajectory files in sample_data
for trajectory_file in Path("sample_data").rglob("trajectory.json"):
    with open(trajectory_file) as f:
        trajectory_data = json.load(f)
    
    # Extract meaningful information and add to graph
    await graphiti.add_episode(
        name=f"Trajectory {trajectory_file.parent.name}",
        episode_body=extract_actions_summary(trajectory_data),
        source=EpisodeType.text,
        reference_time=parse_trajectory_time(trajectory_data),
        group_id=trajectory_file.parent.name
    )
```

## 📊 Output Artifacts

### Traditional Pipeline Outputs
Each instruction generates:
- **JSON file** - Logs and metadata
- **Screenshots** - Initial and final states
- **Interaction trace** - Step-by-step actions (clicks, types, scrolls)
- **Metadata** - Timing, success status, error logs

### Graphiti Knowledge Graph Outputs
- **Entity nodes** - Users, web elements, actions, goals
- **Relationship edges** - Connections between entities
- **Temporal tracking** - When interactions occurred
- **Semantic embeddings** - For intelligent querying

## 🔍 Advanced Features

### 1. Semantic Search of Trajectories
```python
# Search for similar behaviors across all trajectories
results = await graphiti.search(
    query="user creating calendar events",
    limit=10
)
```

### 2. Temporal Analysis
```python
# Find patterns in user behavior over time
results = await graphiti.search(
    query="scheduling meetings",
    search_filters=SearchFilters(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31)
    )
)
```

### 3. Cross-Application Insights
- Track user behaviors across different applications (Calendar, Scholar, Maps)
- Identify common interaction patterns
- Discover automation opportunities

## 🛠️ Development & Customization

### Modifying Graphiti Code
Since `graphiti-core` is installed in **editable mode**:
- ✅ **Python code changes** reflect immediately - just restart your script
- ⚠️ **Dependency changes** require: `pip install -e ../graphiti-main`

### Adding New Data Sources
1. Create extraction functions for new trajectory formats
2. Define custom entity types using Pydantic models
3. Add temporal context for time-based analysis

### Custom Analysis Tools
Create new analysis scripts in `tools/` directory:
```python
# Example: Extract user behavior patterns
from graphiti_core import Graphiti

async def analyze_user_patterns():
    graphiti = Graphiti(...)
    patterns = await graphiti.search("user interaction patterns")
    # Your analysis logic here
```

## 🔧 Troubleshooting

### Common Issues

**Environment**
- `python not found` → Activate virtual environment: `source .venv/bin/activate`
- Import errors → Reinstall graphiti: `pip install -e ../graphiti-main`

**Neo4j Connection**
- Connection refused → Check Neo4j is running: `docker ps`
- Authentication failed → Verify credentials in `.env`

**OpenAI API**
- Rate limit errors → Check API usage and billing
- Invalid API key → Verify `OPENAI_API_KEY` in `.env`

**Browser Automation**
- Playwright errors → Update Chrome path in `.env`
- Session issues → Clear `browser_sessions/` directory

### Getting Help

1. **Check the logs** - Most scripts output detailed error information
2. **Verify environment** - Ensure all `.env` variables are set
3. **Test individual components** - Run `test_graphiti.py` to verify setup
4. **Clear cache** - Remove `browser_sessions/` and `results/` for fresh start

## 🎉 Summary

This enhanced pipeline enables you to:

### Traditional Capabilities
- ✅ Create scalable, persona-grounded instructions
- ✅ Generate executable web automation trajectories
- ✅ Process instructions across multiple accounts in parallel
- ✅ Iterate with multi-phase instruction augmentation

### New Knowledge Graph Capabilities  
- 🧠 **Build temporal knowledge graphs** from trajectory data
- 🔍 **Semantic search** across all user interactions
- 📊 **Pattern discovery** in user behaviors
- 🌐 **Cross-application insights** and relationship mapping
- ⏱️ **Historical analysis** of user interaction trends

The integration of Graphiti transforms your trajectory data from isolated automation logs into a rich, queryable knowledge base that can reveal insights about user behavior patterns, application usage trends, and automation opportunities.


