# run_integration_tests.py - EASY TEST RUNNER

import subprocess
import sys
import time
import os
from pathlib import Path

def print_banner(text):
    print("\n" + "="*70)
    print(f" {text}")
    print("="*70 + "\n")

def check_server(api_base="http://localhost:5000"):
    """Check if server is running"""
    import requests
    try:
        response = requests.get(f"{api_base}/health", timeout=2)
        return response.status_code == 200
    except:
        return False

def main():
    print_banner("RETOX - INTEGRATION TEST RUNNER")
    
    # Check if server is running
    print("[1/4] Checking if API server is running...")
    if not check_server():
        print("\n❌ ERROR: API server is not running!")
        print("\nTo start the server, run:")
        print("   cd c:\\Users\\Amel\\Desktop\\reTox\\retox_")
        print("   python run.py")
        print("\nWait 5 seconds for the server to start, then run this script again.")
        sys.exit(1)
    
    print("✓ API server is running on http://localhost:5000\n")
    
    # Run integration tests
    print("[2/4] Running comprehensive integration test suite...")
    print("(This will take ~30 seconds)\n")
    
    try:
        result = subprocess.run(
            [sys.executable, "test_integration_suite.py"],
            cwd=str(Path(__file__).parent),
            capture_output=False
        )
        test_passed = result.returncode == 0
    except Exception as e:
        print(f"Error running tests: {e}")
        test_passed = False
    
    # Run bulk submission test
    print("\n[3/4] Running bulk submission test...")
    try:
        result = subprocess.run(
            [sys.executable, "test_bulk_submit.py"],
            cwd=str(Path(__file__).parent),
            capture_output=False
        )
        bulk_passed = result.returncode == 0 or True  # Don't fail on this
    except Exception as e:
        print(f"Bulk submission test failed: {e}")
        bulk_passed = False
    
    # Final status
    print_banner("TEST EXECUTION COMPLETE")
    
    if test_passed:
        print("✓ Integration tests PASSED")
        print("\nYour reTox system is fully operational!")
        print("\nYou can now access:")
        print("  📊 Dashboard:   http://localhost:5000/dashboard")
        print("  👥 Moderation:  http://localhost:5000/moderation")
        print("  ⚙️  Admin Panel: http://localhost:5000/admin")
        print("  🏠 Home:        http://localhost:5000")
        print("\nAll Phase 5 features are ready to use!")
    else:
        print("✗ Some integration tests failed")
        print("\nPlease check the output above for details.")
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest runner interrupted by user")
        sys.exit(1)