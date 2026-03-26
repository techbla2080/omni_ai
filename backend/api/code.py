"""
Code Execution API (Step 50)
Endpoint for running Python code safely
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from services.code_executor import run_code, extract_code_from_message

router = APIRouter(prefix="/api/v1", tags=["code"])


class CodeExecuteRequest(BaseModel):
    """Request to execute code"""
    code: str
    language: str = "python"
    extract_from_message: bool = False


class CodeExecuteResponse(BaseModel):
    """Response from code execution"""
    success: bool
    output: str
    error: Optional[str] = None
    execution_time: float
    image: Optional[str] = None  # base64 PNG for matplotlib plots


@router.post("/code/execute", response_model=CodeExecuteResponse)
async def execute_code(request: CodeExecuteRequest):
    """
    Execute Python code safely
    - **code**: Python code to execute (or message containing code)
    - **language**: Programming language (currently only python)
    - **extract_from_message**: If true, extract code from markdown blocks
    """
    code = request.code

    # Extract code from message if requested
    if request.extract_from_message:
        code = extract_code_from_message(code)

    # Auto-detect if the input looks like a natural language message
    # rather than actual code
    if not request.extract_from_message:
        lower = code.lower().strip()
        natural_prefixes = [
            "run this", "execute this", "run:", "execute:",
            "can you run", "please run", "try running"
        ]
        for prefix in natural_prefixes:
            if lower.startswith(prefix):
                code = extract_code_from_message(code)
                break

    if not code or not code.strip():
        raise HTTPException(status_code=400, detail="No code provided")

    # Execute code
    result = run_code(code)

    print(f"💻 Code executed: {'✅ Success' if result['success'] else '❌ Error'} ({result['execution_time']:.3f}s)")

    return CodeExecuteResponse(
        success=result['success'],
        output=result.get('output', ''),
        error=result.get('error'),
        execution_time=result.get('execution_time', 0),
        image=result.get('image')
    )


@router.post("/code/validate")
async def validate_code(request: CodeExecuteRequest):
    """
    Validate Python code without executing
    Checks for syntax errors and dangerous operations
    """
    code = request.code

    if request.extract_from_message:
        code = extract_code_from_message(code)

    if not code or not code.strip():
        raise HTTPException(status_code=400, detail="No code provided")

    # Check syntax
    try:
        compile(code, '<string>', 'exec')
        syntax_valid = True
        syntax_error = None
    except SyntaxError as e:
        syntax_valid = False
        syntax_error = f"Line {e.lineno}: {e.msg}"

    # Check safety
    from services.code_executor import check_code_safety
    safety_result = check_code_safety(code)

    return {
        'valid': syntax_valid and safety_result['safe'],
        'syntax_valid': syntax_valid,
        'syntax_error': syntax_error,
        'safety_valid': safety_result['safe'],
        'safety_error': safety_result.get('error')
    }