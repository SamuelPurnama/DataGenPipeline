import os
import base64
from typing import List
from PIL import Image
from io import BytesIO
import openai

def resize_image_base64(path: str, max_width=512) -> str:
    """Resize the image to a smaller width to reduce vision token usage, and return base64-encoded image."""
    with Image.open(path) as img:
        if img.width > max_width:
            aspect_ratio = img.height / img.width
            new_height = int(max_width * aspect_ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

def generate_instructions(
    persona: str,
    phase: int,
    num_instructions: int,
    screenshot_path: str = None,
    axtree: str = None,
    model: str = "gpt-4.1"
) -> List[str]:
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Compose prompt
    if phase == 1:
        prompt = (
            f"Imagine you are a {persona} using this website. "
            f"Based on your persona and the image of the current state of the page, generate a list of {num_instructions} distinct instructions that you might give to an assistant for tasks in this website. "
            f"These instructions must be feasible given the current page state and does not involve modifying/deleting content that is not currently present. "
            f"Vary the complexity of the instructions."
            f"Use a date at least 3 weeks from September 2025."
            f"You may vary the destination and the 'where from' field, do not always use Seattle."
            f"You should add complexity and varietey through filters, constraints, or sorting options."
            f"Return just the list of instructions, no other, no need for quotations, in english."
            f"Example, (but do not include these in your output): "
            f"- Can you search for cheap 1-week roundtrip flight options from Austin at October under $150 with flight duration less than 3 hours"
            f"- Find the cheapest direct one-way flights from Seoul to Tokyo on October that arrives before 1 pm local time."
            f"- Search for the cheapest direct round-trip economy class flights from Seattle to Orlando for 1 passenger, departing and returning on dates next month."
            f"- Find the cheapest one week roundtrip flight form San Francisco to Honolulu for 2 people around December."
            f"- Search for the cheapest one-way Delta air premium economy class flight from Seattle to London for 1 passenger, departing on the 10th of October."
        )
    else:
        prompt = (
            f"Imagine you are a {persona} using this website. "
            f"previously, you have asked an assistant to perform some tasks on this website. As you can probably see in the screenshot, the website have some existing elements/content in them. "
            f"Based on your persona and the image of the current state of the page, generate a list of {num_instructions} distinct instructions that you might give to an assistant for tasks in this website. "
            f"These instructions must be feasible given the current page state, try to involve modifying/deleting elements that are currently present, and use realistic natural human phrasing."
            f"Make sure to use natural language when writing the instructions."
            f"You can get creative with the instructions, vary the complexity."
            f"IMPORTANT NOTE: These instructions will be done in order, so do not delete an event in the first instruction, and then write an instruction to modify the same event right after."
            f"Try to not modify or delete the same events more than once."
            f"When targeting a specific event to modify or delete use a SPECIFIC DATE and the name, do not just give the month"
            f"If you are adding/changing details of an event, make sure to give what you are changing it to."
            f"Here is the accessibility tree of the current page state to help you understand what elements are available:\n\n{axtree}\n\n"
            f"return just the list of instructions, no other, no need for quotations, in english, dont make the instructions too complex."
        )

    # Prepare messages for OpenAI API
    messages = [
        {"role": "system", "content": "You are a helpful assistant."}
    ]
    user_content = [{"type": "text", "text": prompt}]
    if screenshot_path and os.path.exists(screenshot_path):
        with open(screenshot_path, "rb") as image_file:
            img_b64 = base64.b64encode(image_file.read()).decode('utf-8')
        user_content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + img_b64}})
    messages.append({"role": "user", "content": user_content})

    # Call the API
    resp = client.chat.completions.create(
        model=model,
        temperature=0.7,
        messages=messages,
        n=1
    )
    result = resp.choices[0].message.content.strip()

    # Print actual token usage from API response if available
    output_tokens = getattr(resp.usage, "completion_tokens", None)
    total_tokens = getattr(resp.usage, "total_tokens", None)
    if output_tokens is not None and total_tokens is not None:
        print(f"API reported: input tokens: {total_tokens - output_tokens}, output tokens: {output_tokens}, total: {total_tokens}")
    else:
        print("Token usage info not available from API response.")

    # Split into lines, remove bullets/numbers, and filter empty lines
    instructions = []
    for line in result.splitlines():
        line = line.strip(" -0123456789.")
        if line:
            instructions.append(line)
    return instructions[:num_instructions]
