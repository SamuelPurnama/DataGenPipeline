"""
Confidence validation utilities for trajectory generation.
Provides functions to validate GPT responses through secondary confirmation calls.
"""

import json
import os
from typing import Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import base64

# Add parent directory to path for imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def annotate_screenshot_with_single_annotation(
    screenshot_path: str, 
    targeting_data: list, 
    annotation_id: str,
    output_path: str
) -> str:
    """
    Annotate a screenshot with a single bounding box for the specified annotation ID.
    
    Args:
        screenshot_path: Path to the original screenshot
        targeting_data: List of targeting data containing bounding box information
        annotation_id: The annotation ID to highlight
        output_path: Path where the annotated screenshot will be saved
    
    Returns:
        Path to the annotated screenshot
    """
    try:
        # Load the screenshot
        image = Image.open(screenshot_path)
        draw = ImageDraw.Draw(image)
        
        # Find the element with the specified annotation ID
        target_element = None
        available_ids = []
        
        # Convert annotation_id to both string and int for comparison
        annotation_id_str = str(annotation_id)
        annotation_id_int = int(annotation_id) if annotation_id.isdigit() else None
        
        for element in targeting_data:
            element_id = element.get('annotation_id')
            available_ids.append(element_id)
            
            # Check for both string and int matches
            if (element_id == annotation_id or 
                element_id == annotation_id_str or 
                element_id == annotation_id_int):
                target_element = element
                break
        
        if not target_element:
            print(f"⚠️ Warning: Annotation ID {annotation_id} not found in targeting data")
            print(f"📋 Available annotation IDs: {available_ids}")
            return screenshot_path  # Return original if not found
        
        # Debug: Print the target element structure
        print(f"🔍 Target element for ID {annotation_id}: {json.dumps(target_element, indent=2)}")
        
        # Get bounding box coordinates
        bbox = target_element.get('bounding_box') or target_element.get('bbox')
        if not bbox:
            print(f"⚠️ Warning: No bounding box found for annotation ID {annotation_id}")
            print(f"🔍 Available keys in target element: {list(target_element.keys())}")
            return screenshot_path
        
        x, y, width, height = bbox['x'], bbox['y'], bbox['width'], bbox['height']
        
        # Draw bounding box
        draw.rectangle([x, y, x + width, y + height], outline='red', width=3)
        
        # Add label text
        try:
            # Try to use a default font, fallback to basic if not available
            font = ImageFont.load_default()
        except:
            font = None
        
        label_text = "This is the element targeted"
        if font:
            draw.text((x, y - 20), label_text, fill='red', font=font)
        else:
            draw.text((x, y - 20), label_text, fill='red')
        
        # Save the annotated image
        image.save(output_path)
        print(f"✅ Created single annotation screenshot: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"❌ Error creating single annotation screenshot: {e}")
        return screenshot_path


def make_validation_gpt_call(
    annotated_screenshot_path: str,
    thought: str,
    updated_goal: str,
    code: str,
    description: str,
    annotation_id: str,
    element_role: str = None,
    element_name: str = None
) -> Dict[str, Any]:
    """
    Make a dedicated GPT call specifically for validation.
    
    Args:
        annotated_screenshot_path: Path to the screenshot with single annotation
        thought: The reasoning from the original GPT response
        updated_goal: The updated goal from the original GPT response
        code: The code from the original GPT response
        description: The description from the original GPT response
        annotation_id: The annotation ID that was selected
    
    Returns:
        Dictionary containing validation results
    """
    
    # Encode the image to base64
    try:
        with open(annotated_screenshot_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"❌ Error encoding image: {e}")
        return {
            "is_correct_target": False,
            "code_matches_description": False,
            "action_appropriate": False,
            "overall_confidence": 0.0,
            "reasoning": f"Image encoding error: {str(e)}",
            "suggestions": "Check image file"
        }
    
    # Create the validation prompt
    element_info = ""
    if element_role or element_name:
        element_info = "\nElement Information:"
        if element_role:
            element_info += f"\n- Role: {element_role}"
        if element_name:
            element_info += f"\n- Name: {element_name}"
    
    validation_prompt = f"""You are a validation assistant that reviews AI-generated web automation actions.

You will receive:
1. A screenshot with a single element highlighted (Important: RED bounding box with the text "This is the element targeted")
2. Action Description (a description of the action that WILL BE taken - this action has NOT been executed yet)
3. Goal (the goal to be achieved)
4. Element Information (role and name of the highlighted element){element_info}

IMPORTANT CONTEXT:
- The screenshot shows the CURRENT state of the webpage BEFORE any action is taken
- The highlighted element (with red box and "This is the element targeted") is the element that the AI wants to interact with
- The highlighted element has the role and name specified in the Element Information above
- The action description describes what the AI PLANS to do with that highlighted element
- This is a validation to check if the AI selected the correct element for the planned action

Your task is to evaluate whether the highlighted element (marked with "This is the element targeted" and having the role/name specified above) is the correct target for the planned action described below.

Planned Action Description: {description}
Goal: {updated_goal}
Code: {code}

Please analyze:
1. Is the highlighted element on the image (with the red bounding box) the correct target for this action description?
2. Does the element match what the action description says it will do?
3. Is this action appropriate for getting closer to the stated goal?
4. Is the code appropriate for the action description?

IMPORTANT: Respond with ONLY a valid JSON object. Do not include any markdown formatting, code blocks, or additional text. Just return the raw JSON.

{{
    "is_correct_target": true/false,
    "code_matches_description": true/false,
    "action_appropriate": true/false,
    "overall_confidence": 0.0-1.0,
    "reasoning": "Your detailed reasoning for the validation",
    "suggestions": "Any suggestions for improvement if issues found"
}}"""

    # Prepare the API request
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OpenAI API key not found")
        return {
            "is_correct_target": False,
            "code_matches_description": False,
            "action_appropriate": False,
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
                            "url": f"data:image/png;base64,{base64_image}"
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
                print(f"🔍 Validation Response: {json.dumps(validation_result, indent=2)}")
                return validation_result
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse validation response as JSON: {content}")
                print(f"❌ JSON Error: {e}")
                return {
                    "is_correct_target": False,
                    "code_matches_description": False,
                    "action_appropriate": False,
                    "overall_confidence": 0.0,
                    "reasoning": f"Invalid JSON response from validation API: {str(e)}",
                    "suggestions": "Check validation prompt format"
                }
        else:
            print(f"❌ API request failed with status {response.status_code}: {response.text}")
            return {
                "is_correct_target": False,
                "code_matches_description": False,
                "action_appropriate": False,
                "overall_confidence": 0.0,
                "reasoning": f"API request failed: {response.status_code}",
                "suggestions": "Check API configuration"
            }
            
    except Exception as e:
        print(f"❌ Error during validation API call: {e}")
        return {
            "is_correct_target": False,
            "code_matches_description": False,
            "action_appropriate": False,
            "overall_confidence": 0.0,
            "reasoning": f"Validation API error: {str(e)}",
            "suggestions": "Check network connection and API key"
        }


def process_confidence_validation(
    gpt_response: Dict[str, Any],
    screenshot_path: str,
    targeting_data: list,
    output_dir: str,
    step_idx: int
) -> Dict[str, Any]:
    """
    Main function to process confidence validation for a GPT response.
    
    Args:
        gpt_response: The original GPT response
        screenshot_path: Path to the original screenshot
        targeting_data: List of targeting data
        output_dir: Directory to save validation outputs
        step_idx: Current step index
    
    Returns:
        Dictionary containing validation results
    """
    if not gpt_response or 'selected_annotation_id' not in gpt_response:
        print("⚠️ No annotation ID found in GPT response, skipping validation")
        return {"validation_skipped": True, "reason": "No annotation ID"}
    
    annotation_id = gpt_response['selected_annotation_id']
    if not annotation_id:  # Empty string check
        print("⚠️ Empty annotation ID, skipping validation")
        return {"validation_skipped": True, "reason": "Empty annotation ID"}
    
    # Create output directories for validation files
    validation_image_dir = os.path.join(output_dir, 'validation_image')
    validation_response_dir = os.path.join(output_dir, 'validationresponse')
    os.makedirs(validation_image_dir, exist_ok=True)
    os.makedirs(validation_response_dir, exist_ok=True)
    
    # Create single annotation screenshot
    single_annotation_path = os.path.join(
        validation_image_dir, 
        f"single_annotation_step_{step_idx:03d}.png"
    )
    
    annotated_path = annotate_screenshot_with_single_annotation(
        screenshot_path,
        targeting_data,
        annotation_id,
        single_annotation_path
    )
    
    # Extract element role and name from targeting data
    element_role = None
    element_name = None
    for element in targeting_data:
        element_id = element.get('annotation_id')
        if (element_id == annotation_id or 
            element_id == str(annotation_id) or 
            element_id == int(annotation_id) if str(annotation_id).isdigit() else False):
            element_info = element.get('element_info', {})
            element_role = element_info.get('role', 'unknown')
            element_name = element_info.get('name', 'unnamed')
            break
    
    # Print validation input details
    print(f"🔍 Validation Input Details:")
    print(f"   Element Role: {element_role}")
    print(f"   Element Name: {element_name}")
    print(f"   Thought: {gpt_response.get('thought', '')}")
    print(f"   Description: {gpt_response.get('description', '')}")
    print(f"   Code: {gpt_response.get('code', '')}")
    
    # Perform validation
    validation_result = make_validation_gpt_call(
        annotated_path,
        gpt_response.get('thought', ''),
        gpt_response.get('updated_goal', ''),
        gpt_response.get('code', ''),
        gpt_response.get('description', ''),
        annotation_id,
        element_role,
        element_name
    )
    
    # Save validation results
    validation_file = os.path.join(
        validation_response_dir,
        f"validation_step_{step_idx:03d}.json"
    )
    
    with open(validation_file, 'w', encoding='utf-8') as f:
        json.dump({
            "step_index": step_idx,
            "original_response": gpt_response,
            "validation_result": validation_result,
            "annotated_screenshot_path": annotated_path
        }, f, indent=2, ensure_ascii=False)
    
    print(f"📊 Validation completed for step {step_idx}")
    print(f"   Overall confidence: {validation_result.get('overall_confidence', 'N/A')}")
    print(f"   Correct target: {validation_result.get('is_correct_target', 'N/A')}")
    
    return validation_result
