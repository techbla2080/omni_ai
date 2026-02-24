# 📂 Visual File Placement Guide

## BEFORE (What You Have Now)

```
OMNI-AI/
│
└── backend/
    ├── api/
    │   └── chat.py                 ← Your original chat
    │
    ├── services/
    │   ├── __pycache__/
    │   ├── context_manager.py
    │   └── llm.py
    │
    ├── utils/
    │   ├── __pycache__/
    │   └── config.py
    │
    ├── .env
    ├── complete_database_schema.sql
    └── main.py
```

---

## AFTER (Where to Put New Files)

```
OMNI-AI/
│
├── backend/
│   ├── api/
│   │   ├── chat.py                     ← Keep your original
│   │   ├── chat_enhanced.py            ← 📥 SAVE HERE (NEW)
│   │   └── capabilities.py             ← 📥 SAVE HERE (NEW)
│   │
│   ├── services/
│   │   ├── __pycache__/
│   │   ├── context_manager.py
│   │   └── llm.py
│   │
│   ├── utils/
│   │   ├── __pycache__/
│   │   └── config.py
│   │
│   ├── scripts/                        ← 📁 CREATE THIS FOLDER
│   │   └── seed_capabilities.py        ← 📥 SAVE HERE (NEW)
│   │
│   ├── .env
│   ├── complete_database_schema.sql
│   └── main.py                         ← ✏️ UPDATE THIS FILE
│
├── docs/                                ← 📁 CREATE THIS FOLDER
│   ├── SMART_IDE.md                    ← 📥 SAVE HERE (NEW)
│   └── QUICK_START_IDE.md              ← 📥 SAVE HERE (NEW)
│
└── test_smart_ide.py                   ← 📥 SAVE HERE (NEW)
```

---

## 🎯 Action Plan (Copy-Paste These Commands)

### Option 1: If Using Terminal/Command Line

```bash
# Navigate to your project
cd ~/OMNI-AI
# OR
cd /path/to/your/OMNI-AI

# Create new directories
mkdir -p backend/scripts
mkdir -p docs

# Now save the downloaded files to these locations:
# 1. seed_capabilities.py    → backend/scripts/seed_capabilities.py
# 2. api_capabilities.py     → backend/api/capabilities.py
# 3. enhanced_chat.py        → backend/api/chat_enhanced.py
# 4. test_smart_ide.py       → test_smart_ide.py
# 5. README_SMART_IDE.md     → docs/SMART_IDE.md
# 6. QUICK_START.md          → docs/QUICK_START_IDE.md
```

### Option 2: If Using File Explorer (Windows/Mac/Linux)

**Step 1: Open your OMNI-AI folder**
- Navigate to where you saved OMNI-AI
- Example: `C:\Users\YourName\OMNI-AI` or `~/OMNI-AI`

**Step 2: Create new folders**
- Inside `OMNI-AI/backend/`, create folder named: `scripts`
- Inside `OMNI-AI/`, create folder named: `docs`

**Step 3: Move/Copy downloaded files**

From your Downloads folder, move:

1. `seed_capabilities.py`
   - **To:** `OMNI-AI/backend/scripts/`
   - **Rename to:** `seed_capabilities.py` (keep name)

2. `api_capabilities.py`
   - **To:** `OMNI-AI/backend/api/`
   - **Rename to:** `capabilities.py` ⚠️ (drop the "api_" prefix)

3. `enhanced_chat.py`
   - **To:** `OMNI-AI/backend/api/`
   - **Rename to:** `chat_enhanced.py` ⚠️ (keep this name)

4. `test_smart_ide.py`
   - **To:** `OMNI-AI/` (root folder)
   - **Rename to:** `test_smart_ide.py` (keep name)

5. `README_SMART_IDE.md`
   - **To:** `OMNI-AI/docs/`
   - **Rename to:** `SMART_IDE.md` ⚠️ (drop "README_" prefix)

6. `QUICK_START.md`
   - **To:** `OMNI-AI/docs/`
   - **Rename to:** `QUICK_START_IDE.md` (add "_IDE")

---

## 📝 File Renaming Summary

⚠️ **Important:** Some files need to be renamed when you save them:

| Downloaded File Name | Save As This Name | Location |
|---------------------|-------------------|----------|
| seed_capabilities.py | seed_capabilities.py | backend/scripts/ |
| api_capabilities.py | **capabilities.py** ⚠️ | backend/api/ |
| enhanced_chat.py | chat_enhanced.py | backend/api/ |
| test_smart_ide.py | test_smart_ide.py | project root |
| README_SMART_IDE.md | SMART_IDE.md | docs/ |
| QUICK_START.md | QUICK_START_IDE.md | docs/ |

---

## ✅ Verification

After saving all files, run this to verify:

### On Mac/Linux:
```bash
cd ~/OMNI-AI

# Check if all files exist
ls backend/scripts/seed_capabilities.py
ls backend/api/capabilities.py
ls backend/api/chat_enhanced.py
ls test_smart_ide.py
ls docs/SMART_IDE.md
ls docs/QUICK_START_IDE.md

# Should see each file path printed (no errors)
```

### On Windows (Command Prompt):
```cmd
cd C:\path\to\OMNI-AI

dir backend\scripts\seed_capabilities.py
dir backend\api\capabilities.py
dir backend\api\chat_enhanced.py
dir test_smart_ide.py
dir docs\SMART_IDE.md
dir docs\QUICK_START_IDE.md
```

### On Windows (PowerShell):
```powershell
cd C:\path\to\OMNI-AI

Test-Path backend\scripts\seed_capabilities.py
Test-Path backend\api\capabilities.py
Test-Path backend\api\chat_enhanced.py
Test-Path test_smart_ide.py
Test-Path docs\SMART_IDE.md
Test-Path docs\QUICK_START_IDE.md

# Should all return "True"
```

---

## 🎨 Visual: Your Desktop → Project

```
Your Downloads Folder
    ↓
    ├── seed_capabilities.py ────────────→ OMNI-AI/backend/scripts/seed_capabilities.py
    ├── api_capabilities.py ─────────────→ OMNI-AI/backend/api/capabilities.py
    ├── enhanced_chat.py ────────────────→ OMNI-AI/backend/api/chat_enhanced.py
    ├── test_smart_ide.py ───────────────→ OMNI-AI/test_smart_ide.py
    ├── README_SMART_IDE.md ─────────────→ OMNI-AI/docs/SMART_IDE.md
    └── QUICK_START.md ──────────────────→ OMNI-AI/docs/QUICK_START_IDE.md
```

---

## 🚨 Common Mistakes to Avoid

### ❌ Wrong: Saving in backend/
```
OMNI-AI/backend/capabilities.py  ← NO!
```

### ✅ Right: Saving in backend/api/
```
OMNI-AI/backend/api/capabilities.py  ← YES!
```

---

### ❌ Wrong: Keeping "api_" prefix
```
OMNI-AI/backend/api/api_capabilities.py  ← NO!
```

### ✅ Right: Removing prefix
```
OMNI-AI/backend/api/capabilities.py  ← YES!
```

---

### ❌ Wrong: Test file in backend/
```
OMNI-AI/backend/test_smart_ide.py  ← NO!
```

### ✅ Right: Test file in root
```
OMNI-AI/test_smart_ide.py  ← YES!
```

---

## 🎯 Quick Check List

Before proceeding, verify:

- [ ] Created `backend/scripts/` folder
- [ ] Created `docs/` folder
- [ ] Moved seed_capabilities.py to `backend/scripts/`
- [ ] Moved & renamed api_capabilities.py to `backend/api/capabilities.py`
- [ ] Moved enhanced_chat.py to `backend/api/chat_enhanced.py`
- [ ] Moved test_smart_ide.py to project root
- [ ] Moved docs to `docs/` folder
- [ ] All 6 files in correct locations
- [ ] File names match exactly (case-sensitive!)

---

## 🆘 If You're Still Unsure

**Tell me:**
1. What operating system are you using? (Windows/Mac/Linux)
2. Where is your OMNI-AI project located? (full path)
3. What does your folder structure look like now?

**I'll give you exact commands to run!**

---

## 🎉 Once Files Are in Place

Then you can:

1. **Run the seed script:**
   ```bash
   cd backend
   python scripts/seed_capabilities.py
   ```

2. **Update main.py** (see FILE_PLACEMENT_GUIDE.md)

3. **Start your server:**
   ```bash
   python main.py
   ```

4. **Test it:**
   ```bash
   # From project root
   python test_smart_ide.py
   ```

Ready? Save the files and let me know when you're done! 🚀