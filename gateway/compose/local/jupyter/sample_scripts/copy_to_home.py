#!/usr/bin/env python3
# ruff: noqa: T201, G004, EXE001, F841, TRY300, BLE001, TRY400, PTH123
"""
Automatic Repository Scripts Copy Utility

This script automatically copies the gateway/scripts directory from the SDS code
repository into the user's JupyterHub home directory when their container starts up.

It runs automatically via JupyterHub's post_start_cmd, ensuring every user gets
access to the repository scripts without manual intervention.

Note: Print statements are intentional for user feedback in this utility script.
"""

import logging
import shutil
import sys
from pathlib import Path

# Configure logging for JupyterHub integration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def copy_repository_scripts():
    """Copy the repository scripts directory to the user's home directory."""

    # Get the user's home directory
    home_dir = Path.home()
    target_dir = home_dir / "scripts"

    # Source is the gateway/scripts directory (mounted in the container)
    # We need to look for the actual scripts directory that should be mounted
    source_dir = Path("/srv/jupyter/scripts")

    logger.info(f"Starting automatic script copy for user home: {home_dir}")
    logger.info(f"Source scripts directory: {source_dir}")
    logger.info(f"Target scripts directory: {target_dir}")

    # Check if source directory exists
    if not source_dir.exists():
        logger.error(f"Repository scripts directory not found: {source_dir}")
        logger.error("This script should be run from within the JupyterHub container")
        return False

    # Check if already set up (avoid duplicate copies)
    if target_dir.exists() and any(target_dir.iterdir()):
        logger.info(f"Scripts directory already exists and populated: {target_dir}")
        logger.info("Skipping copy operation to avoid duplicates")
        return True

    # Create target directory if it doesn't exist
    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy all files and subdirectories from the scripts directory
    copied_count = 0
    skipped_count = 0

    try:
        for item in source_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, target_dir)
                logger.info(f"Copied file: {item.name}")
                copied_count += 1
            elif item.is_dir():
                shutil.copytree(item, target_dir / item.name, dirs_exist_ok=True)
                logger.info(f"Copied directory: {item.name}/")
                copied_count += 1

        logger.info(f"Copy operation completed: {copied_count} items copied")

        if copied_count > 0:
            # Create a welcome message
            create_welcome_message(target_dir)

            # Log success
            logger.info(f"Successfully set up scripts directory: {target_dir}")
            logger.info(
                f"Available scripts: {[item.name for item in target_dir.iterdir()]}"
            )

        return True

    except Exception as e:
        logger.error(f"Error copying repository scripts: {e}")
        return False


def create_welcome_message(target_dir: Path):
    """Create a welcome message for the user."""

    welcome_file = target_dir / "WELCOME.md"

    welcome_content = """# Welcome to SDS Gateway JupyterHub! 👋

## 🎉 Your repository scripts are ready!

This directory contains scripts from the SDS Gateway repository, automatically
copied to your JupyterHub home space for easy access.

## 📁 Available Scripts

### System Scripts
- **`benchmark-disks.sh`** - Disk performance benchmarking
- **`create-snapshot.sh`** - Create system snapshots
- **`restore-snapshot.sh`** - Restore system snapshots
- **`common.sh`** - Common shell functions

### Your Scripts
This directory is also where you can add your own sample scripts, including:
- Spectrogram generation scripts
- Data analysis utilities
- Custom RF processing tools
- Any other scripts you develop

## 🚀 Usage

### Shell Scripts
```bash
# Make scripts executable
chmod +x *.sh

# Run a script
./benchmark-disks.sh
./create-snapshot.sh
```

### Python Scripts
```bash
# Run Python scripts
python your_script.py
python spectrogram_analysis.py
```

### Adding Your Own Scripts
1. Create new Python or shell scripts in this directory
2. Make shell scripts executable: `chmod +x your_script.sh`
3. Run them from anywhere: `~/scripts/your_script.py`

## 🔧 Dependencies

Some scripts may require specific packages. Install them as needed:
```bash
pip install numpy matplotlib scipy h5py digital_rf
```

## 📚 Next Steps

1. Explore the available repository scripts
2. Add your own spectrogram and analysis scripts here
3. Customize scripts for your specific needs
4. Check the main SDS Gateway documentation

## 💡 Tips

- This directory is in your home space, so you can modify scripts
- Keep backups of important scripts before modifying
- Test scripts in a safe environment first
- Add your spectrogram and analysis scripts here

Happy scripting! 🎯
"""

    try:
        with open(welcome_file, "w") as f:
            f.write(welcome_content)
        logger.info("Created welcome message for user")
    except Exception as e:
        logger.error(f"Could not create welcome message: {e}")


def main():
    """Main function - called automatically by JupyterHub."""

    logger.info("Starting automatic repository scripts copy for JupyterHub user")

    try:
        success = copy_repository_scripts()

        if success:
            logger.info("Repository scripts copy completed successfully")
            print("✅ Repository scripts automatically copied to ~/scripts/")
        else:
            logger.error("Failed to copy repository scripts")
            print("❌ Failed to copy repository scripts automatically")
            return 1

    except Exception as e:
        logger.error("Unexpected error during automatic copy: %s", e)
        print(f"💥 Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    # Exit with appropriate code for JupyterHub integration
    sys.exit(main())
