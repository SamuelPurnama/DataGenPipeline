"""
Post-action validation utilities for trajectory generation.
Provides functions to validate the results of executed actions by comparing before/after page states.
"""

import json
import os
from typing import Dict, Any, Optional
import base64
import requests

# Add parent directory to path for imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_post_action_validation_call(
    before_screenshot_path: str,
    after_screenshot_path: str,
    action_description: str
) -> Dict[str, Any]:
    """
    Make a GPT call to validate the results of an executed action by comparing before/after screenshots.
    
    Args:
        before_screenshot_path: Path to the screenshot taken before the action
        after_screenshot_path: Path to the screenshot taken after the action
        action_description: Description of the action that was executed
    
    Returns:
        Dictionary containing validation results
    """
    
    # Encode both images to base64
    try:
        with open(before_screenshot_path, "rb") as image_file:
            before_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        
        with open(after_screenshot_path, "rb") as image_file:
            after_base64 = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"❌ Error encoding images: {e}")
        return {
            "action_successful": False,
            "page_state_changed": False,
            "overall_confidence": 0.0,
            "reasoning": f"Image encoding error: {str(e)}",
            "suggestions": "Check image files"
        }
    
    # Create the validation prompt
    validation_prompt = f"""You are a post-action validation assistant that reviews the results of executed web automation actions.

You will receive:
1. A "BEFORE" screenshot showing the page state before the action was executed
2. An "AFTER" screenshot showing the page state after the action was executed
3. Action Description (what action was actually executed)

IMPORTANT CONTEXT:
- The BEFORE screenshot shows the page state before the action was taken
- The AFTER screenshot shows the page state after the action was executed
- The action has already been executed - you are validating the RESULTS
- Compare the two screenshots to determine if the action achieved its intended effect
- Look for visual changes, new elements, different states, etc.

Your task is to evaluate whether the executed action was successful based on the visual changes.

Executed Action Description: {action_description}

Please analyze:
1. Did the action execute successfully (no errors, action completed)?
2. Did the page state change as expected from the action?
3. Are there any visual indicators that the action had the intended effect?

IMPORTANT: Respond with ONLY a valid JSON object. Do not include any markdown formatting, code blocks, or additional text. Just return the raw JSON.

{{
    "action_successful": true/false,
    "page_state_changed": true/false,
    "overall_confidence": 0.0-1.0,
    "reasoning": "Your detailed reasoning for the validation",
    "suggestions": "Any suggestions for improvement if issues found"
}}"""

    # Prepare the API request
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OpenAI API key not found")
        return {
            "action_successful": False,
            "page_state_changed": False,
            "overall_confidence": 0.0,
            "reasoning": "API key not found",
            "suggestions": "Set OPENAI_API_KEY environment variable"
        }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": validation_prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{before_base64}"
                        }
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{after_base64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 1000,
        "temperature": 0.1
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # Try to parse the JSON response
            try:
                # Clean the content to remove markdown formatting
                content = content.strip()
                if content.startswith('```json'):
                    content = content[7:]  # Remove ```json
                if content.endswith('```'):
                    content = content[:-3]  # Remove ```
                content = content.strip()
                
                validation_result = json.loads(content)
                print(f"🔍 Post-Action Validation Response: {json.dumps(validation_result, indent=2)}")
                return validation_result
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse post-action validation response as JSON: {content}")
                print(f"❌ JSON Error: {e}")
                return {
                    "action_successful": False,
                    "page_state_changed": False,
                    "overall_confidence": 0.0,
                    "reasoning": f"Invalid JSON response from validation API: {str(e)}",
                    "suggestions": "Check validation prompt format"
                }
        else:
            print(f"❌ Post-action validation API request failed with status {response.status_code}: {response.text}")
            return {
                "action_successful": False,
                "page_state_changed": False,
                "overall_confidence": 0.0,
                "reasoning": f"API request failed: {response.status_code}",
                "suggestions": "Check API configuration"
            }
            
    except Exception as e:
        print(f"❌ Error during post-action validation API call: {e}")
        return {
            "action_successful": False,
            "page_state_changed": False,
            "overall_confidence": 0.0,
            "reasoning": f"Post-action validation API error: {str(e)}",
            "suggestions": "Check network connection and API key"
        }


def process_post_action_validation(
    before_screenshot_path: str,
    after_screenshot_path: str,
    action_description: str,
    output_dir: str = None,
    step_idx: int = None
) -> Dict[str, Any]:
    """
    Main function to process post-action validation.
    
    Args:
        before_screenshot_path: Path to the before screenshot
        after_screenshot_path: Path to the after screenshot
        action_description: Description of the executed action
        output_dir: Directory to save validation results
        step_idx: Current step index
    
    Returns:
        Dictionary containing validation results
    """
    
    # Print validation input details
    print(f"🔍 Post-Action Validation Input Details:")
    print(f"   Action Description: {action_description}")
    
    # Perform validation
    validation_result = make_post_action_validation_call(
        before_screenshot_path,
        after_screenshot_path,
        action_description
    )
    
    # Save validation results if output directory is provided
    if output_dir and step_idx is not None:
        validation_dir = os.path.join(output_dir, 'post_action_validation')
        os.makedirs(validation_dir, exist_ok=True)
        
        validation_file = os.path.join(
            validation_dir,
            f"post_action_validation_step_{step_idx:03d}.json"
        )
        
        with open(validation_file, 'w', encoding='utf-8') as f:
            json.dump({
                "step_index": step_idx,
                "before_screenshot": before_screenshot_path,
                "after_screenshot": after_screenshot_path,
                "action_description": action_description,
                "validation_result": validation_result
            }, f, indent=2, ensure_ascii=False)
        
        print(f"📊 Post-action validation completed for step {step_idx}")
        print(f"   Action Successful: {validation_result.get('action_successful', 'N/A')}")
        print(f"   Page State Changed: {validation_result.get('page_state_changed', 'N/A')}")
        print(f"   Overall Confidence: {validation_result.get('overall_confidence', 'N/A')}")
    
    return validation_result
