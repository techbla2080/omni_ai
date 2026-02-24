"""
Image OCR Text Extraction Service
"""

import pytesseract
from PIL import Image
import os
from typing import Dict
import logging

logger = logging.getLogger(__name__)

# Set Tesseract path (Windows)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


class OCRExtractor:
    SUPPORTED_FORMATS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}
    
    def extract_text(self, file_path: str) -> Dict:
        if not os.path.exists(file_path):
            return {"success": False, "error": "File not found", "text": None}
        
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.SUPPORTED_FORMATS:
            return {"success": False, "error": f"Unsupported format: {ext}", "text": None}
        
        try:
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image).strip()
            
            if not text:
                return {"success": True, "text": "", "error": None}
            
            logger.info(f"✅ OCR extracted {len(text)} chars")
            return {"success": True, "text": text, "error": None}
            
        except Exception as e:
            logger.error(f"❌ OCR failed: {e}")
            return {"success": False, "error": str(e), "text": None}


ocr_extractor = OCRExtractor()