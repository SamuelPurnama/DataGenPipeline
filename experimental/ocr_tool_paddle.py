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
               "elements": []
           }
    
    # Access the data from the result object
    # The data is stored in the result object's internal structure
    result_data = res.res if hasattr(res, 'res') else res
    
    # Combine text and bounding boxes into individual objects
    texts = result_data['rec_texts']
    boxes = result_data['rec_boxes'] 
    scores = result_data['rec_scores']
    
           for i, (text, box, score) in enumerate(zip(texts, boxes, scores)):
               x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
               
               # Calculate click coordinates (center of bounding box)
               click_x = (x1 + x2) // 2
               click_y = (y1 + y2) // 2
               
               text_element = {
                   "annotation_id": i,
                   "text": text,
                   "confidence": float(score),
                   "bounding_box": {
                       "x1": x1,
                       "y1": y1,
                       "x2": x2,
                       "y2": y2
                   },
                   "click_coordinates": {
                       "x": click_x,
                       "y": click_y
                   }
               }
               organized_data["elements"].append(text_element)
    
    # Save organized JSON
    with open("output/organized_ocr_results.json", "w", encoding="utf-8") as f:
        json.dump(organized_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved organized results with {len(organized_data['elements'])} text elements")