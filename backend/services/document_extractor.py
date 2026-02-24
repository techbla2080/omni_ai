"""
Document Text Extraction Service
Extract text from Word, Excel, CSV, TXT files
"""

import os
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class DocumentExtractor:
    """Service for extracting text from various document types"""
    
    def extract_text(self, file_path: str) -> Dict:
        """Extract text based on file type"""
        
        if not os.path.exists(file_path):
            return {"success": False, "error": "File not found", "text": None}
        
        ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if ext == '.docx':
                return self._extract_docx(file_path)
            elif ext in ['.xlsx', '.xls']:
                return self._extract_excel(file_path)
            elif ext == '.csv':
                return self._extract_csv(file_path)
            elif ext in ['.txt', '.md', '.rtf']:
                return self._extract_text(file_path)
            else:
                return {"success": False, "error": f"Unsupported format: {ext}", "text": None}
        except Exception as e:
            logger.error(f"❌ Extraction failed: {e}")
            return {"success": False, "error": str(e), "text": None}
    
    def _extract_docx(self, file_path: str) -> Dict:
        """Extract text from Word document"""
        from docx import Document
        
        doc = Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n\n".join(paragraphs)
        
        logger.info(f"✅ DOCX extracted {len(text)} chars")
        return {"success": True, "text": text, "error": None, "type": "docx"}
    
    def _extract_excel(self, file_path: str) -> Dict:
        """Extract data from Excel file"""
        import pandas as pd
        
        # Read all sheets
        xlsx = pd.ExcelFile(file_path)
        all_text = []
        
        for sheet_name in xlsx.sheet_names:
            df = pd.read_excel(xlsx, sheet_name=sheet_name)
            all_text.append(f"=== Sheet: {sheet_name} ===")
            all_text.append(df.to_string())
        
        text = "\n\n".join(all_text)
        
        logger.info(f"✅ Excel extracted {len(text)} chars from {len(xlsx.sheet_names)} sheets")
        return {"success": True, "text": text, "error": None, "type": "excel", "sheets": len(xlsx.sheet_names)}
    
    def _extract_csv(self, file_path: str) -> Dict:
        """Extract data from CSV file"""
        import pandas as pd
        
        df = pd.read_csv(file_path)
        text = df.to_string()
        
        logger.info(f"✅ CSV extracted {len(text)} chars, {len(df)} rows")
        return {"success": True, "text": text, "error": None, "type": "csv", "rows": len(df)}
    
    def _extract_text(self, file_path: str) -> Dict:
        """Extract plain text"""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        
        logger.info(f"✅ TXT extracted {len(text)} chars")
        return {"success": True, "text": text, "error": None, "type": "text"}


document_extractor = DocumentExtractor()