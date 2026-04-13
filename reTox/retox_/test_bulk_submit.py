# test_bulk_submit.py (UPDATED)

import requests
import json
import time
from datetime import datetime

API_BASE = "http://localhost:5000"

def submit_comment(external_id, text, subreddit="news"):
    """Submit a comment"""
    payload = {
        "external_id": external_id,  # Use unique ID with timestamp
        "subreddit": subreddit,
        "author": f"user_{external_id}",
        "text": text,
        "reddit_score": 10,
        "reddit_permalink": f"/r/{subreddit}/comments/{external_id}"
    }
    
    response = requests.post(f"{API_BASE}/api/queue/submit", json=payload)
    if response.status_code == 201:
        data = response.json()
        return data['comment_id']
    else:
        print(f"Failed to submit comment {external_id}: {response.text}")
        return None

def submit_review(comment_id, decision="approve"):
    """Submit a review for a comment"""
    payload = {
        "comment_id": comment_id,
        "decision": decision,
        "notes": f"Test review - {decision}"
    }
    
    response = requests.post(f"{API_BASE}/api/reviews", json=payload)
    if response.status_code == 201:
        return True
    else:
        print(f"Failed to review comment {comment_id}: {response.text}")
        return False

def main():
    test_comments = [
        "How retarted are you from 1 to 10",
        "I disagree with this opinion",
        "You are stupid",
        "Great work on the project",
        "Dickhead move",
        "Love this content",
        "Kill yourself",
        "Its shit",
        "Worst thing I've seen",
        "Excellent point",
    ]
    
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    
    print("=" * 60)
    print("BULK SUBMITTING TEST DATA")
    print("=" * 60)
    
    # Submit 50 comments with reviews to trigger retraining
    for i in range(50):
        comment_text = test_comments[i % len(test_comments)]
        
        # Use unique ID with timestamp
        unique_id = f"test_{timestamp}_{i}"
        
        # Submit comment
        comment_id = submit_comment(unique_id, comment_text)
        if not comment_id:
            continue
        
        # Decide decision based on text (toxic vs clean)
        decision = "reject" if any(word in comment_text.lower() for word in ["stupid", "trash", "hate", "worst"]) else "approve"
        
        # Submit review
        submit_review(comment_id, decision)
        
        print(f"[{i+1}/50] Submitted comment {comment_id} with decision: {decision}")
        
        # Small delay to avoid overwhelming the API
        time.sleep(0.1)
    
    print("\n" + "=" * 60)
    print("BULK SUBMISSION COMPLETE")
    print("=" * 60)
    print("\nWait 20 seconds for Learning agent to trigger retraining...")
    print("Then check:")
    print("  - http://localhost:5000/api/training/history")
    print("  - http://localhost:5000/dashboard")

if __name__ == "__main__":
    main()