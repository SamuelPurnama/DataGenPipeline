# Prompt Augmentation Pipeline

This repository contains a pipeline for generating and executing web automation instructions based on different personas. The system uses GPT-4 to generate and augment instructions, then executes them using Playwright.

## Overview

The pipeline consists of two main components:

1. **Pipeline Instruction Generator** (`pipeline_instruction.py`)
   - Generates initial and augmented instructions for different personas
   - Uses GPT-4 to create contextually relevant instructions
   - Supports two phases of instruction generation
   - Distributes personas among multiple Google accounts for parallel processing

2. **Pipeline Trajectory Generator** (`pipeline_trajectory_generation.py`)
   - Executes the generated instructions using Playwright
   - Creates detailed trajectories of the automation process
   - Saves screenshots and execution logs for each instruction

## Setup

1. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up environment variables in `.env`:
   ```env
   CHROME_EXECUTABLE_PATH=/path/to/chrome/executable
   OPENAI_API_KEY=your_openai_api_key
   ```

## Step-by-Step Usage Flow

### Step 1: Configure Parameters
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

### Step 2: Generate Phase 1 Instructions
Run the following script to generate Phase 1 instructions:
```bash
python pipeline_instruction.py
```

This script will:
- Use the first account to generate instructions for `PERSONAS_PER_ACCOUNT` personas
- Generate `PHASE1_NUM_INSTRUCTIONS` per persona
- Save the output to: `results/instructions_phase1.json`

### Step 3: Generate Phase 1 Trajectories
Open `pipeline_trajectory_generation.py` and configure:
```python
PHASE = 1
MODE = 0  # 0: Automatic execution, 1: Interactive mode
```

Then run:
```bash
python pipeline_trajectory_generation.py
```

This will:
- Load `instructions_phase1.json`
- Automatically handle Google authentication by creating and maintaining persistent browser sessions in account-specific directories under `browser_sessions/`
- Once logged in, the session is saved and reused for future runs, eliminating the need for repeated logins
- Execute instructions using Playwright in parallel across multiple accounts
- Save browser trajectories, screenshots, and logs into uniquely named folders (UUID-based) inside `results/`

### Step 4: Generate Phase 2 Instructions
Update the phase in `pipeline_instruction.py`:
```python
PHASE = 2
```

Then run:
```bash
python pipeline_instruction.py
```

This will:
- Distribute personas among all configured accounts
- Each account processes its assigned `PERSONAS_PER_ACCOUNT` personas
- Generate `PHASE2_NUM_INSTRUCTIONS` per persona
- Save the output to: `results/instructions_phase2.json`

### Step 5: Generate Phase 2 Trajectories
Repeat the trajectory generation step for Phase 2:
- Update `PHASE = 2` in `pipeline_trajectory_generation.py`
- Run the script again:
```bash
python pipeline_trajectory_generation.py
```

This will:
- Read instructions from `instructions_phase2.json`
- Generate second-phase trajectories conditioned on modified web states

## Output Artifacts

Each instruction will generate:
- A `.json` file with logs and metadata
- Screenshots (initial + final state)
- A step-by-step interaction trace (clicks, types, scrolls, etc.)

## Summary

This pipeline allows you to:
- Create scalable, persona-grounded natural instructions
- Generate real executable trajectories through Playwright
- Process instructions in parallel across multiple Google accounts
- Iterate and augment your dataset with Phase 1 → Phase 2 logic


