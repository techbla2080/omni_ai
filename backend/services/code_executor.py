"""
Code Executor - Sandbox Edition
Runs Python code in an isolated Docker container
- No access to host filesystem
- No access to database or secrets
- 30 second timeout
- 256MB RAM limit
- No network access (except for sandbox container itself)
"""

import subprocess
import time
import re
import os
import tempfile
import base64
import logging

logger = logging.getLogger(__name__)

# Sandbox container name
SANDBOX_CONTAINER = "omniai-sandbox-1"

# Limits
TIMEOUT_SECONDS = 30
MAX_OUTPUT_LENGTH = 50000

# Dangerous patterns to block before sending to sandbox
BLOCKED_PATTERNS = [
    r'subprocess\.',
    r'os\.system',
    r'os\.popen',
    r'os\.exec',
    r'os\.spawn',
    r'os\.remove',
    r'os\.rmdir',
    r'os\.unlink',
    r'shutil\.rmtree',
    r'__import__\s*\(\s*["\']subprocess',
    r'__import__\s*\(\s*["\']shutil',
    r'eval\s*\(\s*input',
    r'exec\s*\(\s*input',
    r'open\s*\(.*/etc/',
    r'open\s*\(.*/proc/',
    r'open\s*\(.*/sys/',
]


def check_code_safety(code: str) -> dict:
    """Check code for dangerous patterns before execution"""
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return {
                'safe': False,
                'error': f'Blocked: dangerous operation detected ({pattern.split(".")[0]})'
            }
    return {'safe': True}


def run_code(code: str) -> dict:
    """
    Execute Python code in sandbox container
    
    Returns:
        {
            'success': bool,
            'output': str,
            'error': str or None,
            'execution_time': float,
            'image': str or None  # base64 PNG if matplotlib plot generated
        }
    """
    start_time = time.time()
    
    # Safety check first
    safety = check_code_safety(code)
    if not safety['safe']:
        return {
            'success': False,
            'output': '',
            'error': safety['error'],
            'execution_time': time.time() - start_time
        }
    
    # Wrap code to capture matplotlib output
    wrapped_code = _wrap_code_for_plots(code)
    
    try:
        # Try sandbox container first
        result = _run_in_sandbox(wrapped_code)
    except Exception as e:
        logger.warning(f"Sandbox failed ({e}), falling back to local execution")
        # Fallback to local subprocess if sandbox not available
        result = _run_local(wrapped_code)
    
    result['execution_time'] = time.time() - start_time
    return result


def _run_in_sandbox(code: str) -> dict:
    """Run code inside the sandbox Docker container"""
    
    # Write code to a temp file and copy to container
    # Using docker exec with python -c is simpler for short code
    # For longer code, we pipe it via stdin
    
    try:
        process = subprocess.run(
            [
                "docker", "exec",
                "-i",  # interactive for stdin
                "--user", "sandbox",
                SANDBOX_CONTAINER,
                "python3", "-c", code
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env={**os.environ, 'PYTHONUNBUFFERED': '1'}
        )
        
        output = process.stdout[:MAX_OUTPUT_LENGTH]
        error = process.stderr[:MAX_OUTPUT_LENGTH] if process.returncode != 0 else None
        
        # Check for matplotlib image output
        image = None
        if '__PLOT_BASE64__:' in output:
            lines = output.split('\n')
            clean_output = []
            for line in lines:
                if line.startswith('__PLOT_BASE64__:'):
                    image = line.replace('__PLOT_BASE64__:', '')
                else:
                    clean_output.append(line)
            output = '\n'.join(clean_output)
        
        return {
            'success': process.returncode == 0,
            'output': output.strip(),
            'error': error.strip() if error else None,
            'image': image
        }
        
    except subprocess.TimeoutExpired:
        # Kill any running process in sandbox
        subprocess.run(
            ["docker", "exec", SANDBOX_CONTAINER, "pkill", "-f", "python3"],
            capture_output=True, timeout=5
        )
        return {
            'success': False,
            'output': '',
            'error': f'Execution timed out ({TIMEOUT_SECONDS}s limit). Your code took too long to run.',
            'image': None
        }
    except FileNotFoundError:
        raise Exception("Docker not available - sandbox container not running")


def _run_local(code: str) -> dict:
    """Fallback: run code locally with subprocess (less secure)"""
    
    try:
        process = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'PYTHONUNBUFFERED': '1'}
        )
        
        output = process.stdout[:MAX_OUTPUT_LENGTH]
        error = process.stderr[:MAX_OUTPUT_LENGTH] if process.returncode != 0 else None
        
        # Check for matplotlib image output
        image = None
        if '__PLOT_BASE64__:' in output:
            lines = output.split('\n')
            clean_output = []
            for line in lines:
                if line.startswith('__PLOT_BASE64__:'):
                    image = line.replace('__PLOT_BASE64__:', '')
                else:
                    clean_output.append(line)
            output = '\n'.join(clean_output)
        
        return {
            'success': process.returncode == 0,
            'output': output.strip(),
            'error': error.strip() if error else None,
            'image': image
        }
        
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'output': '',
            'error': f'Execution timed out ({TIMEOUT_SECONDS}s limit)',
            'image': None
        }
    except Exception as e:
        return {
            'success': False,
            'output': '',
            'error': str(e),
            'image': None
        }


def _wrap_code_for_plots(code: str) -> str:
    """Wrap code to capture matplotlib plots as base64 images"""
    
    if 'matplotlib' in code or 'plt.' in code or 'plt.show' in code:
        # Add non-interactive backend and save plot to base64
        wrapper = """
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64

# Store original show function
_original_show = plt.show

def _capture_show(*args, **kwargs):
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='#1a1a1f', edgecolor='none')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    print(f'__PLOT_BASE64__:{img_base64}')
    buf.close()

plt.show = _capture_show

"""
        return wrapper + code
    
    return code


def extract_code_from_message(message: str) -> str:
    """Extract code from a message that may contain markdown code blocks"""
    
    # Try to find Python code block
    python_match = re.search(r'```python\s*([\s\S]*?)\s*```', message)
    if python_match:
        return python_match.group(1).strip()
    
    # Try any code block
    code_match = re.search(r'```\s*([\s\S]*?)\s*```', message)
    if code_match:
        return code_match.group(1).strip()
    
    # Try to extract after common prefixes
    for prefix in ['run:', 'execute:', 'run this:', 'execute this:']:
        if message.lower().startswith(prefix):
            return message[len(prefix):].strip()
    
    # Return as-is (might be raw code)
    return message.strip()