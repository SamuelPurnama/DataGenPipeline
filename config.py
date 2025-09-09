# ========== GENERAL CONFIGURATION ==========
RESULTS_DIR = "data/results"
BROWSER_SESSIONS_DIR = "data/browser_sessions"
SAMPLE_DATA_DIR = "data/sample_data"
URL = "https://flights.google.com"


# ========== INSTRUCTION GENERATION PARAMETERS ==========
TOTAL_PERSONAS = 5  # Total number of personas to process
PHASE1_INSTRUCTIONS_PER_PERSONA = 5  # Instructions per persona for phase 1 (initial state)
PHASE2_INSTRUCTIONS_PER_PERSONA = 20 # Instructions per persona for phase 2 (modified state)
PERSONAHUB_DATA_PATH = "persona.jsonl"  # Path to PersonaHub data file
SCREENSHOT_PATH = "screenshot.png"      # Path for screenshots


# ========== TRAJECTORY GENERATION PARAMETERS ==========
PHASE = 1                              # Current phase (1 or 2)
MAX_RETRIES = 2                        # Maximum retries for failed actions
MAX_STEPS = 40                         # Maximum number of steps before failing
ACTION_TIMEOUT = 10000                 # 10 seconds timeout for actions
# Execution Modes:
# 0 - Automatic Mode: Processes all instructions without manual intervention
# 1 - Interactive Mode: Requires Enter press after each instruction for manual review
MODE = 0
SEARCH_CONTEXT = False                 # Whether to search for relevant past trajectories for context

# Trajectory Processing Configuration:
# AUTO_TRAJECTORY_PROCESSING: Set to True to automatically process all instructions, False for manual control
AUTO_TRAJECTORY_PROCESSING = True      # Set to True to process all instructions, False for manual control
MAX_INSTRUCTIONS_TO_PROCESS = 10       # Maximum number of instructions to process (only used when AUTO_TRAJECTORY_PROCESSING = False)

# Account Indexing Configuration:
# AUTO_INDEXING: Set to True to automatically calculate start_idx/end_idx for accounts
# - When True: Uses first NUM_ACCOUNTS_TO_USE accounts and calculates indexes automatically
# - When False: Uses manual start_idx/end_idx values specified in ACCOUNTS list
AUTO_INDEXING = True                   # Set to True for automatic index calculation, False for manual
NUM_ACCOUNTS_TO_USE = 4                # Number of accounts to use (only used when AUTO_INDEXING = True)

# How auto-indexing works:
# - Total instructions = TOTAL_PERSONAS × (PHASE1_INSTRUCTIONS_PER_PERSONA or PHASE2_INSTRUCTIONS_PER_PERSONA)
# - If AUTO_TRAJECTORY_PROCESSING = False: limit to MAX_INSTRUCTIONS_TO_PROCESS
# - Distribute evenly: base_instructions = total ÷ NUM_ACCOUNTS_TO_USE
# - Extra instructions = total % NUM_ACCOUNTS_TO_USE (first few accounts get +1)
# - Example: 25 instructions ÷ 3 accounts = 8,8,9 (first account gets extra)





# ========== KNOWLEDGE BASE CONFIGURATION ==========
MAX_CONTEXT_LENGTH = 3000              # Maximum context length in characters
KNOWLEDGE_BASE_TYPE = "graphrag"       # Type of knowledge base to use





# ========== END-TO-END PIPELINE CONTROL SETTINGS ==========
# Set to True/False to enable/disable each pipeline step
ENABLE_INSTRUCTION_GENERATION = False   # Step 1: Generate instructions from personas
ENABLE_TRAJECTORY_GENERATION = True    # Step 2: Generate trajectories using AI automation
ENABLE_TASK_VERIFICATION = True        # Step 3: Verify and organize completed tasks

# Additional settings
SKIP_CONFIRMATION = False              # Set to True to skip user confirmation prompts
VERBOSE_OUTPUT = False                 # Set to True for detailed error output





# ========== GOOGLE ACCOUNTS CONFIGURATION ==========
ACCOUNTS = [
    {
        "email": "kukukud4@gmail.com",
        "password": "samJP535",
        "user_data_dir": "sam2",
        "start_idx": 0,
        "end_idx": 1
    },
    {
        "email": "testeracc482@gmail.com",
        "password": "Lalala123",
        "user_data_dir": "test1",
        "start_idx": 1,
        "end_idx": 2
    },
    {
        "email": "testeracc649@gmail.com",
        "password": "Lalala123",
        "user_data_dir": "test2",
        "start_idx": 10,
        "end_idx": 20
    },
    {
        "email": "samuelperry9973@gmail.com",
        "password": "Lalala123",
        "user_data_dir": "test3",
        "start_idx": 20,
        "end_idx": 30
    },
    {
        "email": "diamondjove@gmail.com",
        "password": "Lalala123",
        "user_data_dir": "test4",
        "start_idx": 30,
        "end_idx": 40
    },
    {
        "email": "daikintanuw@gmail.com",
        "password": "Lalala123",
        "user_data_dir": "test5",
        "start_idx": 40,
        "end_idx": 50
    },
    {
        "email": "daikintanuwijaya@gmail.com",
        "password": "Lalala123",
        "user_data_dir": "test6",
        "start_idx": 50,
        "end_idx": 60
    },
    {
        "email": "dalecormick1@gmail.com",
        "password": "Lalala123",
        "user_data_dir": "test7",
        "start_idx": 60,
        "end_idx": 70
    },
    {
        "email": "suprismth@gmail.com",
        "password": "Lalala123",
        "user_data_dir": "test8",
        "start_idx": 70,
        "end_idx": 80
    },
    {
        "email": "kintilbirdie@gmail.com",
        "password": "Lalala123",
        "user_data_dir": "test9",
        "start_idx": 80,
        "end_idx": 90
    },
    {
        "email": "asephartenstein@gmail.com",
        "password": "Lalala123",
        "user_data_dir": "test10",
        "start_idx": 90,
        "end_idx": 100
    }
]

# ========== AUTO-INDEXING LOGIC ==========
def calculate_auto_indexes():
    """
    Automatically calculate start_idx and end_idx for accounts based on:
    - NUM_ACCOUNTS_TO_USE: Number of accounts to use
    - PERSONAS_PER_ACCOUNT: Personas per account
    - PHASE1_NUM_INSTRUCTIONS or PHASE2_NUM_INSTRUCTIONS: Instructions per persona
    """
    if not AUTO_INDEXING:
        return ACCOUNTS
    
    # Calculate total instructions and distribute across accounts
    instructions_per_persona = PHASE2_INSTRUCTIONS_PER_PERSONA if PHASE == 2 else PHASE1_INSTRUCTIONS_PER_PERSONA
    total_instructions = TOTAL_PERSONAS * instructions_per_persona
    
    # Limit instructions if AUTO_TRAJECTORY_PROCESSING is False
    if not AUTO_TRAJECTORY_PROCESSING:
        total_instructions = min(total_instructions, MAX_INSTRUCTIONS_TO_PROCESS)
    
    # Distribute instructions evenly across accounts (some may get one extra)
    base_instructions_per_account = total_instructions // NUM_ACCOUNTS_TO_USE
    extra_instructions = total_instructions % NUM_ACCOUNTS_TO_USE
    
    # Create auto-indexed accounts
    auto_accounts = []
    current_idx = 0
    for i in range(NUM_ACCOUNTS_TO_USE):
        if i < len(ACCOUNTS):
            account = ACCOUNTS[i].copy()  # Copy to avoid modifying original
            
            # Calculate instructions for this account
            instructions_for_this_account = base_instructions_per_account
            if i < extra_instructions:  # First few accounts get one extra instruction
                instructions_for_this_account += 1
            
            account["start_idx"] = current_idx
            account["end_idx"] = current_idx + instructions_for_this_account
            current_idx += instructions_for_this_account
            
            auto_accounts.append(account)
    
    return auto_accounts

# Apply auto-indexing if enabled
if AUTO_INDEXING:
    ACCOUNTS = calculate_auto_indexes()