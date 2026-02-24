#!/usr/bin/env python3
"""
OmniAI Complete Stack Diagnostic Test Suite
============================================
Tests every component of your stack to show current status
"""

import subprocess
import sys
import json
import time
from datetime import datetime
from typing import Dict, List, Tuple
import os

# Try to import requests, install if not available
try:
    import requests
except ImportError:
    print("Installing requests library...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# Configuration
BASE_URL = "http://localhost:8000"
TEST_USER_ID = "diagnostic-test-user-001"
RESULTS = {
    "passed": [],
    "failed": [],
    "warnings": [],
    "skipped": []
}


def print_header(title: str):
    """Print formatted header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_subheader(title: str):
    """Print formatted subheader"""
    print(f"\n--- {title} ---")


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print test result"""
    if passed:
        status = "✅ PASS"
        RESULTS["passed"].append(test_name)
    else:
        status = "❌ FAIL"
        RESULTS["failed"].append(test_name)
    
    print(f"{status}: {test_name}")
    if details:
        print(f"       {details}")


def print_warning(message: str):
    """Print warning message"""
    print(f"⚠️  WARNING: {message}")
    RESULTS["warnings"].append(message)


def print_skip(test_name: str, reason: str):
    """Print skipped test"""
    print(f"⏭️  SKIP: {test_name} - {reason}")
    RESULTS["skipped"].append(f"{test_name}: {reason}")


def print_info(message: str):
    """Print info message"""
    print(f"ℹ️  {message}")


# ==============================================================================
# INFRASTRUCTURE TESTS
# ==============================================================================

def test_server_running() -> bool:
    """Test 1: Check if FastAPI server is running"""
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        return response.status_code in [200, 404]
    except:
        return False


def test_health_endpoint() -> Tuple[bool, dict]:
    """Test 2: Check health endpoint"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            return True, response.json()
        return False, {}
    except Exception as e:
        return False, {"error": str(e)}


def test_detailed_health() -> Tuple[bool, dict]:
    """Test 3: Check detailed health endpoint"""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/health/detailed", timeout=10)
        if response.status_code == 200:
            return True, response.json()
        return False, {}
    except Exception as e:
        return False, {"error": str(e)}


def test_openapi_docs() -> bool:
    """Test 4: Check Swagger/OpenAPI docs available"""
    try:
        response = requests.get(f"{BASE_URL}/docs", timeout=5)
        return response.status_code == 200
    except:
        return False


# ==============================================================================
# DATABASE TESTS
# ==============================================================================

def test_postgresql_connection() -> Tuple[bool, str]:
    """Test 5: Check PostgreSQL connection"""
    try:
        result = subprocess.run(
            ["pg_isready", "-h", "localhost", "-p", "5432"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0, result.stdout.strip()
    except FileNotFoundError:
        return False, "pg_isready not found (PostgreSQL client tools not installed)"
    except Exception as e:
        return False, str(e)


def test_docker_postgres() -> Tuple[bool, str]:
    """Test 6: Check if PostgreSQL is running in Docker"""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=postgres", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return True, result.stdout.strip()
        return False, "No PostgreSQL container found"
    except FileNotFoundError:
        return False, "Docker not found"
    except Exception as e:
        return False, str(e)


def test_redis_connection() -> Tuple[bool, str]:
    """Test 7: Check Redis connection"""
    try:
        result = subprocess.run(
            ["redis-cli", "ping"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and "PONG" in result.stdout:
            return True, "Redis responding"
        return False, result.stderr or "No PONG response"
    except FileNotFoundError:
        return False, "redis-cli not found"
    except Exception as e:
        return False, str(e)


def test_docker_redis() -> Tuple[bool, str]:
    """Test 8: Check if Redis is running in Docker"""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=redis", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return True, result.stdout.strip()
        return False, "No Redis container found"
    except FileNotFoundError:
        return False, "Docker not found"
    except Exception as e:
        return False, str(e)


# ==============================================================================
# LLM TESTS
# ==============================================================================

def test_ollama_running() -> Tuple[bool, str]:
    """Test 9: Check if Ollama is running"""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "ollama"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return True, f"PID: {result.stdout.strip()}"
        
        # Alternative check via API
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            return True, "Running (via API)"
        return False, "Not running"
    except:
        return False, "Cannot detect Ollama process"


def test_ollama_models() -> Tuple[bool, List[str]]:
    """Test 10: Check available Ollama models"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=10)
        if response.status_code == 200:
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]
            return len(models) > 0, models
        return False, []
    except Exception as e:
        return False, [str(e)]


def test_llm_generation() -> Tuple[bool, dict]:
    """Test 11: Test LLM can generate responses"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/chat",
            json={
                "message": "Say 'test successful' and nothing else",
                "user_id": TEST_USER_ID
            },
            timeout=60  # LLM can be slow
        )
        if response.status_code == 200:
            data = response.json()
            return True, {
                "latency_ms": data.get("latency_ms", 0),
                "has_response": len(data.get("response", "")) > 0,
                "conversation_id": data.get("conversation_id", "")
            }
        return False, {"error": f"Status {response.status_code}"}
    except Exception as e:
        return False, {"error": str(e)}


# ==============================================================================
# CAPABILITIES API TESTS
# ==============================================================================

def test_capabilities_list() -> Tuple[bool, dict]:
    """Test 12: List all capabilities"""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/capabilities", timeout=10)
        if response.status_code == 200:
            data = response.json()
            return True, {
                "total": data.get("total", 0),
                "categories": data.get("categories", []),
                "count": len(data.get("capabilities", []))
            }
        return False, {"status": response.status_code}
    except Exception as e:
        return False, {"error": str(e)}


def test_capabilities_by_category() -> Tuple[bool, dict]:
    """Test 13: Filter capabilities by category"""
    categories = ["email", "calendar", "shopping", "productivity"]
    results = {}
    
    try:
        for cat in categories:
            response = requests.get(
                f"{BASE_URL}/api/v1/capabilities",
                params={"category": cat},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                results[cat] = data.get("total", 0)
            else:
                results[cat] = f"Error: {response.status_code}"
        
        return all(isinstance(v, int) for v in results.values()), results
    except Exception as e:
        return False, {"error": str(e)}


def test_capability_categories() -> Tuple[bool, dict]:
    """Test 14: Get category statistics"""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/capabilities/categories", timeout=10)
        if response.status_code == 200:
            data = response.json()
            return True, {
                "count": len(data),
                "categories": [item.get("category", "") for item in data]
            }
        return False, {"status": response.status_code}
    except Exception as e:
        return False, {"error": str(e)}


def test_capability_natural_search() -> Tuple[bool, dict]:
    """Test 15: Natural language capability search"""
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/capabilities/search/natural",
            params={"query": "Can you help me with emails?"},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return True, {
                "has_capability": data.get("has_capability", False),
                "matches": data.get("matched_capabilities", [])
            }
        return False, {"status": response.status_code}
    except Exception as e:
        return False, {"error": str(e)}


def test_capability_discovery_tracking() -> Tuple[bool, dict]:
    """Test 16: Track capability discovery"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/capabilities/test-cap-id/discover",
            json={
                "user_id": TEST_USER_ID,
                "discovery_method": "diagnostic_test"
            },
            timeout=10
        )
        if response.status_code == 200:
            return True, response.json()
        return False, {"status": response.status_code}
    except Exception as e:
        return False, {"error": str(e)}


def test_capability_usage_tracking() -> Tuple[bool, dict]:
    """Test 17: Track capability usage"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/capabilities/test-cap-id/use",
            json={"user_id": TEST_USER_ID},
            timeout=10
        )
        if response.status_code == 200:
            return True, response.json()
        return False, {"status": response.status_code}
    except Exception as e:
        return False, {"error": str(e)}


def test_user_capability_stats() -> Tuple[bool, dict]:
    """Test 18: Get user capability statistics"""
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/capabilities/user/{TEST_USER_ID}/stats",
            timeout=10
        )
        if response.status_code == 200:
            return True, response.json()
        return False, {"status": response.status_code}
    except Exception as e:
        return False, {"error": str(e)}


# ==============================================================================
# CHAT INTEGRATION TESTS
# ==============================================================================

def test_chat_capability_detection() -> Tuple[bool, dict]:
    """Test 19: Chat detects 'what can you do?' queries"""
    triggers = [
        "What can you do?",
        "Show me your features",
        "Help me discover what's possible"
    ]
    
    results = {}
    
    try:
        for trigger in triggers:
            response = requests.post(
                f"{BASE_URL}/api/v1/chat",
                json={
                    "message": trigger,
                    "user_id": TEST_USER_ID
                },
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                results[trigger] = {
                    "response_type": data.get("response_type", "unknown"),
                    "has_capabilities": data.get("capabilities") is not None,
                    "has_suggestions": data.get("suggestions") is not None
                }
            else:
                results[trigger] = {"error": response.status_code}
        
        # Check if at least one triggered capability list
        detected = any(
            r.get("response_type") == "capability_list" 
            for r in results.values() 
            if isinstance(r, dict)
        )
        return detected, results
    except Exception as e:
        return False, {"error": str(e)}


def test_conversation_persistence() -> Tuple[bool, dict]:
    """Test 20: Test conversation tracking"""
    try:
        # Create a conversation
        response = requests.post(
            f"{BASE_URL}/api/v1/chat",
            json={
                "message": "Remember this: test123",
                "user_id": TEST_USER_ID
            },
            timeout=60
        )
        
        if response.status_code != 200:
            return False, {"error": "Failed to create conversation"}
        
        conv_id = response.json().get("conversation_id")
        
        # Retrieve it
        response = requests.get(
            f"{BASE_URL}/api/v1/chat/conversations/{conv_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            return True, {
                "conversation_id": conv_id,
                "retrievable": True
            }
        return False, {"conversation_id": conv_id, "retrievable": False}
    except Exception as e:
        return False, {"error": str(e)}


# ==============================================================================
# FILE STRUCTURE TESTS
# ==============================================================================

def test_project_structure() -> Tuple[bool, dict]:
    """Test 21: Check project file structure"""
    required_files = {
        "backend/main.py": False,
        "backend/api/chat.py": False,
        "backend/api/capabilities.py": False,
        "backend/api/chat_enhanced.py": False,
        "backend/services/llm.py": False,
        "backend/services/context_manager.py": False,
        "backend/utils/config.py": False,
        "backend/scripts/seed_capabilities.py": False,
        "backend/.env": False,
        "backend/complete_database_schema.sql": False
    }
    
    # Check each file
    base_path = os.getcwd()
    
    # Try common project locations
    possible_paths = [
        base_path,
        os.path.expanduser("~/OMNI-AI"),
        os.path.join(base_path, "OMNI-AI"),
        os.path.expanduser("~"),
    ]
    
    found_project = False
    project_path = ""
    
    for path in possible_paths:
        if os.path.exists(os.path.join(path, "backend/main.py")):
            project_path = path
            found_project = True
            break
    
    if found_project:
        for file in required_files.keys():
            full_path = os.path.join(project_path, file)
            required_files[file] = os.path.exists(full_path)
    
    all_present = all(required_files.values())
    
    return all_present, {
        "project_path": project_path,
        "files": required_files
    }


def test_env_variables() -> Tuple[bool, dict]:
    """Test 22: Check environment variables"""
    required_vars = [
        "DATABASE_URL",
        "REDIS_URL",
        "MODEL_NAME",
        "JWT_SECRET"
    ]
    
    # Try to read from .env file
    env_file_exists = False
    env_vars_found = {}
    
    possible_env_paths = [
        "backend/.env",
        os.path.expanduser("~/OMNI-AI/backend/.env"),
        ".env"
    ]
    
    for env_path in possible_env_paths:
        if os.path.exists(env_path):
            env_file_exists = True
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        key = line.split('=')[0].strip()
                        if key in required_vars:
                            env_vars_found[key] = True
            break
    
    for var in required_vars:
        if var not in env_vars_found:
            env_vars_found[var] = False
    
    all_vars_present = all(env_vars_found.values())
    
    return all_vars_present, {
        "env_file_exists": env_file_exists,
        "variables": env_vars_found
    }


# ==============================================================================
# PERFORMANCE TESTS
# ==============================================================================

def test_response_latency() -> Tuple[bool, dict]:
    """Test 23: Measure API response times"""
    endpoints = {
        "capabilities_list": "/api/v1/capabilities",
        "categories": "/api/v1/capabilities/categories",
        "health": "/health"
    }
    
    latencies = {}
    
    for name, endpoint in endpoints.items():
        try:
            start = time.time()
            response = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
            end = time.time()
            
            if response.status_code == 200:
                latencies[name] = round((end - start) * 1000, 2)  # ms
            else:
                latencies[name] = f"Error: {response.status_code}"
        except Exception as e:
            latencies[name] = f"Error: {str(e)}"
    
    # Check if all latencies are under 500ms
    all_fast = all(
        isinstance(v, (int, float)) and v < 500 
        for v in latencies.values()
    )
    
    return all_fast, latencies


def test_memory_usage() -> Tuple[bool, dict]:
    """Test 24: Check system memory"""
    try:
        result = subprocess.run(
            ["free", "-h"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                mem_line = lines[1].split()
                return True, {
                    "total": mem_line[1],
                    "used": mem_line[2],
                    "free": mem_line[3],
                    "available": mem_line[6] if len(mem_line) > 6 else "N/A"
                }
        return False, {"error": "Cannot parse memory info"}
    except FileNotFoundError:
        # Windows alternative
        try:
            import psutil
            mem = psutil.virtual_memory()
            return True, {
                "total": f"{mem.total / (1024**3):.2f}GB",
                "used": f"{mem.used / (1024**3):.2f}GB",
                "free": f"{mem.free / (1024**3):.2f}GB",
                "percent": f"{mem.percent}%"
            }
        except:
            return False, {"error": "Cannot get memory info"}
    except Exception as e:
        return False, {"error": str(e)}


# ==============================================================================
# MAIN TEST RUNNER
# ==============================================================================

def run_all_tests():
    """Run complete diagnostic suite"""
    
    print_header("🔍 OMNI-AI COMPLETE STACK DIAGNOSTIC")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Testing server at: {BASE_URL}")
    
    # ==== INFRASTRUCTURE ====
    print_header("1️⃣  INFRASTRUCTURE TESTS")
    
    # Test 1: Server running
    if test_server_running():
        print_result("FastAPI Server Running", True)
    else:
        print_result("FastAPI Server Running", False, "Server not responding at localhost:8000")
        print("\n⛔ Cannot continue without server. Please start your backend:")
        print("   cd backend && python main.py")
        return
    
    # Test 2: Health endpoint
    passed, data = test_health_endpoint()
    print_result("Health Endpoint", passed, f"Response: {data}")
    
    # Test 3: Detailed health
    passed, data = test_detailed_health()
    if passed:
        print_result("Detailed Health Check", True)
        checks = data.get("checks", {})
        for service, status in checks.items():
            print(f"       • {service}: {status.get('status', 'unknown')}")
    else:
        print_result("Detailed Health Check", False, "Endpoint not available")
    
    # Test 4: OpenAPI docs
    print_result("Swagger UI (/docs)", test_openapi_docs())
    
    # ==== DATABASES ====
    print_header("2️⃣  DATABASE TESTS")
    
    # Test 5: PostgreSQL
    passed, msg = test_postgresql_connection()
    print_result("PostgreSQL Connection", passed, msg)
    
    # Test 6: Docker PostgreSQL
    passed, msg = test_docker_postgres()
    if passed:
        print_result("PostgreSQL Docker Container", True, msg)
    else:
        print_warning(f"PostgreSQL container: {msg}")
    
    # Test 7: Redis
    passed, msg = test_redis_connection()
    print_result("Redis Connection", passed, msg)
    
    # Test 8: Docker Redis
    passed, msg = test_docker_redis()
    if passed:
        print_result("Redis Docker Container", True, msg)
    else:
        print_warning(f"Redis container: {msg}")
    
    # ==== LLM ====
    print_header("3️⃣  LLM TESTS")
    
    # Test 9: Ollama running
    passed, msg = test_ollama_running()
    print_result("Ollama Service", passed, msg)
    
    # Test 10: Ollama models
    passed, models = test_ollama_models()
    if passed:
        print_result("Ollama Models Available", True, f"Models: {', '.join(models)}")
    else:
        print_result("Ollama Models Available", False, "No models found or Ollama not running")
    
    # Test 11: LLM generation
    print_info("Testing LLM response generation (may take 30-60 seconds)...")
    passed, data = test_llm_generation()
    if passed:
        print_result("LLM Response Generation", True, f"Latency: {data.get('latency_ms', 'N/A')}ms")
    else:
        print_result("LLM Response Generation", False, f"Error: {data.get('error', 'Unknown')}")
    
    # ==== CAPABILITIES API ====
    print_header("4️⃣  SMART AI IDE (CAPABILITIES) TESTS")
    
    # Test 12: List capabilities
    passed, data = test_capabilities_list()
    if passed:
        print_result(
            "List All Capabilities", 
            True, 
            f"Total: {data.get('total', 0)} | Categories: {len(data.get('categories', []))}"
        )
        if data.get('total', 0) < 20:
            print_warning(f"Expected 20 capabilities, found {data.get('total', 0)}")
    else:
        print_result("List All Capabilities", False, f"Error: {data}")
    
    # Test 13: Filter by category
    passed, data = test_capabilities_by_category()
    print_result("Filter by Category", passed, f"Results: {data}")
    
    # Test 14: Category stats
    passed, data = test_capability_categories()
    if passed:
        print_result("Category Statistics", True, f"Found {data.get('count', 0)} categories")
    else:
        print_result("Category Statistics", False, f"Error: {data}")
    
    # Test 15: Natural language search
    passed, data = test_capability_natural_search()
    print_result(
        "Natural Language Search", 
        passed, 
        f"Has capability: {data.get('has_capability', False)}"
    )
    
    # Test 16: Discovery tracking
    passed, data = test_capability_discovery_tracking()
    print_result("Capability Discovery Tracking", passed)
    
    # Test 17: Usage tracking
    passed, data = test_capability_usage_tracking()
    print_result("Capability Usage Tracking", passed)
    
    # Test 18: User stats
    passed, data = test_user_capability_stats()
    if passed:
        print_result(
            "User Statistics", 
            True, 
            f"Discovered: {data.get('discovered_count', 0)} | Used: {data.get('used_count', 0)}"
        )
    else:
        print_result("User Statistics", False)
    
    # ==== CHAT INTEGRATION ====
    print_header("5️⃣  CHAT INTEGRATION TESTS")
    
    # Test 19: Capability detection
    print_info("Testing chat capability detection...")
    passed, data = test_chat_capability_detection()
    if passed:
        print_result("Chat Capability Detection", True, "'What can you do?' triggers capability list")
    else:
        print_result("Chat Capability Detection", False, "Detection not working")
        if isinstance(data, dict):
            for trigger, result in data.items():
                print(f"       • '{trigger}': {result}")
    
    # Test 20: Conversation persistence
    passed, data = test_conversation_persistence()
    print_result("Conversation Tracking", passed, f"ID: {data.get('conversation_id', 'N/A')}")
    
    # ==== FILE STRUCTURE ====
    print_header("6️⃣  PROJECT STRUCTURE TESTS")
    
    # Test 21: Project structure
    passed, data = test_project_structure()
    if passed:
        print_result("Project File Structure", True, f"All files present")
    else:
        print_result("Project File Structure", False, "Missing files")
        if "files" in data:
            for file, exists in data["files"].items():
                status = "✅" if exists else "❌"
                print(f"       {status} {file}")
    
    # Test 22: Environment variables
    passed, data = test_env_variables()
    if passed:
        print_result("Environment Variables", True, "All required vars configured")
    else:
        print_result("Environment Variables", False, "Missing variables")
        if "variables" in data:
            for var, exists in data["variables"].items():
                status = "✅" if exists else "❌"
                print(f"       {status} {var}")
    
    # ==== PERFORMANCE ====
    print_header("7️⃣  PERFORMANCE TESTS")
    
    # Test 23: Response latency
    passed, data = test_response_latency()
    print_result("API Response Latency", passed, "All endpoints < 500ms" if passed else "Slow responses")
    for endpoint, latency in data.items():
        print(f"       • {endpoint}: {latency}{'ms' if isinstance(latency, (int, float)) else ''}")
    
    # Test 24: Memory usage
    passed, data = test_memory_usage()
    if passed:
        print_result("System Memory", True)
        for key, value in data.items():
            print(f"       • {key}: {value}")
    else:
        print_skip("System Memory", "Cannot retrieve memory info")
    
    # ==== SUMMARY ====
    print_header("📊 DIAGNOSTIC SUMMARY")
    
    total_tests = len(RESULTS["passed"]) + len(RESULTS["failed"])
    pass_rate = (len(RESULTS["passed"]) / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\n  Total Tests: {total_tests}")
    print(f"  ✅ Passed: {len(RESULTS['passed'])}")
    print(f"  ❌ Failed: {len(RESULTS['failed'])}")
    print(f"  ⚠️  Warnings: {len(RESULTS['warnings'])}")
    print(f"  ⏭️  Skipped: {len(RESULTS['skipped'])}")
    print(f"\n  📈 Pass Rate: {pass_rate:.1f}%")
    
    # Grade
    if pass_rate >= 90:
        grade = "A - Excellent! 🎉"
    elif pass_rate >= 80:
        grade = "B - Good"
    elif pass_rate >= 70:
        grade = "C - Satisfactory"
    elif pass_rate >= 60:
        grade = "D - Needs Work"
    else:
        grade = "F - Critical Issues"
    
    print(f"  🏆 Grade: {grade}")
    
    # Failed tests detail
    if RESULTS["failed"]:
        print_subheader("Failed Tests (Fix These)")
        for test in RESULTS["failed"]:
            print(f"  ❌ {test}")
    
    # Warnings
    if RESULTS["warnings"]:
        print_subheader("Warnings (Optional Fixes)")
        for warning in RESULTS["warnings"]:
            print(f"  ⚠️  {warning}")
    
    # Stack status
    print_header("🎯 STACK STATUS ASSESSMENT")
    
    # Determine what's working
    core_working = "FastAPI Server Running" in RESULTS["passed"]
    llm_working = "LLM Response Generation" in RESULTS["passed"]
    ide_working = "List All Capabilities" in RESULTS["passed"]
    chat_detection = "Chat Capability Detection" in RESULTS["passed"]
    
    print("\n  CORE COMPONENTS:")
    print(f"  {'✅' if core_working else '❌'} FastAPI Backend")
    print(f"  {'✅' if llm_working else '❌'} LLM Integration (Ollama + Llama)")
    print(f"  {'✅' if ide_working else '❌'} Smart AI IDE (Capabilities)")
    print(f"  {'✅' if chat_detection else '❌'} Chat Capability Detection")
    
    db_working = "PostgreSQL Connection" in RESULTS["passed"]
    redis_working = "Redis Connection" in RESULTS["passed"]
    
    print("\n  DATA LAYER:")
    print(f"  {'✅' if db_working else '🔶'} PostgreSQL Database")
    print(f"  {'✅' if redis_working else '🔶'} Redis Cache")
    print(f"  {'❌'} Pinecone Vectors (Not implemented)")
    print(f"  {'❌'} Neo4j Knowledge Graph (Not implemented)")
    
    print("\n  OVERALL READINESS:")
    
    if core_working and llm_working and ide_working:
        print("  🟢 READY FOR DEMO - Core functionality working!")
        print("      You can show: Chat + Capability Discovery")
    elif core_working and ide_working:
        print("  🟡 PARTIALLY READY - API working, LLM needs attention")
        print("      Can demonstrate: Capability browsing")
    elif core_working:
        print("  🟠 FOUNDATION READY - Server running, features need work")
        print("      Next: Fix LLM integration or capabilities")
    else:
        print("  🔴 NOT READY - Server not running")
        print("      Start with: python backend/main.py")
    
    print_header("📋 RECOMMENDED NEXT STEPS")
    
    if not core_working:
        print("  1. Start your FastAPI server:")
        print("     cd backend && python main.py")
    elif not llm_working:
        print("  1. Fix LLM integration:")
        print("     - Check Ollama is running: ollama serve")
        print("     - Verify model exists: ollama list")
        print("     - Test: ollama run llama3.2:1b 'Hello'")
    elif not ide_working:
        print("  1. Seed capabilities database:")
        print("     python backend/scripts/seed_capabilities.py")
    elif not chat_detection:
        print("  1. Check enhanced chat router is included in main.py")
    elif not db_working:
        print("  1. Start PostgreSQL:")
        print("     docker-compose up -d postgres")
    elif not redis_working:
        print("  1. Start Redis:")
        print("     docker run -d -p 6379:6379 redis:7-alpine")
    else:
        print("  1. 🎉 All core tests passing!")
        print("  2. Consider adding:")
        print("     - Frontend UI")
        print("     - Real integrations (Gmail, Calendar)")
        print("     - User authentication")
    
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    print("\n⚠️  IMPORTANT: Make sure your backend server is running!")
    print("   Command: cd backend && python main.py")
    print("\n   If not running, start it now and wait for it to initialize.\n")
    
    input("Press ENTER when ready to start diagnostic...")
    
    run_all_tests()