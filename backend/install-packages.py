import sys
import os
import subprocess
import tempfile

print("=" * 50)
print("NETBOX MOVIE WEBSITE - PACKAGE INSTALLER")
print("=" * 50)

# Add the correct paths
sys.path.insert(0, r'D:\Lib\site-packages')
sys.path.insert(0, r'D:\Lib')

print("\nPython paths:")
for p in sys.path[:5]:  # Show first 5 paths
    print(f"  {p}")

# Check if pip module is accessible
try:
    import pip
    print(f"\n✅ Found pip module: {pip.__version__}")
    pip_available = True
except ImportError:
    print("\n❌ pip module not found in sys.path")
    pip_available = False

# Method 1: Try using pip module directly
if pip_available:
    print("\nInstalling packages using pip module...")
    packages = ["Flask==2.3.3", "Flask-CORS==4.0.0", "gunicorn==21.2.0"]
    
    for package in packages:
        print(f"Installing {package}...")
        try:
            pip.main(['install', package])
            print(f"✅ {package} installed")
        except:
            print(f"⚠️  Failed to install {package}, trying alternative...")

# Method 2: Use subprocess with full Python path
print("\n\nTrying alternative installation method...")

# Install packages one by one
packages = [
    ("Flask", "2.3.3"),
    ("Flask-CORS", "4.0.0"),
    ("gunicorn", "21.2.0"),
    ("Werkzeug", "2.3.7")
]

for package, version in packages:
    print(f"\nInstalling {package}=={version}...")
    
    # Try multiple methods
    methods = [
        [sys.executable, "-m", "pip", "install", f"{package}=={version}"],
        [sys.executable, "-c", f"import sys; sys.path.append(r'D:\\Lib\\site-packages'); import pip; pip.main(['install', '{package}=={version}'])"]
    ]
    
    success = False
    for method in methods:
        try:
            result = subprocess.run(method, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ {package} installed successfully")
                success = True
                break
            else:
                print(f"  Method failed: {result.stderr[:100]}...")
        except:
            continue
    
    if not success:
        print(f"⚠️  Could not install {package}, will try manual download...")

print("\n" + "=" * 50)
print("CHECKING INSTALLATION...")
print("=" * 50)

# Verify installations
try:
    import flask
    print(f"✅ Flask: {flask.__version__}")
except ImportError:
    print("❌ Flask not installed")

try:
    from flask_cors import CORS
    print("✅ Flask-CORS: Installed")
except ImportError:
    print("❌ Flask-CORS not installed")

print("\n" + "=" * 50)
print("SETUP COMPLETE!")
print("=" * 50)

print("\nTo run your website:")
print("1. Create required folders:")
print("   mkdir backend\\movies")
print("   mkdir static\\assets")
print("\n2. Run the app:")
print("   cd backend")
print("   python app.py")
print("\n3. Open browser: http://localhost:5000")

input("\nPress Enter to exit...")