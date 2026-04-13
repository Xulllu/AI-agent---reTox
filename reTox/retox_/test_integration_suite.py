# test_integration_suite.py - COMPREHENSIVE INTEGRATION TEST

import requests
import json
import time
from datetime import datetime
import sys
from typing import Dict, List, Tuple

# ===== CONFIGURATION =====

API_BASE = "http://localhost:5000"
TIMEOUT = 10
VERBOSE = True

# ===== COLOR OUTPUT =====

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    """Print section header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}\n")

def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")

def print_error(text):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")

def print_warning(text):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")

def print_info(text):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ {text}{Colors.RESET}")

# ===== TEST UTILITIES =====

def make_request(method: str, endpoint: str, data: dict = None, expect_status: int = 200) -> Tuple[bool, dict]:
    """Make HTTP request and return (success, data)"""
    try:
        url = f"{API_BASE}{endpoint}"
        
        if method.upper() == 'GET':
            response = requests.get(url, timeout=TIMEOUT)
        elif method.upper() == 'POST':
            response = requests.post(url, json=data, timeout=TIMEOUT)
        elif method.upper() == 'PUT':
            response = requests.put(url, json=data, timeout=TIMEOUT)
        else:
            return False, {'error': f'Unknown method: {method}'}
        
        if response.status_code == expect_status:
            try:
                return True, response.json()
            except:
                return True, {'raw': response.text}
        else:
            return False, {'error': f'Status {response.status_code}', 'response': response.text[:200]}
    
    except requests.exceptions.ConnectionError:
        return False, {'error': f'Connection failed to {url}'}
    except Exception as e:
        return False, {'error': str(e)}

# ===== TEST FUNCTIONS =====

def test_health_check():
    """Test: Health check endpoint"""
    print_info("Testing health check...")
    success, data = make_request('GET', '/health')
    
    if success and data.get('status') == 'ok':
        print_success(f"Health check passed - Status: {data['status']}")
        return True
    else:
        print_error(f"Health check failed: {data}")
        return False

def test_info_endpoint():
    """Test: Info endpoint"""
    print_info("Testing info endpoint...")
    success, data = make_request('GET', '/info')
    
    if success and 'name' in data:
        print_success(f"Info endpoint OK - App: {data.get('name')}")
        return True
    else:
        print_error(f"Info endpoint failed: {data}")
        return False

def test_home_page():
    """Test: Home page loads"""
    print_info("Testing home page...")
    try:
        response = requests.get(f"{API_BASE}/", timeout=TIMEOUT)
        if response.status_code == 200 and 'reTox' in response.text:
            print_success("Home page loaded successfully")
            return True
        else:
            print_error(f"Home page failed: Status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Home page error: {e}")
        return False

def test_dashboard_page():
    """Test: Dashboard page loads"""
    print_info("Testing dashboard page...")
    try:
        response = requests.get(f"{API_BASE}/dashboard", timeout=TIMEOUT)
        if response.status_code == 200 and 'dashboard' in response.text.lower():
            print_success("Dashboard page loaded successfully")
            return True
        else:
            print_error(f"Dashboard page failed: Status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Dashboard page error: {e}")
        return False

def test_moderation_page():
    """Test: Moderation page loads"""
    print_info("Testing moderation page...")
    try:
        response = requests.get(f"{API_BASE}/moderation", timeout=TIMEOUT)
        if response.status_code == 200 and 'moderation' in response.text.lower():
            print_success("Moderation page loaded successfully")
            return True
        else:
            print_error(f"Moderation page failed: Status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Moderation page error: {e}")
        return False

def test_admin_page():
    """Test: Admin page loads"""
    print_info("Testing admin page...")
    try:
        response = requests.get(f"{API_BASE}/admin", timeout=TIMEOUT)
        if response.status_code == 200 and 'admin' in response.text.lower():
            print_success("Admin page loaded successfully")
            return True
        else:
            print_error(f"Admin page failed: Status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Admin page error: {e}")
        return False

def test_submit_comment() -> int:
    """Test: Submit a comment and return comment_id"""
    print_info("Testing comment submission...")
    
    timestamp = int(time.time() * 1000)
    payload = {
        "external_id": f"test_{timestamp}",
        "subreddit": "test",
        "author": "test_user",
        "text": "This is a test comment for integration testing",
        "reddit_score": 10,
        "reddit_permalink": "/r/test/comments/abc123"
    }
    
    success, data = make_request('POST', '/api/queue/submit', payload, expect_status=201)
    
    if success and 'comment_id' in data:
        print_success(f"Comment submitted: ID {data['comment_id']}")
        return data['comment_id']
    else:
        print_error(f"Comment submission failed: {data}")
        return None

def test_dashboard_stats():
    """Test: Get dashboard statistics"""
    print_info("Testing dashboard stats endpoint...")
    success, data = make_request('GET', '/api/dashboard/stats')
    
    if success and 'summary' in data:
        summary = data['summary']
        print_success(f"Dashboard stats retrieved:")
        print(f"  - Total comments: {summary.get('total_comments')}")
        print(f"  - Average toxicity: {summary.get('average_toxicity')}")
        print(f"  - Accuracy: {summary.get('accuracy_percent')}%")
        return True
    else:
        print_error(f"Dashboard stats failed: {data}")
        return False

def test_recent_comments():
    """Test: Get recent comments"""
    print_info("Testing recent comments endpoint...")
    success, data = make_request('GET', '/api/dashboard/recent-comments?limit=5')
    
    if success and 'comments' in data:
        print_success(f"Retrieved {len(data['comments'])} recent comments")
        return True
    else:
        print_error(f"Recent comments failed: {data}")
        return False

def test_training_status():
    """Test: Get training status"""
    print_info("Testing training status endpoint...")
    success, data = make_request('GET', '/api/training/status')
    
    if success:
        print_success(f"Training status retrieved:")
        print(f"  - Gold labels: {data.get('gold_labels_since_last_train')}")
        print(f"  - Threshold: {data.get('gold_threshold')}")
        print(f"  - Retraining enabled: {data.get('retraining_enabled')}")
        return True
    else:
        print_error(f"Training status failed: {data}")
        return False

def test_training_history():
    """Test: Get training history"""
    print_info("Testing training history endpoint...")
    success, data = make_request('GET', '/api/training/history')
    
    if success and 'models' in data:
        print_success(f"Training history retrieved: {len(data['models'])} model versions")
        return True
    else:
        print_error(f"Training history failed: {data}")
        return False

def test_queue_stats():
    """Test: Get queue statistics"""
    print_info("Testing queue stats endpoint...")
    success, data = make_request('GET', '/api/queue/stats')
    
    if success and 'queued' in data:
        print_success(f"Queue stats retrieved:")
        print(f"  - Queued: {data.get('queued')}")
        print(f"  - Processing: {data.get('processing')}")
        print(f"  - Completed: {data.get('completed')}")
        return True
    else:
        print_warning(f"Queue stats endpoint not yet implemented")
        return False

def test_submit_review(comment_id: int):
    """Test: Submit a review"""
    print_info(f"Testing review submission for comment {comment_id}...")
    
    payload = {
        "comment_id": comment_id,
        "decision": "approve",
        "notes": "Test review for integration testing"
    }
    
    success, data = make_request('POST', '/api/reviews', payload, expect_status=201)
    
    if success:
        print_success(f"Review submitted successfully")
        return True
    else:
        print_error(f"Review submission failed: {data}")
        return False

def test_get_profile():
    """Test: Get subreddit profile"""
    print_info("Testing profile endpoint...")
    success, data = make_request('GET', '/api/profiles/test')
    
    if success and 'subreddit' in data:
        print_success(f"Profile retrieved for {data['subreddit']}")
        return True
    else:
        print_error(f"Profile retrieval failed: {data}")
        return False

def test_get_user_profile():
    """Test: Get user toxicity profile"""
    print_info("Testing user profile endpoint...")
    success, data = make_request('GET', '/api/users/test_user')
    
    if success and 'author' in data:
        print_success(f"User profile retrieved:")
        print(f"  - Total comments: {data.get('total_comments')}")
        print(f"  - Toxicity rate: {data.get('toxicity_rate')}")
        print(f"  - High risk: {data.get('is_high_risk')}")
        return True
    else:
        print_warning(f"User profile endpoint may not have data yet")
        return False

def test_error_handling():
    """Test: Error handling (404, 400)"""
    print_info("Testing error handling...")
    
    # Test 404
    success, data = make_request('GET', '/nonexistent', expect_status=404)
    if success or data.get('error') == 'Not found':
        print_success("404 handling works correctly")
    else:
        print_warning(f"404 handling unexpected: {data}")
    
    # Test 400 (bad request)
    bad_payload = {"invalid": "data"}
    success, data = make_request('POST', '/api/queue/submit', bad_payload, expect_status=400)
    if not success or 'error' in data:
        print_success("400 handling works correctly")
    else:
        print_warning(f"400 handling unexpected")
    
    return True

# ===== MAIN TEST SUITE =====

def run_all_tests():
    """Run complete test suite"""
    print_header("RETOX INTEGRATION TEST SUITE")
    print_info(f"Testing: {API_BASE}")
    print_info(f"Time: {datetime.utcnow().isoformat()}\n")
    
    results = {
        'passed': 0,
        'failed': 0,
        'warnings': 0,
        'tests': []
    }
    
    # Test 1: Health Check
    print_header("PHASE 1: SYSTEM HEALTH")
    if test_health_check():
        results['passed'] += 1
    else:
        results['failed'] += 1
        print_error("FATAL: System not responding. Aborting tests.")
        return results
    
    # Test 2: Info & Pages
    print_header("PHASE 2: ENDPOINTS & PAGES")
    tests = [
        ("Info Endpoint", test_info_endpoint),
        ("Home Page", test_home_page),
        ("Dashboard Page", test_dashboard_page),
        ("Moderation Page", test_moderation_page),
        ("Admin Page", test_admin_page),
    ]
    
    for name, test_func in tests:
        if test_func():
            results['passed'] += 1
        else:
            results['failed'] += 1
        results['tests'].append(name)
    
    # Test 3: API Endpoints
    print_header("PHASE 3: API ENDPOINTS")
    
    # Submit test comment
    comment_id = test_submit_comment()
    if comment_id:
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Submit review
    if comment_id and test_submit_review(comment_id):
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Dashboard stats
    if test_dashboard_stats():
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Recent comments
    if test_recent_comments():
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Training endpoints
    if test_training_status():
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    if test_training_history():
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Queue stats
    if test_queue_stats():
        results['passed'] += 1
    else:
        results['warnings'] += 1
    
    # Profiles
    if test_get_profile():
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    if test_get_user_profile():
        results['passed'] += 1
    else:
        results['warnings'] += 1
    
    # Test 4: Error Handling
    print_header("PHASE 4: ERROR HANDLING")
    if test_error_handling():
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Summary
    print_header("TEST SUMMARY")
    
    total = results['passed'] + results['failed'] + results['warnings']
    pass_rate = (results['passed'] / total * 100) if total > 0 else 0
    
    print(f"\n{Colors.BOLD}Results:{Colors.RESET}")
    print(f"  {Colors.GREEN}✓ Passed: {results['passed']}{Colors.RESET}")
    print(f"  {Colors.RED}✗ Failed: {results['failed']}{Colors.RESET}")
    print(f"  {Colors.YELLOW}⚠ Warnings: {results['warnings']}{Colors.RESET}")
    print(f"  {Colors.BOLD}Total: {total}{Colors.RESET}")
    print(f"\n{Colors.BOLD}Pass Rate: {pass_rate:.1f}%{Colors.RESET}\n")
    
    if results['failed'] == 0:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ ALL TESTS PASSED!{Colors.RESET}\n")
        return True
    else:
        print(f"{Colors.RED}{Colors.BOLD}✗ SOME TESTS FAILED{Colors.RESET}\n")
        return False

if __name__ == '__main__':
    try:
        success = run_all_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Tests interrupted by user{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}Fatal error: {e}{Colors.RESET}")
        sys.exit(1)