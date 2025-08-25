from doctr.io import DocumentFile
from doctr.models import ocr_predictor

model = ocr_predictor(pretrained=True)
# PDF
image = DocumentFile.from_images("testMapImage2.png")
# Analyze
result = model(image)
result.show()
print(result)