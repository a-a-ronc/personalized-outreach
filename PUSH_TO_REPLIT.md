# Push to Replit - Quick Guide

## Option 1: Import from GitHub (Recommended)

### Step 1: Push to GitHub
```bash
git add .
git commit -m "Production-ready: Multi-channel outreach platform"
git push origin master
```

### Step 2: Import to Replit
1. Go to [Replit](https://replit.com)
2. Click "Create Repl"
3. Select "Import from GitHub"
4. Enter your repository URL
5. Replit will automatically clone and set up

### Step 3: Configure Secrets
In Replit, click "Secrets" (lock icon) and add all API keys from your `.env` file.

---

## Option 2: Direct Git Push to Replit

### Step 1: Create Repl on Replit.com
1. Create a blank Python repl
2. Note the Git URL (Settings → Version Control)

### Step 2: Add Replit as Remote
```bash
git remote add replit https://github.com/replit-git/your-repl-name.git
```

### Step 3: Push
```bash
git push replit master
```

---

## Option 3: Manual Upload (Slow)

1. Create blank Python repl on Replit
2. Upload all files via Replit file browser
3. Manually create directories (backend/, dashboard/, data/, etc.)
4. Upload files to correct locations

**Not recommended** - tedious for 30+ files.

---

## What to Push

### ✅ Include These Files:
```
backend/
dashboard/
data/
templates/
logs/
*.py (14 Python modules)
*.md (3 documentation files)
*.sh (start.sh)
*.txt (requirements.txt)
.replit
replit.nix
.env.example
.gitignore
```

### ❌ Don't Push These:
```
.env (contains secrets!)
__pycache__/
*.pyc
data/leads.db (will be created on Replit)
logs/*.log
dashboard/node_modules/
.git/ (if using import from GitHub)
```

---

## Pre-Push Checklist

- [ ] All unnecessary files removed (tmpclaude, test CSVs, etc.)
- [ ] `.env` file NOT in git (check `.gitignore`)
- [ ] `.env.example` has all required variables
- [ ] `requirements.txt` up to date
- [ ] `README.md` updated
- [ ] `test_backend.py` passes locally
- [ ] Git status clean (no uncommitted changes)

---

## After Pushing to Replit

### 1. Configure Secrets
Add all variables from `.env` to Replit Secrets.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Initialize Database
```bash
python migrate_db.py
```

### 4. Test Backend
```bash
python test_backend.py
```

### 5. Start Application
Click "Run" or:
```bash
./start.sh
```

---

## Git Commands Cheatsheet

### Check Status
```bash
git status
```

### Stage All Changes
```bash
git add .
```

### Commit
```bash
git commit -m "Your commit message"
```

### Push to GitHub
```bash
git push origin master
```

### View Remotes
```bash
git remote -v
```

### Add New Remote (Replit)
```bash
git remote add replit <replit-git-url>
```

### Push to Multiple Remotes
```bash
git push origin master
git push replit master
```

---

## Troubleshooting

### "Please tell me who you are" Error
```bash
git config --global user.email "your-email@example.com"
git config --global user.name "Your Name"
```

### Merge Conflicts
```bash
git pull origin master --rebase
# Resolve conflicts
git add .
git rebase --continue
git push origin master
```

### Force Push (Dangerous!)
```bash
git push origin master --force
```
Only use if you're sure!

### Revert Last Commit
```bash
git reset --soft HEAD~1  # Keep changes
git reset --hard HEAD~1  # Discard changes
```

---

## Deployment Timeline

1. **Push to GitHub**: 1 minute
2. **Import to Replit**: 2 minutes
3. **Configure Secrets**: 2 minutes
4. **Install Dependencies**: 3 minutes
5. **Initialize Database**: 30 seconds
6. **Test Backend**: 1 minute
7. **Start Application**: 30 seconds

**Total: ~10 minutes** to go live on Replit! 🚀
