# Initialize PaddleOCR instance
from paddleocr import PaddleOCR
import json

ocr = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False)

# Run OCR inference on a sample image 
print("Processing image")
result = ocr.predict(input="letseego.png")

# Process results and create organized JSON structure
for res in result:
    res.print()
    res.save_to_img("output")
    
    # Debug: Check what attributes are available
    print(f"Available attributes: {dir(res)}")
    
    # Create organized JSON structure
    organized_data = {
        "image_path": "letseego.png",  # Use the filename directly
        "text_elements": []
    }
    
    # Access the data from the result object
    # The data is stored in the result object's internal structure
    result_data = res.res if hasattr(res, 'res') else res
    
    # Combine text and bounding boxes into individual objects
    texts = result_data['rec_texts']
    boxes = result_data['rec_boxes'] 
    scores = result_data['rec_scores']
    
    for i, (text, box, score) in enumerate(zip(texts, boxes, scores)):
        text_element = {
            "id": i,
            "text": text,
            "confidence": float(score),
            "bounding_box": {
                "x1": int(box[0]),
                "y1": int(box[1]), 
                "x2": int(box[2]),
                "y2": int(box[3])
            }
        }
        organized_data["text_elements"].append(text_element)
    
    # Save organized JSON
    with open("output/organized_ocr_results.json", "w", encoding="utf-8") as f:
        json.dump(organized_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved organized results with {len(organized_data['text_elements'])} text elements")