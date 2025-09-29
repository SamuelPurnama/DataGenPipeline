import json
import base64
from typing import Dict, List, Optional
from openai import OpenAI
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def chat_ai_playwright_code_ocr(
    previous_steps: List[Dict],
    taskGoal: str,
    taskPlan: str,
    image_path: str,
    elements_data: Dict,
    failed_codes: List[str] = None,
    is_deletion_task: bool = False,
    url: str = "",
    error_log: str = "",
    trajectory_context: str = "",
    session_dir: str = None
) -> Optional[Dict]:
    """
    Generate Playwright code using OCR-based element detection.
    
    Args:
        previous_steps: List of previous execution steps
        taskGoal: The main task goal
        taskPlan: Current task plan/goal
        image_path: Path to the screenshot
        elements_data: Elements data containing text elements with bounding boxes
        failed_codes: List of previously failed code attempts
        is_deletion_task: Whether this is a deletion task
        url: Current page URL
        error_log: Error log from previous attempts
        trajectory_context: Context from past trajectories
    
    Returns:
        Dictionary containing the GPT response with code, description, etc.
    """
    
    if failed_codes is None:
        failed_codes = []
    
    # Encode image to base64
    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"❌ Error encoding image: {e}")
        return None
    
    # Prepare elements for the prompt
    elements_text = ""
    if elements_data and 'elements' in elements_data:
        elements_text = "\n\nAvailable Text Elements (OCR):\n"
        for element in elements_data['elements']:
            annotation_id = element.get('annotation_id', '?')
            text = element.get('text', 'unnamed')
            
            elements_text += f"  {annotation_id}. {text}\n"
        elements_text += "\n"
    
    # Prepare previous steps context
    previous_steps_text = ""
    if previous_steps:
        previous_steps_text = "\n\nPrevious Steps:\n"
        for i, step in enumerate(previous_steps[-5:], 1):  # Last 5 steps
            previous_steps_text += f"{i}. {step.get('step', 'Unknown step')}\n"
        previous_steps_text += "\n"
    
    # Prepare failed codes context
    failed_codes_text = ""
    if failed_codes:
        failed_codes_text = "\n\nFailed Code Attempts (DO NOT repeat these):\n"
        for i, code in enumerate(failed_codes, 1):
            failed_codes_text += f"{i}. {code}\n"
        failed_codes_text += "\n"
    
    # Prepare error log context
    error_log_text = ""
    if error_log:
        error_log_text = f"\n\nError from last attempt: {error_log}\n"
    
    # Prepare trajectory context
    trajectory_text = ""
    if trajectory_context:
        trajectory_text = f"\n\nRelevant Past Trajectories:\n{trajectory_context}\n"
    
    # Construct the system prompt
    system_prompt = """You are an assistant that analyzes a web page's interactable elements and the screenshot of the current page to help complete a user's task on a flight-booking website (e.g., Google Flights).
Instructions:
1. Check if the task goal has already been completed (i.e., not just filled out, but fully finalized by CLICKING SAVE/SUBMIT. DON'T SAY TASK IS COMPLETED UNTIL THE SAVE BUTTON IS CLICKED). If so, return a task summary.
2. If not, predict the next step the user should take to make progress.
3. Identify the correct UI element based on the elements data and a screenshot of the current page to perform the next predicted step to get closer to the end goal.
4. You will receive both a taskGoal (overall goal) and a taskPlan (current specific goal). Use the taskPlan to determine the immediate next action, while keeping the taskGoal in mind for context.
5. If and only if the current taskPlan is missing any required detail (for example, if the plan is 'schedule a meeting' but no time, end time, or event name is specified), you must clarify or update the plan by inventing plausible details or making reasonable assumptions. As you analyze the current state of the page, you are encouraged to edit and clarify the plan to make it more specific and actionable. For example, if the plan is 'schedule a meeting', you might update it to 'schedule a meeting called "Team Sync" from 2:00 PM to 3:00 PM'.
6. You must always return an 'updated_goal' field in your JSON response. If you do not need to change the plan, set 'updated_goal' to the current plan you were given. If you need to clarify or add details, set 'updated_goal' to the new, clarified plan.
7. Return a JSON object.

⚠️ *ACTION TYPE REQUIREMENT*: You MUST specify the action type in your response. The action type should be one of:
- "click" - for clicking buttons, links, or other clickable elements (requires id)
- "fill" - for entering text into input fields, textboxes, or forms (NO id needed)
- "wait" - for waiting for page loading, animations, or dynamic content to appear (NO id needed)

⚠️ *TEXT TO FILL REQUIREMENT*: If the action_type is "fill", you MUST include a "text_to_fill" field with the actual text to enter.

⚠️ *ANNOTATION ID REQUIREMENT*: You MUST always include "selected_annotation_id" with the annotation ID of the element you want to interact with. For "click" actions, this is the element to click. For "fill" actions, this is the input field to fill (the system will handle clicking it first). For "wait" actions, you can set this to null or omit it since no specific element interaction is needed.

⚠️ *SEPARATE ACTIONS*: When you need to fill an input field, you should return a "click" action first to select the field, then in the next GPT call, return a "fill" action to type the text. Do NOT combine click and fill into a single action.

⚠️ *CONFIDENCE REQUIREMENT*: You MUST include a "confidence" field with a score from 0.0 to 1.0 indicating how confident you are in this action choice and code (0.0 = very uncertain, 1.0 = completely certain).

You will receive:
- Task goal – the user's intended outcome (e.g., "find a one-way flight to New York")
- Previous steps – a list of actions the user has already taken. It's okay if the previous steps array is empty.
- Interactive Elements (interactable elements with annotation ids) – a list of role-name objects describing all visible and interactive elements on the page
- Sreenshot of the current page

IMPORTANT: 
- IF U SEE THE IMAGE OR ELEMENTS THAT IS NOT A GOOGLE FLIGHTS PAGE, EXAMPLE: IS AN ALASKA AIRLINES PAGE, DELTA AIRLINES PAGE, FRONTIER AIRLINES PAGE, OR ANY OTHER AIRLINES, YOU SHOULD RETURN A TASK SUMMARY. BASICALLY IF IT'S NOT A GOOGLE FLIGHT WEBSITE, YOU SHOULD RETURN A TASK SUMMARY.
- You should look at the screenshot thoroughly and make sure you pick the element from the interactive elements list (by its annotation id) that are visible on the screenshot of the page.
- When filling in combobox, or any other input field, you should first return a "click" action to select the field, then in the next step return a "fill" action to type the text.
- After choosing an element with an annotation id in the elements list, make sure to look at the screenshot again and make sure to see if the element is visible on the screenshot. If not, choose another element.
- For input fields, first click the field (action_type: "click"), then in the next GPT call, fill it (action_type: "fill").


IMPORTANT: When selecting annotation ids, make sure to look at the screenshot first to locate that elemenet with the annotation id, and make sure it's a visible element on the screenshot, if not, choose another annotation id.

Examples of clarifying vague goals:
- Goal: "Search for flights to Paris"
  → updated_goal: "Search for one-way economy flights from Seattle to Paris on June 10th"
- Goal: "Get the cheapest flight to LA"
  → updated_goal: "Search for round-trip economy flights from Seattle to Los Angeles on July 5th and return on July 12th, sorted by price"

Your response must be a JSON object with this structure:
```json
{
    "description": "A clear, natural language description of what the code will do, try including the element that should be interacted with and the action to be taken",
    "updated_goal": "The new, clarified plan if you changed it, or the current plan if unchanged",
    "thought": "Your reasoning for choosing this action",
    "selected_annotation_id": "The annotation id of the interactable element you're targeting",
    "action_type": "The type of action being performed (click, fill, select, navigate, or wait)",
    "text_to_fill": "The text to fill (ONLY include this field if action_type is 'fill')",
    "confidence": "A confidence score from 0.0 to 1.0 indicating how confident you are in this action choice and code (0.0 = very uncertain, 1.0 = completely certain)"
}
```
For example:
```json
{
    "description": "Click the Create button to start creating a new event",
    "updated_goal": "Create a new event titled 'Mystery Event' at May 20th from 10 AM to 11 AM",
    "thought": "I need to click the Create button to start creating a new event",
    "selected_annotation_id": "1",
    "action_type": "click",
    "confidence": 0.9
}
```
or
```json
{
    "description": "Click on the departure airport field to select it",
    "updated_goal": "Search for flights from Seattle to New York",
    "thought": "I need to click the departure airport field first to select it",
    "selected_annotation_id": "15",
    "action_type": "click",
    "confidence": 0.85
}
```
or for the second step (after clicking the field):
```json
{
    "description": "Fill in the departure airport field with 'Seattle'",
    "updated_goal": "Search for flights from Seattle to New York",
    "thought": "Now I need to fill the selected field with Seattle",
    "selected_annotation_id": "15",
    "action_type": "fill",
    "text_to_fill": "Seattle",
    "confidence": 0.85
}
```
or for waiting:
```json
{
    "description": "Wait for the page to load completely",
    "updated_goal": "Search for flights from Seattle to New York",
    "thought": "The page is still loading, I need to wait for it to finish",
    "selected_annotation_id": null,
    "action_type": "wait",
    "confidence": 0.9
}
```
If the task is completed, return a JSON with a instruction summary:
```json
{
    "summary_instruction": "An instruction that describes the overall task that was accomplished based on the actions taken so far. It should be phrased as a single, clear instruction you would give to a web assistant to replicate the completed task. For example: 'Find one-way flights from Seattle to New York on May 10th'.",
    "output": "A short factual answer or result if the task involved identifying specific information (e.g., 'Found a round-trip flight ticket from Seattle to New York on June 10th until June 17th, starting at $242 with United Airlines')",
    "confidence": 0.95
}
```"""
    
    # Construct the user prompt
    user_prompt = f"""Task Goal: {taskGoal}
Current Task Plan: {taskPlan}
Current URL: {url}
{elements_text}{previous_steps_text}{failed_codes_text}{error_log_text}{trajectory_text}

Please analyze the screenshot and available elements to determine the next action."""
    
    # Save what gets sent to GPT if session_dir is provided
    if session_dir:
        try:
            gpt_prompt_dir = os.path.join(session_dir, 'gpt_prompts')
            os.makedirs(gpt_prompt_dir, exist_ok=True)
            
            # Create a timestamp for this GPT call
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Include milliseconds
            
            # Save system prompt
            system_prompt_file = os.path.join(gpt_prompt_dir, f'system_prompt_{timestamp}.txt')
            with open(system_prompt_file, 'w', encoding='utf-8') as f:
                f.write(system_prompt)
            
            # Save user prompt
            user_prompt_file = os.path.join(gpt_prompt_dir, f'user_prompt_{timestamp}.txt')
            with open(user_prompt_file, 'w', encoding='utf-8') as f:
                f.write(user_prompt)
            
            # Save elements data
            elements_file = os.path.join(gpt_prompt_dir, f'elements_data_{timestamp}.json')
            with open(elements_file, 'w', encoding='utf-8') as f:
                json.dump(elements_data, f, indent=2, ensure_ascii=False)
            
            # Save complete prompt data
            complete_prompt_data = {
                "timestamp": timestamp,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "elements_data": elements_data,
                "image_path": image_path,
                "task_goal": taskGoal,
                "task_plan": taskPlan,
                "url": url
            }
            
            complete_prompt_file = os.path.join(gpt_prompt_dir, f'complete_prompt_{timestamp}.json')
            with open(complete_prompt_file, 'w', encoding='utf-8') as f:
                json.dump(complete_prompt_data, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Saved GPT prompt data to: {gpt_prompt_dir}")
            
        except Exception as e:
            print(f"⚠️ Error saving GPT prompt data: {e}")
    
    try:
        # Make the API call
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        # Parse the response
        content = response.choices[0].message.content.strip()
        
        # Try to parse as JSON
        try:
            result = json.loads(content)
            
            # Add token usage info
            if hasattr(response, 'usage'):
                result['total_tokens'] = response.usage.total_tokens
            
            return result
            
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract JSON from markdown
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                if json_end != -1:
                    json_content = content[json_start:json_end].strip()
                    try:
                        result = json.loads(json_content)
                        if hasattr(response, 'usage'):
                            result['total_tokens'] = response.usage.total_tokens
                        return result
                    except json.JSONDecodeError:
                        pass
            
            print(f"❌ Failed to parse GPT response as JSON: {content}")
            return None
            
    except Exception as e:
        print(f"❌ Error calling GPT API: {e}")
        return None
