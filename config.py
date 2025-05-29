PERSONAS_PER_ACCOUNT = 2  # Number of personas each account will process
PHASE1_NUM_INSTRUCTIONS = 5  # Instructions per persona for phase 1 (initial state)
PHASE2_NUM_INSTRUCTIONS = 5 # Instructions per persona for phase 2 (modified state)
RESULTS_DIR = "results"
URL = "https://calendar.google.com"

# Google Accounts Configuration
ACCOUNTS = [
    {
        "email": "kukukud4@gmail.com",
        "password": "samJP535",
        "user_data_dir": "sam1",
        "start_idx": 0,
        "end_idx": 5
    },
    {
        "email": "samueljovarenp@gmail.com",
        "password": "samJP535",
        "user_data_dir": "sam2",
        "start_idx": 5,
        "end_idx": 10
    },
]