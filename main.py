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

# ========== CONFIGURABLE PARAMETERS ==========
NUM_PERSONAS = 1  # Number of personas to process
PHASE1_NUM_INSTRUCTIONS = 3  # Instructions per persona for phase 1 (initial state)
PHASE2_NUM_INSTRUCTIONS = 3  # Instructions per persona for phase 2 (modified state)
PERSONAHUB_DATA_PATH = "persona.jsonl"  # Path to PersonaHub data file
RESULTS_DIR = "results"
OUTPUT_PATH = os.path.join(RESULTS_DIR, "generated_instructions.jsonl")  # Output file path
SCREENSHOT_PATH = "screenshot_calendar.png"
URL = "https://calendar.google.com/"

def main():
    # Ensure results directory exists
    os.makedirs(RESULTS_DIR, exist_ok=True)

    dataset = load_dataset("proj-persona/PersonaHub", data_files=PERSONAHUB_DATA_PATH)['train']
    shuffled = dataset.shuffle(seed=random.randint(0, 9999))  # Use a random seed each run
    personas = shuffled[:NUM_PERSONAS]['persona']
    print(personas)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as out_file:
        for persona in tqdm(personas, desc="Processing personas"):
            phase1_instructions = generate_instructions(
                persona, phase=1, num_instructions=PHASE1_NUM_INSTRUCTIONS, screenshot_path=SCREENSHOT_PATH
            )
            
            print(phase1_instructions)

            phase1_augmented_instructions = generate_augmented_instructions(
                phase1_instructions, screenshot_path=SCREENSHOT_PATH
            )

            print(phase1_augmented_instructions)

            # for instruction in phase1_instructions:
            #     generate_trajectory(instruction, url=URL)

            # phase2_instructions = generate_instructions(
            #     persona, phase=2, num_instructions=PHASE2_NUM_INSTRUCTIONS, screenshot_path=SCREENSHOT_PATH
            # )

            # phase2_augmented_instructions = generate_augmented_instructions(
            #     persona, phase2_instructions, screenshot_path=SCREENSHOT_PATH
            # )

            # generate_trajectory(persona, phase2_augmented_instructions, screenshot_path=SCREENSHOT_PATH)

    print(f"Instructions generated and saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
