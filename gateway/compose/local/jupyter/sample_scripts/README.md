# Automatic Repository Scripts Copy Utility

This directory contains the utility script that **automatically copies** the SDS Gateway repository scripts into each user's JupyterHub home space when their container starts.

## 🎯 **What This Does Automatically**

The `copy_to_home.py` script runs **automatically** via JupyterHub's `post_start_cmd` when each user's container starts up. This ensures every user gets access to:

- **System scripts** (benchmark-disks.sh, create-snapshot.sh, etc.)
- **Your own sample scripts** (including spectrogram scripts)
- **Any other scripts** you develop

## 🚀 **How It Works (Fully Automatic)**

### **No Manual Action Required:**

1. ✅ **User logs into JupyterHub** (automatic)
2. ✅ **User container starts** (automatic)
3. ✅ **Scripts automatically copy** to `~/scripts/` (automatic)
4. ✅ **User gets scripts immediately** (automatic)

### **What Users See:**

- **First login**: Scripts appear automatically in `~/scripts/`
- **Subsequent logins**: Scripts already there, no duplicate copying
- **Always available**: Scripts accessible from anywhere in JupyterHub

## 📁 **What Gets Copied Automatically**

From the repository `gateway/scripts/` directory:
- `benchmark-disks.sh` - Disk performance benchmarking
- `create-snapshot.sh` - Create system snapshots  
- `restore-snapshot.sh` - Restore system snapshots
- `common.sh` - Common shell functions
- Any other scripts in that directory

## 🔧 **Technical Implementation**

### **JupyterHub Configuration:**
```python
# Automatically copy repository scripts to user's home directory when container starts
c.DockerSpawner.post_start_cmd = [
    "pip install spectrumx",
    "python /srv/jupyter/sample_scripts/copy_to_home.py"
]
```

### **Script Features:**
- **Automatic execution** during container startup
- **Duplicate prevention** (won't copy if already exists)
- **Comprehensive logging** for troubleshooting
- **Error handling** with proper exit codes
- **Welcome message** creation for users

## 📚 **User Experience**

### **Immediate Access:**
```bash
# User can immediately access scripts
cd ~/scripts
ls -la

# Run existing scripts
chmod +x *.sh
./benchmark-disks.sh

# Add their own scripts
touch spectrogram_analysis.py
python spectrogram_analysis.py
```

### **Adding Your Own Scripts:**
1. **Navigate to `~/scripts/`** (already created automatically)
2. **Create new Python or shell scripts**
3. **Include your spectrogram sample script**
4. **Run them immediately**

## 💡 **Why This Approach is Perfect**

- **Zero user effort** - Scripts appear automatically
- **Consistent experience** - Every user gets the same setup
- **No manual commands** - Everything happens behind the scenes
- **Professional quality** - Seamless user experience
- **Easy maintenance** - One script handles all users

## 🎉 **Result**

Every JupyterHub user automatically gets:
- ✅ **Repository scripts** in `~/scripts/` (automatic)
- ✅ **Place to add their own scripts** (ready to use)
- ✅ **Immediate access** (no setup required)
- ✅ **Professional experience** (seamless integration)

This is exactly what you requested: **automatic triggering** that copies the repository scripts into each user's newly created JupyterHub home space! 🚀
