import base64
from io import BytesIO
import os
from PIL import Image
from typing import List
import openai

def resize_image_base64(path: str, max_width=512) -> str:
    """Resize image and return base64-encoded PNG."""
    with Image.open(path) as img:
        if img.width > max_width:
            aspect_ratio = img.height / img.width
            new_height = int(max_width * aspect_ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

def generate_augmented_instructions(
    instructions: List[str],
    screenshot_path: str = None,
    model: str = "gpt-4o"
) -> List[str]:
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    instruction_text = "\n".join([f"{i+1}. {instr}" for i, instr in enumerate(instructions)])

    system_msg = {
        "role": "system",
        "content": (
            f"You are an assistant that rewrites user instructions into clear, explicit, and actionable steps for a web automation agent"
            f"Your output should be clear and executable, and contain a high-level directions based only on the visible UI elements existing in the screenshot."
            f"If instruction is vague, explained implicitly, or lack key information for the web agent, please add clarifying keywords or add more details relevant to the page to clarify the instruction "
            f"For example:"
            f"For pages maps or flights that involves navigation, transport, or routes, you should include explicit methods or modes and clear location endpoints if implied (e.g., 'by car', 'by walking', 'from Seattle to San Francisco')."
            f"For pages like maps, calendar, or flights you should add clear timing (e.g., 'right now', 'form May 12 to May 23', 'at 12 pm', etc.)."
            f"You should also use explicit UI verbs relevant to the page (e.g., 'open', 'search', 'navigate', 'send', 'compose')"
            f"IMPORTANT: If includes personal information like name, address, or contact details of a person, replace with a realistic placeholder"
            f"Example: 'email my mom' -> 'send a message to mom@example.com' or 'share my calendar with my friend' -> 'share your calendar with sam@example.com'"
            f"If instruction includes an animate noun or references to a group of people, replace it with a random generic name/s or generate contact details if needded"
            f"Example: 'invite my team to a progress check meeting' -> 'send an event invitation to sam@example.com, john@example.com, and jane@example.com'"
            f"If instruction is too complex, you can just focus on the simple but most important part of the instruction"
            f"Output 1 sentence of instruction per instruction input"
        )
    }

    user_content = [{"type": "text", "text": (
        "Below is a list of user instructions. Rewrite each one.\n"
        f"Instructions:\n{instruction_text}\n\n"
        f"Make sure your output is a list of instructions, no other text, no need for quotations, in english."

    )}]

    # 👇 Append image only once and safely
    if screenshot_path and os.path.exists(screenshot_path):
        img_b64 = resize_image_base64(screenshot_path)
        user_content.append({
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64," + img_b64}
        })

    messages = [system_msg, {"role": "user", "content": user_content}]

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.5
    )

    result = resp.choices[0].message.content.strip()

    # Print token usage
    if hasattr(resp, "usage") and resp.usage:
        print(f"API reported: input: {resp.usage.prompt_tokens}, output: {resp.usage.completion_tokens}, total: {resp.usage.total_tokens}")
    else:
        print("Token usage info not available from API response.")

    # Parse response
    augmented_list = []
    for line in result.split("\n"):
        line = line.strip()
        if line:
            parts = line.split(". ", 1)
            augmented_list.append(parts[1] if len(parts) == 2 else parts[0])

    return augmented_list
