"""
File Upload API
Handle file uploads and processing
Step 42: PDF Text Extraction
Step 43: Image OCR
Step 44: Document Processing
Step 47: Code File Extraction
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import os
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from services.pdf_extractor import pdf_extractor
from services.ocr_extractor import ocr_extractor
from services.document_extractor import document_extractor
from services.code_extractor import extract_code_content

from typing import Optional, List
import re

router = APIRouter(prefix="/api/v1", tags=["files"])

# File storage directory
UPLOAD_DIR = "C:/Users/pagar/OneDrive/Desktop/omni-ai/backend/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Allowed file types
ALLOWED_EXTENSIONS = {
    # Documents
    'pdf', 'doc', 'docx', 'txt', 'md', 'rtf',
    # Images
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg',
    # Spreadsheets
    'xlsx', 'xls', 'csv', 'tsv',
    # Code
    'py', 'js', 'jsx', 'ts', 'tsx', 'java', 'cpp', 'c', 'h', 'hpp',
    'html', 'css', 'scss', 'json', 'xml', 'yaml', 'yml',
    'sh', 'bash', 'sql', 'go', 'rs', 'rb', 'php', 'swift', 'kt',
    # Archives
    'zip', 'tar', 'gz'
}

# Max file size (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024


# ============================================================================
# Pydantic Models
# ============================================================================

class FileResponse(BaseModel):
    """File upload response"""
    file_id: str
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    mime_type: Optional[str]
    uploaded_at: str
    url: str


class FileListResponse(BaseModel):
    """List of files"""
    files: List[FileResponse]
    total: int


# ============================================================================
# Helper Functions
# ============================================================================

def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_type(filename: str) -> str:
    """Determine file type category"""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if ext in ['pdf', 'doc', 'docx', 'txt', 'md', 'rtf']:
        return 'document'
    elif ext in ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg']:
        return 'image'
    elif ext in ['xlsx', 'xls', 'csv', 'tsv']:
        return 'spreadsheet'
    elif ext in ['py', 'js', 'jsx', 'ts', 'tsx', 'java', 'cpp', 'c', 'h', 'hpp',
                 'html', 'css', 'scss', 'json', 'xml', 'yaml', 'yml',
                 'sh', 'bash', 'sql', 'go', 'rs', 'rb', 'php', 'swift', 'kt']:
        return 'code'
    elif ext in ['zip', 'tar', 'gz']:
        return 'archive'
    else:
        return 'other'


# ============================================================================
# File Upload Endpoints
# ============================================================================

@router.post("/files/upload", response_model=FileResponse)
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a file
    
    Supports: PDFs, images, documents, spreadsheets, code files
    Max size: 50MB
    """
    
    # Validate filename
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    # Check file extension
    if not allowed_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    
    # Read file content
    content = await file.read()
    
    # Check file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    # Generate unique file ID and path
    file_id = str(uuid.uuid4())
    file_extension = file.filename.rsplit('.', 1)[1].lower()
    stored_filename = f"{file_id}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, stored_filename)
    
    # Determine file type
    file_type = get_file_type(file.filename)
    original_filename = file.filename
    
    # Save file to disk
    try:
        with open(file_path, 'wb') as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Save metadata to database
    try:
        await db.execute(
            text("""
                INSERT INTO files (
                    id, conversation_id, filename, original_filename, 
                    file_type, file_size, file_path, mime_type, created_at
                )
                VALUES (
                    :id, :conv_id, :filename, :original_filename,
                    :file_type, :file_size, :file_path, :mime_type, NOW()
                )
            """),
            {
                "id": file_id,
                "conv_id": conversation_id,
                "filename": stored_filename,
                "original_filename": original_filename,
                "file_type": file_type,
                "file_size": len(content),
                "file_path": file_path,
                "mime_type": file.content_type
            }
        )
        await db.commit()
    except Exception as e:
        # Clean up file if database insert fails
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Failed to save file metadata: {str(e)}")
    
    print(f"✅ File uploaded: {original_filename} → {file_id} ({file_type})")
    
    # ========== PDF TEXT EXTRACTION (STEP 42) ==========
    if file_type == "document" and original_filename.lower().endswith('.pdf'):
        print(f"📄 Processing PDF: {original_filename}")
        extraction_result = pdf_extractor.extract_text(file_path)
        
        if extraction_result["success"]:
            await db.execute(
                text("""
                    UPDATE files 
                    SET extracted_text = :extracted_text, processed = true
                    WHERE id = :file_id
                """),
                {"extracted_text": extraction_result["text"], "file_id": file_id}
            )
            await db.commit()
            print(f"✅ Extracted {len(extraction_result['text'])} chars from {extraction_result['pages']} pages")
        else:
            await db.execute(
                text("UPDATE files SET processed = true, processing_error = :error WHERE id = :file_id"),
                {"error": extraction_result["error"], "file_id": file_id}
            )
            await db.commit()
            print(f"❌ PDF extraction failed: {extraction_result['error']}")
    # ========== END PDF EXTRACTION ==========
    
    # ========== IMAGE OCR EXTRACTION (STEP 43) ==========
    if file_type == "image":
        print(f"🖼️ Processing image for OCR: {original_filename}")
        ocr_result = ocr_extractor.extract_text(file_path)
        
        if ocr_result["success"] and ocr_result["text"]:
            await db.execute(
                text("UPDATE files SET extracted_text = :extracted_text, processed = true WHERE id = :file_id"),
                {"extracted_text": ocr_result["text"], "file_id": file_id}
            )
            await db.commit()
            print(f"✅ OCR extracted {len(ocr_result['text'])} chars")
        else:
            await db.execute(
                text("UPDATE files SET processed = true WHERE id = :file_id"),
                {"file_id": file_id}
            )
            await db.commit()
            print(f"ℹ️ No text found in image")
    # ========== END IMAGE OCR ==========
    
    # ========== DOCUMENT EXTRACTION (STEP 44) ==========
    if file_type == "document" and not original_filename.lower().endswith('.pdf'):
        print(f"📝 Processing document: {original_filename}")
        doc_result = document_extractor.extract_text(file_path)
        
        if doc_result["success"] and doc_result["text"]:
            await db.execute(
                text("UPDATE files SET extracted_text = :extracted_text, processed = true WHERE id = :file_id"),
                {"extracted_text": doc_result["text"], "file_id": file_id}
            )
            await db.commit()
            print(f"✅ Document extracted {len(doc_result['text'])} chars")
        else:
            await db.execute(
                text("UPDATE files SET processed = true WHERE id = :file_id"),
                {"file_id": file_id}
            )
            await db.commit()
    # ========== END DOCUMENT EXTRACTION ==========
    
    # ========== SPREADSHEET EXTRACTION (STEP 44) ==========
    if file_type == "spreadsheet":
        print(f"📊 Processing spreadsheet: {original_filename}")
        sheet_result = document_extractor.extract_text(file_path)
        
        if sheet_result["success"] and sheet_result["text"]:
            await db.execute(
                text("UPDATE files SET extracted_text = :extracted_text, processed = true WHERE id = :file_id"),
                {"extracted_text": sheet_result["text"], "file_id": file_id}
            )
            await db.commit()
            print(f"✅ Spreadsheet extracted {len(sheet_result['text'])} chars")
        else:
            await db.execute(
                text("UPDATE files SET processed = true WHERE id = :file_id"),
                {"file_id": file_id}
            )
            await db.commit()
    # ========== END SPREADSHEET EXTRACTION ==========
    
    # ========== CODE FILE EXTRACTION (STEP 47) ==========
    if file_type == "code":
        print(f"💻 Processing code file: {original_filename}")
        code_result = extract_code_content(file_path)
        
        if code_result["success"] and code_result["content"]:
            await db.execute(
                text("UPDATE files SET extracted_text = :extracted_text, processed = true WHERE id = :file_id"),
                {"extracted_text": code_result["content"], "file_id": file_id}
            )
            await db.commit()
            print(f"✅ Code extracted: {code_result['line_count']} lines ({code_result['language']})")
        else:
            await db.execute(
                text("UPDATE files SET processed = true, processing_error = :error WHERE id = :file_id"),
                {"error": code_result.get("error", "Unknown error"), "file_id": file_id}
            )
            await db.commit()
            print(f"❌ Code extraction failed: {code_result.get('error')}")
    # ========== END CODE FILE EXTRACTION ==========
    
    return FileResponse(
        file_id=file_id,
        filename=stored_filename,
        original_filename=original_filename,
        file_type=file_type,
        file_size=len(content),
        mime_type=file.content_type,
        uploaded_at=datetime.utcnow().isoformat(),
        url=f"/api/v1/files/{file_id}"
    )


@router.get("/files/{file_id}")
async def get_file(
    file_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get file metadata by ID"""
    
    result = await db.execute(
        text("""
            SELECT id, filename, original_filename, file_type, file_size, 
                   mime_type, created_at, processed, extracted_text
            FROM files WHERE id = :file_id
        """),
        {"file_id": file_id}
    )
    
    file_data = result.fetchone()
    
    if not file_data:
        raise HTTPException(status_code=404, detail="File not found")
    
    return {
        "file_id": str(file_data[0]),
        "filename": file_data[1],
        "original_filename": file_data[2],
        "file_type": file_data[3],
        "file_size": file_data[4],
        "mime_type": file_data[5],
        "created_at": file_data[6].isoformat() if file_data[6] else None,
        "processed": file_data[7],
        "has_text": bool(file_data[8])
    }


@router.get("/files", response_model=FileListResponse)
async def list_files(
    conversation_id: Optional[str] = None,
    file_type: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """List uploaded files"""
    
    query = "SELECT id, filename, original_filename, file_type, file_size, mime_type, created_at FROM files WHERE 1=1"
    params = {}
    
    if conversation_id:
        query += " AND conversation_id = :conv_id"
        params["conv_id"] = conversation_id
    
    if file_type:
        query += " AND file_type = :file_type"
        params["file_type"] = file_type
    
    query += " ORDER BY created_at DESC LIMIT :limit"
    params["limit"] = limit
    
    result = await db.execute(text(query), params)
    rows = result.fetchall()
    
    files = []
    for row in rows:
        files.append(FileResponse(
            file_id=str(row[0]),
            filename=row[1],
            original_filename=row[2],
            file_type=row[3],
            file_size=row[4],
            mime_type=row[5],
            uploaded_at=row[6].isoformat() if row[6] else None,
            url=f"/api/v1/files/{row[0]}"
        ))
    
    return FileListResponse(files=files, total=len(files))


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a file"""
    
    result = await db.execute(
        text("SELECT file_path FROM files WHERE id = :file_id"),
        {"file_id": file_id}
    )
    file_data = result.fetchone()
    
    if not file_data:
        raise HTTPException(status_code=404, detail="File not found")
    
    if os.path.exists(file_data[0]):
        try:
            os.remove(file_data[0])
        except Exception as e:
            print(f"⚠️ Could not delete file: {e}")
    
    await db.execute(text("DELETE FROM files WHERE id = :file_id"), {"file_id": file_id})
    await db.commit()
    
    print(f"🗑️ File deleted: {file_id}")
    return {"status": "deleted", "file_id": file_id, "deleted_at": datetime.utcnow().isoformat()}


@router.get("/files/{file_id}/text")
async def get_file_text(
    file_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get extracted text from a file"""
    
    result = await db.execute(
        text("SELECT extracted_text, processed, processing_error FROM files WHERE id = :file_id"),
        {"file_id": file_id}
    )
    
    file_data = result.fetchone()
    
    if not file_data:
        raise HTTPException(status_code=404, detail="File not found")
    
    extracted_text, processed, error = file_data
    
    if not processed:
        return {"processed": False, "message": "File still processing"}
    if error:
        return {"processed": True, "success": False, "error": error}
    if not extracted_text:
        return {"processed": True, "success": False, "error": "No text extracted"}
    
    return {"processed": True, "success": True, "text": extracted_text, "char_count": len(extracted_text)}


@router.get("/files/stats")
async def get_file_stats(db: AsyncSession = Depends(get_db)):
    """Get file statistics"""
    
    result = await db.execute(text("SELECT * FROM file_stats"))
    stats = result.fetchone()
    
    if not stats:
        return {"total_files": 0, "processed_files": 0, "pending_files": 0, "total_size_bytes": 0, "total_size_mb": 0, "conversations_with_files": 0}
    
    return {
        "total_files": stats[0] or 0,
        "processed_files": stats[1] or 0,
        "pending_files": stats[2] or 0,
        "total_size_bytes": stats[3] or 0,
        "total_size_mb": round((stats[3] or 0) / 1024 / 1024, 2),
        "conversations_with_files": stats[4] or 0
    }

# ============================================================================
# FILE SEARCH (STEP 49)
# ============================================================================

class SearchResult(BaseModel):
    """Search result item"""
    file_id: str
    filename: str
    file_type: str
    snippet: str
    match_count: int
    uploaded_at: Optional[str]


class SearchResponse(BaseModel):
    """Search response"""
    query: str
    results: List[SearchResult]
    total: int


def extract_snippet(text: str, query: str, context_chars: int = 100) -> str:
    """Extract snippet around the matched query"""
    if not text or not query:
        return ""
    
    # Find query position (case-insensitive)
    lower_text = text.lower()
    lower_query = query.lower()
    pos = lower_text.find(lower_query)
    
    if pos == -1:
        # Return beginning of text if no exact match
        return text[:context_chars * 2] + "..." if len(text) > context_chars * 2 else text
    
    # Extract context around match
    start = max(0, pos - context_chars)
    end = min(len(text), pos + len(query) + context_chars)
    
    snippet = text[start:end]
    
    # Add ellipsis
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    
    return snippet


def count_matches(text: str, query: str) -> int:
    """Count occurrences of query in text"""
    if not text or not query:
        return 0
    return len(re.findall(re.escape(query), text, re.IGNORECASE))


@router.get("/files/search", response_model=SearchResponse)
async def search_files(
    q: str,
    file_type: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """
    Search through uploaded files by content and filename
    
    - **q**: Search query
    - **file_type**: Filter by type (document, image, code, spreadsheet)
    - **limit**: Max results (default 20)
    """
    
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    query = q.strip()
    
    # Build search query
    sql = """
        SELECT id, original_filename, file_type, extracted_text, created_at
        FROM files
        WHERE (
            LOWER(original_filename) LIKE LOWER(:search_pattern)
            OR LOWER(extracted_text) LIKE LOWER(:search_pattern)
        )
    """
    params = {"search_pattern": f"%{query}%"}
    
    # Add file type filter
    if file_type:
        sql += " AND file_type = :file_type"
        params["file_type"] = file_type
    
    sql += " ORDER BY created_at DESC LIMIT :limit"
    params["limit"] = limit
    
    try:
        result = await db.execute(text(sql), params)
        rows = result.fetchall()
        
        results = []
        for row in rows:
            file_id, filename, ftype, extracted_text, created_at = row
            
            # Extract snippet and count matches
            snippet = extract_snippet(extracted_text or "", query)
            match_count = count_matches(extracted_text or "", query)
            
            # Also count filename matches
            if query.lower() in filename.lower():
                match_count += 1
            
            results.append(SearchResult(
                file_id=str(file_id),
                filename=filename,
                file_type=ftype,
                snippet=snippet,
                match_count=match_count,
                uploaded_at=created_at.isoformat() if created_at else None
            ))
        
        # Sort by match count (most relevant first)
        results.sort(key=lambda x: x.match_count, reverse=True)
        
        print(f"🔍 Search '{query}' → {len(results)} results")
        
        return SearchResponse(
            query=query,
            results=results,
            total=len(results)
        )
        
    except Exception as e:
        print(f"❌ Search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")