PERSONAS_PER_ACCOUNT = 2  # Number of personas each account will process
PHASE1_NUM_INSTRUCTIONS = 5  # Instructions per persona for phase 1 (initial state)
PHASE2_NUM_INSTRUCTIONS = 5 # Instructions per persona for phase 2 (modified state)
RESULTS_DIR = "results"
URL = "https://calendar.google.com"

# Google Accounts Configuration
ACCOUNTS = [
    {
        "email": "example1@gmail.com",
        "password": "password1",
        "user_data_dir": "example1",
        "start_idx": 0,
        "end_idx": 5
    },
    {
        "email": "example2@gmail.com",
        "password": "password2",
        "user_data_dir": "example2",
        "start_idx": 5,
        "end_idx": 10
    }, 
    #Add more accounts as needed
]
