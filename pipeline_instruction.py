import random
import os
from dotenv import load_dotenv
load_dotenv()

import json
from datasets import load_dataset
from tqdm import tqdm
from generate_instruction import generate_instructions
from prompt_augmentation import generate_augmented_instructions
import openai
from playwright.sync_api import sync_playwright
from google_auth import ensure_google_login
from concurrent.futures import ThreadPoolExecutor

# ========== CONFIGURABLE PARAMETERS ==========
from config import (
    PHASE1_NUM_INSTRUCTIONS,
    PHASE2_NUM_INSTRUCTIONS,
    RESULTS_DIR,
    URL,
    ACCOUNTS,
    PERSONAS_PER_ACCOUNT
)

chrome_executable_path = os.getenv("CHROME_EXECUTABLE_PATH")
PERSONAHUB_DATA_PATH = "persona.jsonl"  # Path to PersonaHub data file
SCREENSHOT_PATH = "screenshot.png"
PHASE = 2

# Directory to store all browser sessions
BROWSER_SESSIONS_DIR = "browser_sessions"
os.makedirs(BROWSER_SESSIONS_DIR, exist_ok=True)

def write_documentation(persona, url, instructions, augmented_instructions, results_dir=RESULTS_DIR, filename=f"instructions_phase{PHASE}.json"):
    import json

    # Ensure the results directory exists
    os.makedirs(results_dir, exist_ok=True)
    file_path = os.path.join(results_dir, filename)

    # Load existing data if file exists, else start with empty list
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    else:
        data = []

    # Append new entry
    data.append({
        "persona": persona,
        "url": url,
        "instructions": instructions,
        "augmented_instructions": augmented_instructions
    })

    # Write back to file
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_instructions_for_account(account, persona, num_instructions):
    """Generate instructions for a specific account and persona."""
    user_data_dir = os.path.join(BROWSER_SESSIONS_DIR, account["user_data_dir"])
    if not os.path.exists(user_data_dir):
        os.makedirs(user_data_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=chrome_executable_path,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = browser.new_page()
        page.goto(URL)
        
        # Ensure we're logged in before proceeding
        # ensure_google_login(page, account["email"], account["password"], URL)
            
        # Take screenshot
        screenshot_path = SCREENSHOT_PATH
        page.screenshot(path=screenshot_path)
        
        # Get accessibility tree for phase 2
        axtree = None
        if PHASE == 2:
            axtree = page.accessibility.snapshot()
            
        # Generate instructions and augment them
        instructions = generate_instructions(
            persona, PHASE, num_instructions=num_instructions, 
            screenshot_path=screenshot_path, axtree=axtree
        )

        print(f"Generated {len(instructions)} instructions for account {account['email']}")
            
        augmented_instructions = generate_augmented_instructions(
            instructions, screenshot_path=screenshot_path
        )

        browser.close()
        return instructions, augmented_instructions

def main():
    # Ensure results directory exists
    os.makedirs(RESULTS_DIR, exist_ok=True)

    dataset = load_dataset("proj-persona/PersonaHub", data_files=PERSONAHUB_DATA_PATH)['train']
    shuffled = dataset.shuffle(seed=random.randint(0, 9999))  # Use a random seed each run
    
    # Calculate total personas needed
    total_personas = PERSONAS_PER_ACCOUNT * len(ACCOUNTS)
    personas = shuffled[:total_personas]['persona']
    num_instructions = PHASE2_NUM_INSTRUCTIONS if PHASE == 2 else PHASE1_NUM_INSTRUCTIONS

    print(f"Processing {total_personas} personas total ({PERSONAS_PER_ACCOUNT} per account)")

    if PHASE == 1:
        # Phase 1: Use first account only
        account = ACCOUNTS[0]
        for persona in tqdm(personas[:PERSONAS_PER_ACCOUNT], desc="Processing personas"):
            instructions, augmented_instructions = generate_instructions_for_account(
                account, persona, num_instructions
            )
            write_documentation(persona, URL, instructions, augmented_instructions)
    else:
        # Phase 2: Each account processes its assigned personas
        for i, account in enumerate(ACCOUNTS):
            start_idx = i * PERSONAS_PER_ACCOUNT
            end_idx = start_idx + PERSONAS_PER_ACCOUNT
            
            print(f"\nAccount {account['email']} processing personas {start_idx} to {end_idx-1}")
            
            # Process this account's assigned personas
            for persona in tqdm(personas[start_idx:end_idx], desc=f"Processing with account {i+1}"):
                try:
                    instructions, augmented = generate_instructions_for_account(
                        account, persona, num_instructions
                    )
                    print(f"Generated {len(instructions)} instructions for persona: {persona}")
                    write_documentation(persona, URL, instructions, augmented)
                except Exception as e:
                    print(f"Error processing persona {persona} with account {account['email']}: {e}")
                    # Write error state to maintain documentation
                    write_documentation(persona, URL, 
                                     [f"ERROR: {e}"] * num_instructions,
                                     [f"ERROR: {e}"] * num_instructions)

if __name__ == "__main__":
    main()