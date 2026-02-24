# 🔍 OmniAI Stack Diagnostic Suite

## What This Does

Runs **24 comprehensive tests** across your entire OmniAI stack to show you:
- What's working ✅
- What's broken ❌
- What needs attention ⚠️
- Your overall grade 📊
- Recommended next steps 📋

---

## 📦 Files Included

1. **omni_diagnostic.py** - Main test suite (24 tests)
2. **check_services.sh** - Service startup checker (optional)

---

## 🚀 Quick Start

### Option 1: Just Run the Diagnostic

```bash
# Navigate to your OMNI-AI project
cd OMNI-AI

# Make sure your server is running first!
cd backend
python main.py

# In a NEW terminal, run the diagnostic
cd OMNI-AI
python omni_diagnostic.py
```

### Option 2: Check Services First (Linux/Mac)

```bash
# Make script executable
chmod +x check_services.sh

# Run service checker
./check_services.sh

# Then run diagnostic
python omni_diagnostic.py
```

---

## 📋 What Gets Tested

### 1️⃣ Infrastructure (4 tests)
- FastAPI server running
- Health endpoint responding
- Detailed health check
- Swagger UI accessible

### 2️⃣ Databases (4 tests)
- PostgreSQL connection
- PostgreSQL Docker container
- Redis connection
- Redis Docker container

### 3️⃣ LLM Integration (3 tests)
- Ollama service running
- Available models
- LLM response generation

### 4️⃣ Smart AI IDE (7 tests)
- List all capabilities
- Filter by category
- Category statistics
- Natural language search
- Discovery tracking
- Usage tracking
- User statistics

### 5️⃣ Chat Integration (2 tests)
- "What can you do?" detection
- Conversation persistence

### 6️⃣ Project Structure (2 tests)
- Required files present
- Environment variables configured

### 7️⃣ Performance (2 tests)
- API response latency
- System memory usage

---

## 📊 Understanding Results

### Pass/Fail Indicators

```
✅ PASS - Working correctly
❌ FAIL - Not working (needs fix)
⚠️  WARNING - Working but could be better
⏭️  SKIP - Couldn't test (missing dependency)
```

### Grades

```
A (90-100%) - Excellent! Ready for demo
B (80-89%)  - Good, minor fixes needed
C (70-79%)  - Satisfactory, some work needed
D (60-69%)  - Needs work
F (<60%)    - Critical issues to fix
```

### Stack Status Colors

```
🟢 READY FOR DEMO - Core functionality working
🟡 PARTIALLY READY - Some features working
🟠 FOUNDATION READY - Server running, features need work
🔴 NOT READY - Server not running
```

---

## 🔧 Pre-requisites

Before running the diagnostic:

1. **Python 3.x installed**
2. **Backend server running** (`python main.py`)
3. **PostgreSQL running** (local or Docker)
4. **Ollama running** with a model pulled
5. **Redis running** (optional, for cache tests)

---

## 🐛 Common Issues

### "Server not responding"
```bash
# Start your server first
cd backend
source venv/bin/activate
python main.py
```

### "No module named 'requests'"
The script auto-installs this, but if it fails:
```bash
pip install requests
```

### "Ollama not running"
```bash
# Start Ollama
ollama serve

# In another terminal, verify
ollama list
```

### "PostgreSQL connection failed"
```bash
# Start via Docker
docker run -d --name omniai-postgres \
  -e POSTGRES_USER=omniai \
  -e POSTGRES_PASSWORD=omniai \
  -e POSTGRES_DB=omniai \
  -p 5432:5432 \
  postgres:15
```

### "Capabilities not found"
```bash
# Run the seed script
cd backend
python scripts/seed_capabilities.py
```

---

## 📈 Sample Output

```
═══════════════════════════════════════════════════════════════════
  🔍 OMNI-AI COMPLETE STACK DIAGNOSTIC
═══════════════════════════════════════════════════════════════════

--- 1️⃣  INFRASTRUCTURE TESTS ---
✅ PASS: FastAPI Server Running
✅ PASS: Health Endpoint
✅ PASS: Swagger UI (/docs)

--- 2️⃣  DATABASE TESTS ---
✅ PASS: PostgreSQL Connection
⚠️  WARNING: Redis container: Not running

--- 3️⃣  LLM TESTS ---
✅ PASS: Ollama Service
✅ PASS: LLM Response Generation
       Latency: 1250ms

--- 4️⃣  SMART AI IDE TESTS ---
✅ PASS: List All Capabilities
       Total: 20 | Categories: 9

... (more tests) ...

═══════════════════════════════════════════════════════════════════
  📊 DIAGNOSTIC SUMMARY
═══════════════════════════════════════════════════════════════════

  Total Tests: 24
  ✅ Passed: 20
  ❌ Failed: 2
  ⚠️  Warnings: 2
  
  📈 Pass Rate: 83.3%
  🏆 Grade: B - Good

  OVERALL READINESS:
  🟢 READY FOR DEMO - Core functionality working!

═══════════════════════════════════════════════════════════════════
```

---

## 🎯 After Running Diagnostics

Based on your results:

### If Grade A:
🎉 Celebrate! You're ready to demo. Consider:
- Building a frontend
- Adding real integrations
- Deploying to cloud

### If Grade B-C:
Fix the failed tests first:
- Check error messages
- Follow recommended next steps
- Re-run diagnostic after fixes

### If Grade D-F:
Focus on basics:
1. Get server running
2. Fix database connection
3. Get LLM working
4. Then test again

---

## 💡 Tips

1. **Run tests frequently** - After each major change
2. **Save results** - Redirect output to file: `python omni_diagnostic.py > results.txt`
3. **Fix one thing at a time** - Don't try to fix everything at once
4. **Start from top** - Infrastructure → Database → LLM → Features

---

## 🆘 Need Help?

If tests fail and you're stuck:

1. **Check the error message** - Usually tells you what's wrong
2. **Verify service is running** - Docker, Ollama, PostgreSQL
3. **Check file locations** - Make sure files are in right places
4. **Read the logs** - `tail -f /tmp/omniai_server.log`

---

## 🚀 Ready?

```bash
# Let's see where your stack stands!
python omni_diagnostic.py
```

Good luck! 🍀