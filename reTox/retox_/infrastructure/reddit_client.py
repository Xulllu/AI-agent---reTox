# infrastructure/reddit_client.py (FIXED - Using requests JSON API, no auth needed)

import requests
import re
import json
from typing import List, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class RedditClient:
    def __init__(self):
        """
        Initialize Reddit client using requests library
        No authentication needed - uses public Reddit JSON API
        
        Primer:
            reddit_client = RedditClient()
            comments = reddit_client.collect_comments(
                url='https://www.reddit.com/r/news/comments/1q7i7oc/...',
                limit=100
            )
        """
        self.base_url = "https://www.reddit.com"
        self.headers = {
            'User-Agent': 'ReTox-ToxicityDetector/1.0 (+https://github.com/retox)'
        }
        logger.info("Reddit client initialized (requests-based, no auth needed)")
    
    def extract_post_info(self, url: str) -> Dict:
        """
        Extract subreddit and submission ID from Reddit URL
        
        Supports:
        - https://www.reddit.com/r/news/comments/1q7i7oc/fbi_takes_over_case...
        - https://reddit.com/r/news/comments/1q7i7oc/
        - /r/news/comments/1q7i7oc/
        """
        # Try different URL patterns (handles both www and non-www)
        patterns = [
            r'reddit\.com/r/([a-z0-9_]+)/comments/([a-z0-9]+)',
            r'/r/([a-z0-9_]+)/comments/([a-z0-9]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return {
                    'subreddit': match.group(1),
                    'submission_id': match.group(2)
                }
        
        logger.error(f"Could not extract post info from URL: {url}")
        raise ValueError(f"Invalid Reddit URL format. Expected: https://reddit.com/r/subreddit/comments/id/")
    
    def collect_comments(self, url: str, limit: int = 100) -> List[Dict]:
        """
        Collect all comments from a Reddit thread using JSON API
        
        Args:
            url: Reddit thread URL
            limit: Maximum number of comments to collect (default: 100)
        
        Returns:
            List of comment dictionaries with fields:
            - id: Comment ID
            - subreddit: Subreddit name
            - author: Username
            - body: Comment text
            - score: Upvote count
            - created_utc: Timestamp
            - permalink: Reddit link
            - parent_id: Parent comment ID
            - is_submission: True if original post
            - has_media: True if contains media links
        """
        try:
            post_info = self.extract_post_info(url)
            subreddit = post_info['subreddit']
            submission_id = post_info['submission_id']
            
            logger.info(f"Fetching submission: {submission_id} from r/{subreddit}")
            
            # Build API URL - Reddit automatically serves JSON at .json endpoint
            api_url = f"{self.base_url}/r/{subreddit}/comments/{submission_id}.json"
            
            logger.debug(f"Making request to: {api_url}")
            
            # Make request to Reddit JSON API
            response = requests.get(api_url, headers=self.headers, timeout=30)
            
            # Handle common HTTP errors
            if response.status_code == 404:
                raise ValueError(f"Post not found (404): https://reddit.com/r/{subreddit}/comments/{submission_id}")
            elif response.status_code == 403:
                raise ValueError(f"Access denied (403): This subreddit or post may be restricted/private")
            elif response.status_code == 429:
                raise ValueError(f"Rate limited (429): Reddit is rate limiting requests. Please try again later.")
            elif response.status_code != 200:
                raise ValueError(f"Reddit API error ({response.status_code}): {response.reason}")
            
            data = response.json()
            
            # Validate response structure
            if not isinstance(data, list) or len(data) < 2:
                raise ValueError("Invalid Reddit API response format")
            
            comments_data = []
            
            # === Parse original post (data[0]) ===
            try:
                post_listing = data[0]['data']['children'][0]['data']
                if post_listing.get('selftext'):  # Skip link-only posts
                    comments_data.append({
                        'id': post_listing['id'],
                        'subreddit': subreddit,
                        'author': post_listing.get('author', '[deleted]'),
                        'body': post_listing['title'] + "\n\n" + post_listing['selftext'],
                        'parent_id': None,
                        'score': post_listing['score'],
                        'created_utc': post_listing['created_utc'],
                        'permalink': f"https://reddit.com{post_listing['permalink']}",
                        'is_submission': True,
                        'has_media': self._detect_media(post_listing['selftext'])
                    })
                    logger.debug(f"Added original post: {post_listing['id']}")
            except Exception as e:
                logger.warning(f"Could not parse original post: {e}")
            
            # === Parse comments (data[1]) ===
            try:
                comments_tree = data[1]['data']['children']
                comment_count = 0
                
                def process_comments(children):
                    """Recursively process comment tree"""
                    nonlocal comment_count
                    
                    for child in children:
                        if comment_count >= limit:
                            return  # Stop if limit reached
                        
                        try:
                            # Only process actual comments (kind='t1')
                            if child['kind'] != 't1':
                                continue
                            
                            comment_data = child['data']
                            
                            # Skip deleted/removed/bot comments
                            author = comment_data.get('author')
                            if author in ['[deleted]', '[removed]', None]:
                                continue
                            
                            body = comment_data.get('body', '').strip()
                            
                            # Skip very short comments
                            if len(body) < 3:
                                continue
                            
                            # Skip moderator distinguished comments (optional)
                            if comment_data.get('distinguished') == 'moderator':
                                continue
                            
                            # Extract parent ID
                            parent_id = None
                            if '_' in comment_data.get('parent_id', ''):
                                parent_id = comment_data['parent_id'].split('_')[1]
                            
                            has_media = self._detect_media(body)
                            
                            comments_data.append({
                                'id': comment_data['id'],
                                'subreddit': subreddit,
                                'author': author,
                                'body': body,
                                'parent_id': parent_id,
                                'score': comment_data['score'],
                                'created_utc': comment_data['created_utc'],
                                'permalink': f"https://reddit.com{comment_data['permalink']}",
                                'is_submission': False,
                                'has_media': has_media
                            })
                            
                            comment_count += 1
                            logger.debug(f"Added comment {comment_count}/{limit}: {comment_data['id']}")
                            
                            # Process nested replies recursively
                            replies = comment_data.get('replies')
                            if replies and isinstance(replies, dict):
                                nested_children = replies.get('data', {}).get('children', [])
                                if nested_children:
                                    process_comments(nested_children)
                        
                        except Exception as e:
                            logger.debug(f"Skipped comment due to error: {e}")
                            continue
                
                # Start processing comment tree
                process_comments(comments_tree)
            
            except Exception as e:
                logger.warning(f"Error parsing comments section: {e}")
            
            logger.info(f"✅ Successfully collected {len(comments_data)} comments from r/{subreddit}")
            return comments_data
        
        except requests.exceptions.Timeout:
            logger.error("Request timeout - Reddit took too long to respond")
            raise ValueError("⏱️ Reddit API timeout - please try again in a moment")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            raise ValueError("🔌 Could not connect to Reddit - check your internet connection")
        except ValueError:
            # Re-raise ValueError as-is (our custom error messages)
            raise
        except Exception as e:
            logger.error(f"Unexpected error collecting comments: {e}")
            raise ValueError(f"❌ Error: {str(e)}")
    
    def _detect_media(self, text: str) -> bool:
        """
        Detect if comment/post contains media links
        
        Args:
            text: Text content to analyze
        
        Returns:
            True if media indicators found, False otherwise
        """
        media_indicators = [
            'imgur.com',
            'i.redd.it',
            'gfycat.com',
            'giphy.com',
            'youtube.com',
            'youtu.be',
            'v.redd.it',
            '[gif]',
            '[img]',
            '.gif',
            '.jpg',
            '.jpeg',
            '.png',
            '.mp4',
            '.webm',
            '.mov'
        ]
        
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in media_indicators)