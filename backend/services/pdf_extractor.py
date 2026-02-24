"""
PDF Text Extraction Service
Extract text from PDF files
"""

import PyPDF2
import os
from typing import Dict
import logging
import re

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Service for extracting text from PDF files"""
    
    def extract_text(self, file_path: str) -> Dict:
        """
        Extract text from a PDF file
        
        Returns:
            Dict with: text, pages, success, error
        """
        
        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": "File not found",
                "text": None,
                "pages": 0
            }
        
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                num_pages = len(pdf_reader.pages)
                
                text_content = []
                
                for page_num in range(num_pages):
                    try:
                        page = pdf_reader.pages[page_num]
                        page_text = page.extract_text()
                        
                        if page_text and page_text.strip():
                            text_content.append(f"--- Page {page_num + 1} ---\n{page_text}")
                    except Exception as e:
                        logger.warning(f"Could not extract page {page_num + 1}: {e}")
                        text_content.append(f"--- Page {page_num + 1} ---\n[Could not extract]")
                
                full_text = "\n\n".join(text_content)
                full_text = self._clean_text(full_text)
                
                logger.info(f"✅ Extracted {len(full_text)} chars from {num_pages} pages")
                
                return {
                    "success": True,
                    "text": full_text,
                    "pages": num_pages,
                    "error": None
                }
                
        except Exception as e:
            logger.error(f"❌ PDF extraction failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "text": None,
                "pages": 0
            }
    
    def _clean_text(self, text: str) -> str:
        """Clean extracted text"""
        # Remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        # Remove null characters
        text = text.replace('\x00', '')
        return text.strip()


# Global instance
pdf_extractor = PDFExtractor()