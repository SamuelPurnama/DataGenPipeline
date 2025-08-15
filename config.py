PERSONAS_PER_ACCOUNT = 1  # Number of personas each account will process
PHASE1_NUM_INSTRUCTIONS = 5  # Instructions per persona for phase 1 (initial state)
PHASE2_NUM_INSTRUCTIONS = 20 # Instructions per persona for phase 2 (modified state)

# Centralized path configuration
RESULTS_DIR = "../data/results"
BROWSER_SESSIONS_DIR = "data/browser_sessions"
SAMPLE_DATA_DIR = "data/sample_data"

URL = "https://flights.google.com"

# Google Accounts Configuration
ACCOUNTS = [
    {
        "email": "samuelperry9973@gmail.com",
        "password": "Lalala123",
        "user_data_dir": "samuelPerry",
        "start_idx": 0,
        "end_idx": 1,
    }
    # {
    #     "email": "testeracc482@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test1",
    #     "start_idx": 0,
    #     "end_idx": 30
    # },
    # {
    #     "email": "testeracc649@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test2",
    #     "start_idx": 30,
    #     "end_idx": 60
    # },
    # {
    #     "email": "samuelperry9973@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test3",
    #     "start_idx": 60,
    #     "end_idx": 90
    # },
    # {
    #     "email": "diamondjove@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test4",
    #     "start_idx": 90,
    #     "end_idx": 120
    # },
    # {
    #     "email": "daikintanuw@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test5",
    #     "start_idx": 120,
    #     "end_idx": 150
    # },
    # {
    #     "email": "daikintanuwijaya@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test6",
    #     "start_idx": 150,
    #     "end_idx": 180
    # },
    # {
    #     "email": "dalecormick1@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test7",
    #     "start_idx": 180,
    #     "end_idx": 210
    # },
    # {
    #     "email": "suprismth@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test8",
    #     "start_idx": 210,
    #     "end_idx": 240
    # },
    # {
    #     "email": "kintilbirdie@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test9",
    #     "start_idx": 240,
    #     "end_idx": 270
    # },
    # {
    #     "email": "asephartenstein@gmail.com",
    #     "password": "Lalala123",
    #     "user_data_dir": "test10",
    #     "start_idx": 270,
    #     "end_idx": 300
    # }
]