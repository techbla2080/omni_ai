"""
Code Executor Service (Step 50)
Safely execute Python code in a sandboxed environment
"""

import sys
import io
import traceback
import signal
import multiprocessing
from typing import Dict, Any
from contextlib import redirect_stdout, redirect_stderr


# Dangerous modules to block
BLOCKED_MODULES = {
    'os', 'subprocess', 'shutil', 'socket', 'requests', 
    'urllib', 'ftplib', 'telnetlib', 'smtplib', 'poplib',
    'imaplib', 'nntplib', 'http', 'xmlrpc', 'ipaddress',
    'ctypes', 'multiprocessing', 'threading', 'concurrent',
    'asyncio', 'pickle', 'shelve', 'marshal', 'importlib',
    'builtins', '__builtin__', 'eval', 'exec', 'compile',
    'open', 'file', 'input', 'raw_input'
}

# Allowed built-in functions
ALLOWED_BUILTINS = {
    'abs', 'all', 'any', 'bin', 'bool', 'chr', 'dict', 
    'divmod', 'enumerate', 'filter', 'float', 'format',
    'frozenset', 'hex', 'int', 'isinstance', 'issubclass',
    'iter', 'len', 'list', 'map', 'max', 'min', 'next',
    'oct', 'ord', 'pow', 'print', 'range', 'repr', 'reversed',
    'round', 'set', 'slice', 'sorted', 'str', 'sum', 'tuple',
    'type', 'zip', 'True', 'False', 'None'
}

# Maximum execution time (seconds)
TIMEOUT_SECONDS = 5

# Maximum output length (characters)
MAX_OUTPUT_LENGTH = 10000


def create_safe_builtins() -> Dict[str, Any]:
    """Create a restricted set of built-in functions"""
    safe_builtins = {}
    
    for name in ALLOWED_BUILTINS:
        if hasattr(__builtins__, name) if isinstance(__builtins__, dict) else hasattr(__builtins__, name):
            if isinstance(__builtins__, dict):
                if name in __builtins__:
                    safe_builtins[name] = __builtins__[name]
            else:
                if hasattr(__builtins__, name):
                    safe_builtins[name] = getattr(__builtins__, name)
    
    # Add safe versions of some functions
    safe_builtins['print'] = print
    safe_builtins['range'] = range
    safe_builtins['len'] = len
    safe_builtins['str'] = str
    safe_builtins['int'] = int
    safe_builtins['float'] = float
    safe_builtins['bool'] = bool
    safe_builtins['list'] = list
    safe_builtins['dict'] = dict
    safe_builtins['set'] = set
    safe_builtins['tuple'] = tuple
    safe_builtins['True'] = True
    safe_builtins['False'] = False
    safe_builtins['None'] = None
    
    return safe_builtins


def check_code_safety(code: str) -> Dict[str, Any]:
    """Check if code contains potentially dangerous operations"""
    
    dangerous_patterns = [
        ('import os', 'Importing os module is not allowed'),
        ('import subprocess', 'Importing subprocess is not allowed'),
        ('import socket', 'Importing socket is not allowed'),
        ('import requests', 'Importing requests is not allowed'),
        ('from os', 'Importing from os is not allowed'),
        ('from subprocess', 'Importing from subprocess is not allowed'),
        ('__import__', 'Dynamic imports are not allowed'),
        ('eval(', 'eval() is not allowed'),
        ('exec(', 'exec() is not allowed'),
        ('compile(', 'compile() is not allowed'),
        ('open(', 'File operations are not allowed'),
        ('file(', 'File operations are not allowed'),
        ('input(', 'input() is not allowed in this environment'),
        ('raw_input(', 'raw_input() is not allowed'),
        ('globals(', 'globals() is not allowed'),
        ('locals(', 'locals() is not allowed'),
        ('vars(', 'vars() is not allowed'),
        ('dir(', 'dir() is not allowed'),
        ('getattr(', 'getattr() is not allowed'),
        ('setattr(', 'setattr() is not allowed'),
        ('delattr(', 'delattr() is not allowed'),
        ('__', 'Dunder methods/attributes are not allowed'),
    ]
    
    code_lower = code.lower()
    
    for pattern, message in dangerous_patterns:
        if pattern.lower() in code_lower:
            return {
                'safe': False,
                'error': f"Security Error: {message}"
            }
    
    return {'safe': True}


def execute_code_in_process(code: str, result_queue: multiprocessing.Queue):
    """Execute code in a separate process with restrictions"""
    
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    try:
        # Create restricted globals
        restricted_globals = {
            '__builtins__': create_safe_builtins(),
            '__name__': '__main__',
        }
        
        # Add safe modules
        import math
        import random
        import json
        import re
        import datetime
        import collections
        import itertools
        import functools
        import string
        
        restricted_globals['math'] = math
        restricted_globals['random'] = random
        restricted_globals['json'] = json
        restricted_globals['re'] = re
        restricted_globals['datetime'] = datetime
        restricted_globals['collections'] = collections
        restricted_globals['itertools'] = itertools
        restricted_globals['functools'] = functools
        restricted_globals['string'] = string
        
        # Capture output
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            exec(code, restricted_globals)
        
        stdout_output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()
        
        # Truncate if too long
        if len(stdout_output) > MAX_OUTPUT_LENGTH:
            stdout_output = stdout_output[:MAX_OUTPUT_LENGTH] + "\n... (output truncated)"
        
        result_queue.put({
            'success': True,
            'output': stdout_output,
            'error': stderr_output if stderr_output else None
        })
        
    except Exception as e:
        error_msg = traceback.format_exc()
        result_queue.put({
            'success': False,
            'output': stdout_capture.getvalue(),
            'error': str(e),
            'traceback': error_msg
        })


def execute_python_code(code: str) -> Dict[str, Any]:
    """
    Execute Python code safely with timeout and restrictions
    """
    
    import time
    start_time = time.time()
    
    # Check code safety first
    safety_check = check_code_safety(code)
    if not safety_check['safe']:
        return {
            'success': False,
            'output': '',
            'error': safety_check['error'],
            'execution_time': 0
        }
    
    # Create a queue for results
    result_queue = multiprocessing.Queue()
    
    # Create and start process
    process = multiprocessing.Process(
        target=execute_code_in_process,
        args=(code, result_queue)
    )
    process.start()
    
    # Wait with timeout
    process.join(timeout=TIMEOUT_SECONDS)
    
    execution_time = time.time() - start_time
    
    # Check if process is still running (timeout)
    if process.is_alive():
        process.terminate()
        process.join()
        return {
            'success': False,
            'output': '',
            'error': f'Execution timed out after {TIMEOUT_SECONDS} seconds',
            'execution_time': execution_time
        }
    
    # Get result from queue
    try:
        result = result_queue.get_nowait()
        result['execution_time'] = execution_time
        return result
    except:
        return {
            'success': False,
            'output': '',
            'error': 'Failed to get execution result',
            'execution_time': execution_time
        }


def extract_code_from_message(message: str) -> str:
    """Extract code from a message that might contain markdown code blocks or natural language"""
    
    import re
    
    # Strip surrounding quotes first
    message = message.strip()
    if (message.startswith('"') and message.endswith('"')) or \
       (message.startswith("'") and message.endswith("'")):
        message = message[1:-1].strip()
    
    # Try to find ```python ... ``` blocks
    python_block = re.search(r'```python\s*(.*?)\s*```', message, re.DOTALL)
    if python_block:
        return python_block.group(1).strip()
    
    # Try to find ``` ... ``` blocks
    code_block = re.search(r'```\s*(.*?)\s*```', message, re.DOTALL)
    if code_block:
        return code_block.group(1).strip()
    
    # Try to find `code` inline blocks
    inline_block = re.search(r'`([^`]+)`', message)
    if inline_block:
        candidate = inline_block.group(1).strip()
        # Only use if it looks like code (has parentheses, operators, etc.)
        if '(' in candidate or '=' in candidate or '+' in candidate:
            return candidate
    
    # Try to find "Run:" or "Execute:" or "Run this code:" prefix
    run_match = re.search(
        r'(?:run|execute|run this code|execute this code|try running|run this|execute this)[\s:]+(.+)',
        message, re.IGNORECASE | re.DOTALL
    )
    if run_match:
        code = run_match.group(1).strip()
        # Strip quotes from extracted code too
        if (code.startswith('"') and code.endswith('"')) or \
           (code.startswith("'") and code.endswith("'")):
            code = code[1:-1].strip()
        return code
    
    # If message looks like pure code (has print, =, for, etc.), return as-is
    code_indicators = ['print(', '=', 'for ', 'while ', 'if ', 'def ', 'class ', 'import ']
    for indicator in code_indicators:
        if indicator in message:
            return message.strip()
    
    # Return the whole message if no pattern found
    return message.strip()


# Simple execution for non-multiprocessing environments (Windows compatibility)
def execute_python_simple(code: str) -> Dict[str, Any]:
    """
    Simple execution without multiprocessing (for Windows compatibility)
    """
    import time
    start_time = time.time()
    
    # Check code safety first
    safety_check = check_code_safety(code)
    if not safety_check['safe']:
        return {
            'success': False,
            'output': '',
            'error': safety_check['error'],
            'execution_time': 0
        }
    
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    try:
        # Create restricted globals
        restricted_globals = {
            '__builtins__': create_safe_builtins(),
            '__name__': '__main__',
        }
        
        # Add safe modules
        import math
        import random
        import json
        import re
        import datetime
        import collections
        import itertools
        import functools
        import string
        
        restricted_globals['math'] = math
        restricted_globals['random'] = random
        restricted_globals['json'] = json
        restricted_globals['re'] = re
        restricted_globals['datetime'] = datetime
        restricted_globals['collections'] = collections
        restricted_globals['itertools'] = itertools
        restricted_globals['functools'] = functools
        restricted_globals['string'] = string
        
        # Capture output
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            exec(code, restricted_globals)
        
        stdout_output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()
        
        # Truncate if too long
        if len(stdout_output) > MAX_OUTPUT_LENGTH:
            stdout_output = stdout_output[:MAX_OUTPUT_LENGTH] + "\n... (output truncated)"
        
        execution_time = time.time() - start_time
        
        return {
            'success': True,
            'output': stdout_output,
            'error': stderr_output if stderr_output else None,
            'execution_time': execution_time
        }
        
    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = traceback.format_exc()
        
        return {
            'success': False,
            'output': stdout_capture.getvalue(),
            'error': str(e),
            'traceback': error_msg,
            'execution_time': execution_time
        }


# Use simple execution by default (better Windows compatibility)
def run_code(code: str) -> Dict[str, Any]:
    """Main entry point for code execution"""
    return execute_python_simple(code)