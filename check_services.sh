#!/bin/bash
#
# OmniAI Stack Startup Checker
# =============================
# Checks and starts all required services before running diagnostics
#

echo "═══════════════════════════════════════════════════════════════════"
echo "  🚀 OMNI-AI STACK STARTUP CHECKER"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track status
ALL_GOOD=true

echo "Checking services..."
echo ""

# 1. Check Docker
echo -n "1. Docker: "
if command -v docker &> /dev/null; then
    if docker info &> /dev/null; then
        echo -e "${GREEN}✅ Running${NC}"
    else
        echo -e "${YELLOW}⚠️  Installed but not running${NC}"
        echo "   Start Docker Desktop or run: sudo systemctl start docker"
        ALL_GOOD=false
    fi
else
    echo -e "${RED}❌ Not installed${NC}"
    ALL_GOOD=false
fi

# 2. Check PostgreSQL
echo -n "2. PostgreSQL: "
if pg_isready -h localhost -p 5432 &> /dev/null; then
    echo -e "${GREEN}✅ Running${NC}"
else
    echo -e "${YELLOW}⚠️  Not running${NC}"
    echo "   Starting via Docker..."
    docker run -d --name omniai-postgres \
        -e POSTGRES_USER=omniai \
        -e POSTGRES_PASSWORD=omniai \
        -e POSTGRES_DB=omniai \
        -p 5432:5432 \
        postgres:15 &> /dev/null
    if [ $? -eq 0 ]; then
        echo -e "   ${GREEN}✅ Started PostgreSQL container${NC}"
        sleep 3 # Wait for startup
    else
        echo -e "   ${RED}❌ Failed to start${NC}"
        ALL_GOOD=false
    fi
fi

# 3. Check Redis
echo -n "3. Redis: "
if redis-cli ping &> /dev/null; then
    echo -e "${GREEN}✅ Running${NC}"
else
    echo -e "${YELLOW}⚠️  Not running${NC}"
    echo "   Starting via Docker..."
    docker run -d --name omniai-redis -p 6379:6379 redis:7-alpine &> /dev/null
    if [ $? -eq 0 ]; then
        echo -e "   ${GREEN}✅ Started Redis container${NC}"
        sleep 2
    else
        echo -e "   ${YELLOW}⚠️  Could not start (may already exist)${NC}"
    fi
fi

# 4. Check Ollama
echo -n "4. Ollama: "
if curl -s http://localhost:11434/api/tags &> /dev/null; then
    echo -e "${GREEN}✅ Running${NC}"
    
    # Check for models
    MODELS=$(curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*"' | head -5)
    if [ -n "$MODELS" ]; then
        echo "   Available models:"
        echo "$MODELS" | sed 's/"name":"/ - /g' | sed 's/"//g' | sed 's/^/   /'
    fi
else
    echo -e "${YELLOW}⚠️  Not running${NC}"
    echo "   Start Ollama with: ollama serve"
    echo "   Or in a new terminal: ollama serve &"
    ALL_GOOD=false
fi

# 5. Check Python environment
echo -n "5. Python: "
if command -v python3 &> /dev/null; then
    VERSION=$(python3 --version 2>&1)
    echo -e "${GREEN}✅ $VERSION${NC}"
else
    echo -e "${RED}❌ Not found${NC}"
    ALL_GOOD=false
fi

# 6. Check for backend directory
echo -n "6. Backend directory: "
if [ -d "backend" ]; then
    echo -e "${GREEN}✅ Found${NC}"
    BACKEND_DIR="backend"
elif [ -d "../backend" ]; then
    echo -e "${GREEN}✅ Found (parent directory)${NC}"
    BACKEND_DIR="../backend"
else
    echo -e "${RED}❌ Not found${NC}"
    echo "   Make sure you're in the OMNI-AI project directory"
    ALL_GOOD=false
fi

# 7. Check if FastAPI is running
echo -n "7. FastAPI Server: "
if curl -s http://localhost:8000/health &> /dev/null; then
    echo -e "${GREEN}✅ Running${NC}"
else
    echo -e "${YELLOW}⚠️  Not running${NC}"
    
    if [ -n "$BACKEND_DIR" ]; then
        echo "   Would you like to start it? (y/n)"
        read -r START_SERVER
        
        if [ "$START_SERVER" = "y" ] || [ "$START_SERVER" = "Y" ]; then
            echo "   Starting FastAPI server..."
            cd "$BACKEND_DIR" || exit
            
            # Activate virtual environment if it exists
            if [ -f "venv/bin/activate" ]; then
                source venv/bin/activate
            fi
            
            # Start server in background
            python main.py &> /tmp/omniai_server.log &
            SERVER_PID=$!
            
            echo "   Server PID: $SERVER_PID"
            echo "   Waiting for startup..."
            sleep 5
            
            if curl -s http://localhost:8000/health &> /dev/null; then
                echo -e "   ${GREEN}✅ Server started successfully${NC}"
            else
                echo -e "   ${RED}❌ Server failed to start${NC}"
                echo "   Check logs: cat /tmp/omniai_server.log"
                ALL_GOOD=false
            fi
            
            cd - &> /dev/null || exit
        else
            ALL_GOOD=false
        fi
    else
        ALL_GOOD=false
    fi
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"

if [ "$ALL_GOOD" = true ]; then
    echo -e "${GREEN}✅ All services are running!${NC}"
    echo ""
    echo "Ready to run diagnostics:"
    echo "  python omni_diagnostic.py"
else
    echo -e "${YELLOW}⚠️  Some services need attention${NC}"
    echo ""
    echo "Fix the issues above before running diagnostics."
fi

echo "═══════════════════════════════════════════════════════════════════"