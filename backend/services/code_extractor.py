# ============================================================================
# OmniAI - Code File Extractor
# ============================================================================

import os
from typing import Optional, Dict

# Supported code file extensions
CODE_EXTENSIONS = {
    # Python
    '.py': 'python',
    '.pyw': 'python',
    '.pyx': 'python',
    
    # JavaScript / TypeScript
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.mjs': 'javascript',
    
    # Web
    '.html': 'html',
    '.htm': 'html',
    '.css': 'css',
    '.scss': 'scss',
    '.sass': 'sass',
    '.less': 'less',
    
    # Data formats
    '.json': 'json',
    '.yaml': 'yaml',
    '.yml': 'yaml',
    '.xml': 'xml',
    '.csv': 'csv',
    
    # Config files
    '.env': 'env',
    '.ini': 'ini',
    '.toml': 'toml',
    '.cfg': 'config',
    
    # Shell / Scripts
    '.sh': 'bash',
    '.bash': 'bash',
    '.zsh': 'zsh',
    '.bat': 'batch',
    '.ps1': 'powershell',
    
    # Database
    '.sql': 'sql',
    
    # Documentation
    '.md': 'markdown',
    '.txt': 'text',
    '.rst': 'rst',
    
    # Other languages
    '.java': 'java',
    '.c': 'c',
    '.cpp': 'cpp',
    '.h': 'c',
    '.hpp': 'cpp',
    '.cs': 'csharp',
    '.go': 'go',
    '.rs': 'rust',
    '.rb': 'ruby',
    '.php': 'php',
    '.swift': 'swift',
    '.kt': 'kotlin',
    '.r': 'r',
    '.R': 'r',
}


def is_code_file(filename: str) -> bool:
    """Check if file is a supported code file"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in CODE_EXTENSIONS


def get_language(filename: str) -> Optional[str]:
    """Get programming language from filename"""
    ext = os.path.splitext(filename)[1].lower()
    return CODE_EXTENSIONS.get(ext)


def extract_code_content(filepath: str) -> Dict:
    """
    Extract content from a code file
    
    Args:
        filepath: Path to the code file
        
    Returns:
        Dict with content, language, line_count, etc.
    """
    filename = os.path.basename(filepath)
    
    if not is_code_file(filename):
        return {
            'success': False,
            'error': f'Unsupported file type: {filename}'
        }
    
    try:
        # Try UTF-8 first (most common)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # Fallback to latin-1 (handles any byte)
            with open(filepath, 'r', encoding='latin-1') as f:
                content = f.read()
        
        # Get file stats
        lines = content.split('\n')
        line_count = len(lines)
        char_count = len(content)
        
        # Detect language
        language = get_language(filename)
        
        # Basic code analysis
        analysis = analyze_code(content, language)
        
        return {
            'success': True,
            'content': content,
            'language': language,
            'line_count': line_count,
            'char_count': char_count,
            'analysis': analysis
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def analyze_code(content: str, language: str) -> Dict:
    """
    Basic code analysis
    
    Returns:
        Dict with functions, classes, imports, etc.
    """
    analysis = {
        'has_functions': False,
        'has_classes': False,
        'has_imports': False,
        'is_empty': len(content.strip()) == 0
    }
    
    if analysis['is_empty']:
        return analysis
    
    lines = content.split('\n')
    
    # Python analysis
    if language == 'python':
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('def '):
                analysis['has_functions'] = True
            elif stripped.startswith('class '):
                analysis['has_classes'] = True
            elif stripped.startswith('import ') or stripped.startswith('from '):
                analysis['has_imports'] = True
    
    # JavaScript/TypeScript analysis
    elif language in ['javascript', 'typescript']:
        for line in lines:
            stripped = line.strip()
            if 'function ' in stripped or '=>' in stripped:
                analysis['has_functions'] = True
            elif stripped.startswith('class '):
                analysis['has_classes'] = True
            elif stripped.startswith('import ') or 'require(' in stripped:
                analysis['has_imports'] = True
    
    # Generic analysis for other languages
    else:
        analysis['has_functions'] = 'function' in content or 'def ' in content
        analysis['has_classes'] = 'class ' in content
        analysis['has_imports'] = 'import ' in content or '#include' in content
    
    return analysis


def get_code_summary(content: str, language: str, max_lines: int = 50) -> str:
    """
    Get a summary of code file for AI context
    
    Args:
        content: Full code content
        language: Programming language
        max_lines: Max lines to include
        
    Returns:
        Formatted summary string
    """
    lines = content.split('\n')
    total_lines = len(lines)
    
    # If file is small, return full content
    if total_lines <= max_lines:
        return f"```{language}\n{content}\n```"
    
    # For large files, show beginning and end
    half = max_lines // 2
    beginning = '\n'.join(lines[:half])
    ending = '\n'.join(lines[-half:])
    
    summary = f"""```{language}
# === First {half} lines ===
{beginning}

# ... ({total_lines - max_lines} lines omitted) ...

# === Last {half} lines ===
{ending}
```"""
    
    return summary