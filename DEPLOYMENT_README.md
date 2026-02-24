# 🚀 OmniAI Deployment Guide

## Files in this package

| File | Purpose |
|------|---------|
| `Dockerfile` | Builds the FastAPI backend container |
| `docker-compose.yml` | Orchestrates all 5 services |
| `nginx.conf` | Reverse proxy + serves frontend |
| `.env.example` | Template for environment variables |
| `init.sql` | Complete database schema (fixes column mismatches) |
| `requirements.txt` | Python dependencies |
| `deploy.sh` | One-command VPS setup script |
| `.dockerignore` | Keeps Docker image clean |

---

## ⚠️ REQUIRED CODE CHANGES (before deploying)

### 1. Make Ollama URL configurable

In `backend/utils/config.py`, add:
```python
OLLAMA_BASE_URL: str = Field(default="http://localhost:11434")
```

Then in `backend/services/llm.py` (or wherever you call Ollama), replace:
```python
# OLD:
url = "http://localhost:11434/api/generate"

# NEW:
from utils.config import settings
url = f"{settings.OLLAMA_BASE_URL}/api/generate"
```

### 2. Remove dev_reset_token from auth.py

In `backend/api/auth.py`, in the `forgot_password` endpoint, remove this line:
```python
"dev_reset_token": reset_token  # DELETE THIS LINE
```

### 3. Fix CORS for production

In `backend/main.py`, change:
```python
# OLD:
allow_origins=["*"]

# NEW (replace with your domain):
allow_origins=["https://yourdomain.com", "http://yourdomain.com"]
```

Or keep `["*"]` for initial testing, lock it down later.

### 4. Set DEBUG=False

In `.env`:
```
DEBUG=False
```

---

## 🖥️ Deployment Steps

### Step 1: Get a VPS
- Hetzner CX22 (€4.5/mo, 4GB RAM) — recommended
- DigitalOcean 4GB ($24/mo)
- Minimum: 4GB RAM, 2 vCPU, 40GB SSD, Ubuntu 22/24

### Step 2: SSH into your server
```bash
ssh root@YOUR_SERVER_IP
```

### Step 3: Upload your project
```bash
# Option A: Git (recommended)
apt install git -y
git clone YOUR_REPO_URL /opt/omniai
cd /opt/omniai

# Option B: SCP from your local machine
scp -r ./OMNI-AI root@YOUR_SERVER_IP:/opt/omniai
ssh root@YOUR_SERVER_IP
cd /opt/omniai
```

### Step 4: Place deployment files
Copy all files from this package into your project root:
```
/opt/omniai/
├── Dockerfile          ← new
├── docker-compose.yml  ← new
├── nginx.conf          ← new
├── .env.example        ← new
├── init.sql            ← new (replaces complete_database_schema.sql)
├── deploy.sh           ← new
├── .dockerignore       ← new
├── requirements.txt    ← new/updated
├── backend/
├── frontend/
```

### Step 5: Run deployment
```bash
chmod +x deploy.sh
./deploy.sh
```

### Step 6: Verify
Open `http://YOUR_SERVER_IP` in browser. You should see the login page.

---

## 🔒 Enable HTTPS (after pointing domain)

1. Point your domain A record to server IP
2. Wait for DNS propagation (5-30 min)
3. Run:
```bash
docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d yourdomain.com

# Then restart nginx
docker compose restart nginx
```

4. Update nginx.conf to add SSL server block (I can provide this when ready)

---

## 📋 Common Commands

```bash
# View all logs
docker compose logs -f

# View specific service
docker compose logs -f backend

# Restart a service
docker compose restart backend

# Stop everything
docker compose down

# Start everything
docker compose up -d

# Enter database shell
docker compose exec postgres psql -U omniai

# Pull a new Ollama model
docker compose exec ollama ollama pull llama3.2:3b

# Check disk usage
docker system df
```

---

## 🚨 Troubleshooting

**Backend won't start:**
```bash
docker compose logs backend
# Usually: missing Python package or DB connection issue
```

**Ollama out of memory:**
```bash
# Check RAM usage
free -h
# If < 1GB free, Ollama can't run. Upgrade VPS or use smaller model.
```

**Database errors:**
```bash
# Reset database (WARNING: deletes all data)
docker compose down -v
docker compose up -d
```

**Can't connect from browser:**
```bash
# Check firewall
ufw allow 80
ufw allow 443
```