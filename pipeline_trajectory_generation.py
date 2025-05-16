from playwright.sync_api import sync_playwright
import json
import os
import uuid
import shutil

from generate_trajectory import chat_ai_playwright_code
from config import RESULTS_DIR

# ========== CONFIGURABLE PARAMETERS ==========
PHASE = 1
START_IDX = 224
END_IDX = 225
MAX_RETRIES = 9
ACTION_TIMEOUT = 30000  # 30 seconds timeout for actions
# Execution Modes:
# 0 - Automatic Mode: Processes all instructions without manual intervention
# 1 - Interactive Mode: Requires Enter press after each instruction for manual review
MODE = 0

def generate_trajectory_loop(user_data_dir, chrome_path, phase, start_idx, end_idx):
    phase_file = os.path.join(RESULTS_DIR, f"instructions_phase{phase}.json")
    try:
        with open(phase_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Error loading {phase_file}: {e}")
        return

    all_instructions = []
    for persona_data in data:
        persona = persona_data['persona']
        url = persona_data['url']
        original_instructions = persona_data['instructions']
        augmented = persona_data['augmented_instructions']
        for orig, aug in zip(original_instructions, augmented):
            all_instructions.append({
                'persona': persona,
                'url': url,
                'original_instruction': orig,
                'augmented_instruction': aug
            })

    total = len(all_instructions)
    if start_idx >= total or end_idx <= start_idx or end_idx > total:
        print(f"❌ Invalid range: total={total}, requested={start_idx}-{end_idx}")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=chrome_path,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        try:
            for idx, item in enumerate(all_instructions[start_idx:end_idx], start=start_idx):
                persona = item['persona']
                url = item['url']
                orig = item['original_instruction']
                aug = item['augmented_instruction']
                run_uuid = str(uuid.uuid4())
                inst_dir = os.path.join(RESULTS_DIR, run_uuid)
                os.makedirs(inst_dir, exist_ok=True)

                print(f"\n🔄 Instruction {idx + 1}/{total}")
                print(f"👤 {persona}")
                print(f"🌐 {url}")
                print(f"📝 Orig: {orig}")
                print(f"🔄 Aug: {aug}")
                print(f"UUID: {run_uuid}")

                page = browser.new_page()
                page.set_default_timeout(ACTION_TIMEOUT)
                page.goto(url)
                page.wait_for_selector('[aria-label*="Google Account"]', timeout=300000)

                execution_history = []
                task_summarizer = []
                current_goal = aug
                should_continue = True

                while should_continue:
                    step_idx = len(task_summarizer)
                    screenshot = os.path.join(inst_dir, f"step_{step_idx}.png")
                    page.screenshot(path=screenshot)
                    tree = page.accessibility.snapshot()
                    is_del = 'delete' in current_goal.lower()

                    gpt_resp = chat_ai_playwright_code(
                        accessibility_tree=tree,
                        previous_steps=execution_history,
                        taskGoal=aug,
                        taskPlan=current_goal,
                        image_path=screenshot,
                        failed_codes=[],
                        is_deletion_task=is_del,
                        url=url
                    )

                    if "summary_instruction" in gpt_resp:
                        summary = {
                            "persona": persona,
                            "original_instruction": orig,
                            "augmented_instruction": aug,
                            "final_instruction": gpt_resp['summary_instruction'],
                            "url": url,
                            "task_steps": task_summarizer
                        }
                        with open(os.path.join(inst_dir, "task_summarizer.json"), "w", encoding="utf-8") as f:
                            json.dump(summary, f, indent=2, ensure_ascii=False)
                        print("✅ Task completed, summary saved.")
                        break

                    if "updated_goal" in gpt_resp:
                        current_goal = gpt_resp["updated_goal"]

                    failed_codes = []
                    retry = 0
                    description = gpt_resp["description"]
                    code = gpt_resp["code"]
                    success = False

                    while retry < MAX_RETRIES and not success:
                        try:
                            print(f"🤖 {description}")
                            exec(code)
                            execution_history.append({'step': description, 'code': code})
                            task_summarizer.append({'step': description, 'code': code, 'axtree': tree})
                            success = True
                        except Exception as e:
                            retry += 1
                            if code not in failed_codes:
                                failed_codes.append(code)
                            print(f"⚠️ Attempt {retry} failed: {e}")
                            if retry < MAX_RETRIES:
                                print("🔄 Retrying GPT for new code...")
                                page.screenshot(path=screenshot)
                                tree = page.accessibility.snapshot()
                                gpt_resp = chat_ai_playwright_code(
                                    accessibility_tree=tree,
                                    previous_steps=execution_history,
                                    taskGoal=aug,
                                    taskPlan=current_goal,
                                    image_path=screenshot,
                                    failed_codes=failed_codes,
                                    is_deletion_task=is_del,
                                    url=url
                                )
                                if "summary_instruction" in gpt_resp:
                                    summary = {
                                        "persona": persona,
                                        "original_instruction": orig,
                                        "augmented_instruction": aug,
                                        "url": url,
                                        "final_instruction": gpt_resp['summary_instruction'],
                                        "task_steps": task_summarizer
                                    }
                                    with open(os.path.join(inst_dir, "task_summarizer.json"), "w", encoding="utf-8") as f:
                                        json.dump(summary, f, indent=2, ensure_ascii=False)
                                    print("✅ Task completed on retry, summary saved.")
                                    should_continue = False
                                    break
                                description = gpt_resp["description"]
                                code = gpt_resp["code"]
                            else:
                                print(f"❌ All {MAX_RETRIES} retries failed; skipping instruction.")
                                shutil.rmtree(inst_dir, ignore_errors=True)
                                should_continue = False
                                break

                    if success:
                        page.wait_for_timeout(2000)
                    else:
                        break

                page.close()
                if MODE == 1:
                    input("🔚 Press Enter to continue...")
        finally:
            input("🔚 Press Enter to close browser...")
            browser.close()

def main():
    chrome_profile = os.getenv("CHROME_PROFILE_PATH")
    chrome_exec = os.getenv("CHROME_EXECUTABLE_PATH")
    generate_trajectory_loop(chrome_profile, chrome_exec, PHASE, START_IDX, END_IDX)

if __name__ == "__main__":
    main()