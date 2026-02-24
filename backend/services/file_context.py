"""
File Context Service
Get file content to include in chat context
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


class FileContextService:
    """Service to fetch file content for chat context"""
    
    async def get_file_context(
        self, 
        db: AsyncSession, 
        file_ids: List[str] = None,
        conversation_id: str = None
    ) -> str:
        """
        Get extracted text from files to include in chat
        
        Args:
            db: Database session
            file_ids: Specific file IDs to include
            conversation_id: Get all files from this conversation
            
        Returns:
            Formatted string with file contents
        """
        
        if not file_ids and not conversation_id:
            return ""
        
        try:
            if file_ids:
                # Get specific files
                placeholders = ", ".join([f":id{i}" for i in range(len(file_ids))])
                params = {f"id{i}": fid for i, fid in enumerate(file_ids)}
                
                result = await db.execute(
                    text(f"""
                        SELECT original_filename, file_type, extracted_text
                        FROM files 
                        WHERE id IN ({placeholders}) AND extracted_text IS NOT NULL
                    """),
                    params
                )
            else:
                # Get all files from conversation
                result = await db.execute(
                    text("""
                        SELECT original_filename, file_type, extracted_text
                        FROM files 
                        WHERE conversation_id = :conv_id AND extracted_text IS NOT NULL
                        ORDER BY created_at DESC
                        LIMIT 5
                    """),
                    {"conv_id": conversation_id}
                )
            
            files = result.fetchall()
            
            if not files:
                return ""
            
            # Format file contents
            context_parts = []
            for filename, file_type, content in files:
                # Truncate very long files
                if len(content) > 10000:
                    content = content[:10000] + "\n...[truncated]..."
                
                context_parts.append(f"=== File: {filename} ({file_type}) ===\n{content}")
            
            file_context = "\n\n".join(context_parts)
            logger.info(f"📎 Added {len(files)} file(s) to context ({len(file_context)} chars)")
            
            return file_context
            
        except Exception as e:
            logger.error(f"❌ Failed to get file context: {e}")
            return ""


file_context_service = FileContextService()