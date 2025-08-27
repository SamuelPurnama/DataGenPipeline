PERSONAS_PER_ACCOUNT = 1  # Number of personas each account will process
PHASE1_NUM_INSTRUCTIONS = 10  # Instructions per persona for phase 1 (initial state)
PHASE2_NUM_INSTRUCTIONS = 20 # Instructions per persona for phase 2 (modified state)

# Centralized path configuration
RESULTS_DIR = "/Users/jovewinston/Documents/DataGenPipeline Complete/DataGenPipeline/data/results"
BROWSER_SESSIONS_DIR = "data/browser_sessions"
SAMPLE_DATA_DIR = "data/sample_data"

URL = "https://flights.google.com"
# Google Accounts Configuration
ACCOUNTS = [
    {
        "email": "testeracc482@gmail.com",
        "password": "Lalala123",
        "user_data_dir": "test1",
        "start_idx": 0,
        "end_idx": 1
    }
    # {
    #     "email": "testeracc649@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test2",
    #     "start_idx": 8,
    #     "end_idx": 16
    # },
    # {
    #     "email": "samuelperry9973@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test3",
    #     "start_idx": 16,
    #     "end_idx": 24
    # },
    # {
    #     "email": "diamondjove@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test4",
    #     "start_idx": 24,
    #     "end_idx": 32
    # },
    # {
    #     "email": "daikintanuw@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test5",
    #     "start_idx": 32,
    #     "end_idx": 40
    # },
    # {
    #     "email": "daikintanuwijaya@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test6",
    #     "start_idx": 40,
    #     "end_idx": 48
    # },
    # {
    #     "email": "dalecormick1@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test7",
    #     "start_idx": 48,
    #     "end_idx": 56
    # },
    # {
    #     "email": "suprismth@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test8",
    #     "start_idx": 56,
    #     "end_idx": 64
    # },
    # {
    #     "email": "kintilbirdie@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test9",
    #     "start_idx": 64,
    #     "end_idx": 72
    # },
    # {
    #     "email": "asephartenstein@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test10",
    #     "start_idx": 72,
    #     "end_idx": 80
    # }
]