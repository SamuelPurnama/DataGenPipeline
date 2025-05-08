import random
import os
from dotenv import load_dotenv
load_dotenv()

import json
from datasets import load_dataset
from tqdm import tqdm
from generate_instruction import generate_instructions
from trajectory_generator import generate_trajectory
from prompt_augmentation import generate_augmented_instructions
import openai
from playwright.sync_api import sync_playwright

# ========== CONFIGURABLE PARAMETERS ==========
NUM_PERSONAS = 1  # Number of personas to process
PHASE1_NUM_INSTRUCTIONS = 2  # Instructions per persona for phase 1 (initial state)
PHASE2_NUM_INSTRUCTIONS = 3  # Instructions per persona for phase 2 (modified state)
PERSONAHUB_DATA_PATH = "persona.jsonl"  # Path to PersonaHub data file
RESULTS_DIR = "results"
OUTPUT_PATH = os.path.join(RESULTS_DIR, "generated_instructions.jsonl")  # Output file path
SCREENSHOT_PATH = "screenshot_calendar.png"
URL = "https://calendar.google.com/"

chrome_profile_path = os.getenv("CHROME_PROFILE_PATH")
chrome_executable_path = os.getenv("CHROME_EXECUTABLE_PATH")

def main():
    # Ensure results directory exists
    os.makedirs(RESULTS_DIR, exist_ok=True)

    dataset = load_dataset("proj-persona/PersonaHub", data_files=PERSONAHUB_DATA_PATH)['train']
    shuffled = dataset.shuffle(seed=random.randint(0, 9999))  # Use a random seed each run
    personas = shuffled[:NUM_PERSONAS]['persona']
    print(personas)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as out_file:
        for persona in tqdm(personas, desc="Processing personas"):
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=chrome_profile_path,
                    executable_path=chrome_executable_path,
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                page = browser.new_page()
                page.goto(URL)

                
                # Take screenshot
                screenshot_path = "screenshot.png"
                page.screenshot(path=screenshot_path)
                
                # Generate instructions and augment them
                phase1_instructions = generate_instructions(
                    persona, phase=1, num_instructions=PHASE1_NUM_INSTRUCTIONS, screenshot_path=screenshot_path
                )
                phase1_augmented_instructions = generate_augmented_instructions(
                    phase1_instructions, screenshot_path=screenshot_path
                )
                
                # Loop through each instruction and perform trajectory
                for instruction in phase1_augmented_instructions:
                    generate_trajectory(instruction, page)
                
                # phase2_instructions = generate_instructions(
                #     persona, phase=2, num_instructions=PHASE2_NUM_INSTRUCTIONS, screenshot_path=SCREENSHOT_PATH
                # )

                # phase2_augmented_instructions = generate_augmented_instructions(
                #     persona, phase2_instructions, screenshot_path=SCREENSHOT_PATH
                # )

                # generate_trajectory(persona, phase2_augmented_instructions, screenshot_path=SCREENSHOT_PATH)
                
                browser.close()

    print(f"Instructions generated and saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
