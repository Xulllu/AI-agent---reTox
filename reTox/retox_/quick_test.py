# quick_test.py - Simple Quick Test

import requests
import json
from datetime import datetime

API_BASE = "http://localhost:5000"

def print_header(text):
    print(f"\n{'='*60}")
    print(f" {text}")
    print(f"{'='*60}\n")

def test_api():
    print_header("RETOX QUICK API TEST")
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: Health Check
    print("[1/6] Health Check...")
    tests_total += 1
    try:
        r = requests.get(f"{API_BASE}/health", timeout=5)
        if r.status_code == 200:
            print(f"✓ Status: {r.json()['status']}\n")
            tests_passed += 1
        else:
            print(f"✗ Status code: {r.status_code}\n")
    except Exception as e:
        print(f"✗ Error: {e}\n")
    
    # Test 2: Home Page
    print("[2/6] Home Page...")
    tests_total += 1
    try:
        r = requests.get(f"{API_BASE}/", timeout=5)
        if r.status_code == 200 and 'reTox' in r.text:
            print(f"✓ Page loaded successfully\n")
            tests_passed += 1
        else:
            print(f"✗ Status code: {r.status_code}\n")
    except Exception as e:
        print(f"✗ Error: {e}\n")
    
    # Test 3: Dashboard
    print("[3/6] Dashboard...")
    tests_total += 1
    try:
        r = requests.get(f"{API_BASE}/dashboard", timeout=5)
        if r.status_code == 200:
            print(f"✓ Page loaded successfully\n")
            tests_passed += 1
        else:
            print(f"✗ Status code: {r.status_code}\n")
    except Exception as e:
        print(f"✗ Error: {e}\n")
    
    # Test 4: Submit Comment
    print("[4/6] Submit Comment...")
    tests_total += 1
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    payload = {
        "external_id": f"ps_test_{timestamp}",
        "subreddit": "news",
        "author": "powershell_user",
        "text": "This is a test comment from PowerShell",
        "reddit_score": 10,
        "reddit_permalink": "/r/news/comments/abc123"
    }
    
    try:
        r = requests.post(f"{API_BASE}/api/queue/submit", json=payload, timeout=5)
        if r.status_code == 201:
            data = r.json()
            comment_id = data.get('comment_id')
            print(f"✓ Comment submitted (ID: {comment_id})\n")
            tests_passed += 1
            
            # Test 5: Submit Review
            print("[5/6] Submit Review...")
            tests_total += 1
            review_payload = {
                "comment_id": comment_id,
                "decision": "approve",
                "notes": "Test review"
            }
            
            try:
                r = requests.post(f"{API_BASE}/api/reviews", json=review_payload, timeout=5)
                if r.status_code == 201:
                    print(f"✓ Review submitted\n")
                    tests_passed += 1
                else:
                    print(f"✗ Status code: {r.status_code}\n")
            except Exception as e:
                print(f"✗ Error: {e}\n")
        else:
            print(f"✗ Status code: {r.status_code}\n")
    except Exception as e:
        print(f"✗ Error: {e}\n")
    
    # Test 6: Get Stats
    print("[6/6] Dashboard Stats...")
    tests_total += 1
    try:
        r = requests.get(f"{API_BASE}/api/dashboard/stats", timeout=5)
        if r.status_code == 200:
            stats = r.json()
            summary = stats.get('summary', {})
            print(f"✓ Stats retrieved:")
            print(f"  - Total comments: {summary.get('total_comments')}")
            print(f"  - Average toxicity: {summary.get('average_toxicity')}")
            print(f"  - Accuracy: {summary.get('accuracy_percent')}%\n")
            tests_passed += 1
        else:
            print(f"✗ Status code: {r.status_code}\n")
    except Exception as e:
        print(f"✗ Error: {e}\n")
    
    # Summary
    print_header("TEST SUMMARY")
    print(f"Passed: {tests_passed}/{tests_total}")
    pass_rate = (tests_passed / tests_total * 100) if tests_total > 0 else 0
    print(f"Pass Rate: {pass_rate:.1f}%\n")
    
    if tests_passed == tests_total:
        print("✓ ALL TESTS PASSED!\n")
        print("You can now access:")
        print("  🏠 Home:        http://localhost:5000")
        print("  📊 Dashboard:   http://localhost:5000/dashboard")
        print("  👥 Moderation:  http://localhost:5000/moderation")
        print("  ⚙️  Admin:       http://localhost:5000/admin\n")
    else:
        print(f"✗ {tests_total - tests_passed} test(s) failed\n")

if __name__ == '__main__':
    test_api()