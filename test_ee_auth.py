"""
Test script to diagnose Earth Engine authentication issues in QGIS.

Run this script in QGIS's Python console:
1. Open QGIS
2. Go to Plugins > Python Console
3. Copy and paste this entire script
4. Set your project_id below
"""

import os
import sys

print("=" * 60)
print("Earth Engine Authentication Diagnostic")
print("=" * 60)

# Check Python version and path
print(f"\nPython version: {sys.version}")
print(f"Python executable: {sys.executable}")

# Check if credentials file exists
credentials_path = os.path.expanduser("~/.config/earthengine/credentials")
print(f"\nCredentials file path: {credentials_path}")
print(f"Credentials file exists: {os.path.exists(credentials_path)}")

if os.path.exists(credentials_path):
    try:
        with open(credentials_path, "r") as f:
            import json

            creds = json.load(f)
            print(f"Credentials file contains keys: {list(creds.keys())}")
            # Check if it has the expected keys
            expected_keys = ["client_id", "client_secret", "refresh_token"]
            missing_keys = [k for k in expected_keys if k not in creds]
            if missing_keys:
                print(f"⚠ Missing keys in credentials: {missing_keys}")
    except Exception as e:
        print(f"✗ Error reading credentials: {e}")
else:
    print("✗ Credentials file not found!")
    print("\nTo authenticate, run in this console:")
    print("  import ee")
    print("  ee.Authenticate()")
    print("\nThen run this diagnostic script again.")

# Try to import Earth Engine
print("\n" + "-" * 60)
print("Testing Earth Engine import and initialization")
print("-" * 60)

try:
    import ee

    print(f"✓ Earth Engine module imported successfully")
    print(f"  EE Version: {ee.__version__}")
    print(f"  EE Location: {ee.__file__}")
except ImportError as e:
    print(f"✗ Failed to import Earth Engine: {e}")
    print("\nTo install Earth Engine API, run in QGIS Python Console:")
    print("  import subprocess, sys")
    print(
        "  subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'earthengine-api'])"
    )
    sys.exit(1)

# Get project ID from plugin settings
print("\n" + "-" * 60)
print("Checking plugin settings")
print("-" * 60)

try:
    from qgis.PyQt.QtCore import QSettings

    settings = QSettings()
    project_id = settings.value("GeeDataCatalogs/ee_project", "", type=str)
    env_project = os.environ.get("EE_PROJECT_ID", None)

    print(f"Project ID from settings: {project_id if project_id else '(not set)'}")
    print(f"Project ID from env var: {env_project if env_project else '(not set)'}")

    # Use the first available project ID
    if not project_id:
        project_id = env_project

    if not project_id:
        print("\n⚠ No project ID found!")
        print("Please set your project ID in:")
        print("  1. Plugin Settings (recommended), OR")
        print("  2. Set EE_PROJECT_ID environment variable")
        project_id = input("\nEnter your GCP Project ID to test: ").strip()

except Exception as e:
    print(f"✗ Error reading settings: {e}")
    project_id = input("\nEnter your GCP Project ID to test: ").strip()

# Test initialization
print("\n" + "-" * 60)
print("Testing Earth Engine initialization")
print("-" * 60)

try:
    print(f"Attempting to initialize with project: {project_id}")
    ee.Initialize(project=project_id)
    print("✓ Earth Engine initialized successfully!")

    # Test a simple EE operation
    print("\nTesting Earth Engine functionality...")
    try:
        image = ee.Image("USGS/SRTMGL1_003")
        scale = image.projection().nominalScale().getInfo()
        print(f"✓ Successfully accessed and queried SRTM dataset")
        print(f"  Nominal scale: {scale} meters")
        print("\n✓✓✓ All tests passed! Earth Engine is working correctly. ✓✓✓")
    except Exception as e:
        print(f"⚠ EE initialized but query failed: {e}")

except Exception as e:
    print(f"✗ Failed to initialize Earth Engine")
    print(f"Error: {str(e)}")
    print("\n" + "-" * 60)
    print("Troubleshooting Steps")
    print("-" * 60)
    print("\n1. Authenticate in QGIS Python Console:")
    print("   import ee")
    print("   ee.Authenticate()")
    print("\n2. Verify your Project ID is correct")
    print(f"   Current: {project_id}")
    print("\n3. Check that your GCP project has Earth Engine enabled:")
    print("   https://console.cloud.google.com/apis/library/earthengine.googleapis.com")
    print("\n4. Try re-authenticating:")
    print("   import ee")
    print("   ee.Authenticate(force=True)")

print("\n" + "=" * 60)
print("Diagnostic complete")
print("=" * 60)
