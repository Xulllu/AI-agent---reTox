from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import logging
from dotenv import load_dotenv


# Load env first
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask APP FIRST
app = Flask(__name__)
CORS(app)

from web.config.services import build_services

services = build_services()

db = services.db
queue_service = services.queue_service
review_service = services.review_service
profile_service = services.profile_service
training_service = services.training_service
dashboard_service = services.dashboard_service
advanced_training_service = services.advanced_training_service
agent_service = services.agent_service
moderation_service = services.moderation_service
reddit_scrape_service = services.reddit_scrape_service
user_service = services.user_service
toxicity_meter_service = services.toxicity_meter_service
admin_training_service = services.admin_training_service

classification_runner = services.classification_runner
learning_runner = services.learning_runner
collection_runner = services.collection_runner


# ===== HEALTH & INFO =====


@app.route('/health', methods=['GET'])
def health():
    payload = agent_service.health_api()
    return jsonify(payload), 200

#Ispravan

@app.route('/info', methods=['GET'])
def info():
    """App info"""
    return jsonify({
        'name': 'ReTox - Context-Aware Toxicity Detection Agent',
        'version': '1.0.0',
        'agents': ['ClassificationRunner', 'LearningRunner', 'CollectionRunner'],
        'description': 'Multi-agent system for Reddit toxicity detection with context awareness'
    }), 200
#Ispravan

@app.route('/api/agents/events', methods=['GET'])
def agent_events():
    limit = request.args.get('limit', 50, type=int)
    events = agent_service.get_recent_events(limit)
    return jsonify({'events': events}), 200
#Ispravan  


@app.route('/', methods=['GET'])
def home():
    """Serve the home landing page"""
    return render_template('home.html')
#Ispravan
# ===== DASHBOARD ENDPOINTS =====

@app.route('/dashboard', methods=['GET'])
def dashboard():
    """Serve the dashboard HTML"""
    return render_template('dashboard.html')
#Ispravan

@app.route('/api/dashboard/stats', methods=['GET'])
def dashboard_stats():
    """GET /api/dashboard/stats - get overall dashboard statistics"""
    try:
        stats = dashboard_service.get_dashboard_stats()
        return jsonify(stats), 200
    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        return jsonify({'error': str(e)}), 400

#Ispravan


@app.route('/api/dashboard/recent-comments', methods=['GET'])
def recent_comments():
    """GET /api/dashboard/recent-comments - get recent comments"""
    try:
        limit_param = request.args.get('limit')  # raw string (ili None)
        comments = dashboard_service.get_recent_comments_api(limit_param)
        return jsonify({'comments': comments}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    
#Ispravan

@app.route('/api/dashboard/collection-jobs', methods=['GET'])
def dashboard_collection_jobs():
    limit_param = request.args.get('limit')  # raw string ili None
    jobs = dashboard_service.get_recent_collection_jobs_api(limit_param)
    return jsonify({'jobs': jobs}), 200

#Ispravan


@app.route('/api/dashboard/collection-jobs/<int:job_id>/comments', methods=['GET'])
def dashboard_collection_job_comments(job_id: int):
    try:
        limit_param = request.args.get('limit')  # raw string ili None
        comments = dashboard_service.get_collection_job_comments_api(job_id, limit_param)
        return jsonify({'comments': comments}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

#Ispravan

@app.route('/api/dashboard/recent-reviews', methods=['GET'])
def dashboard_recent_reviews():
    try:
        limit_param = request.args.get('limit')  # raw string ili None
        reviews = dashboard_service.get_recent_reviews_api(limit_param)
        return jsonify({'reviews': reviews}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

#Ispravan

@app.route('/api/dashboard/subreddit/<subreddit>', methods=['GET'])
def subreddit_stats(subreddit):
    """GET /api/dashboard/subreddit/news - stats for specific subreddit"""
    try:
        stats = dashboard_service.get_subreddit_stats(subreddit)
        if not stats:
            return jsonify({'error': 'Subreddit not found'}), 404
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400
#Ispravan

@app.route('/api/dashboard/agent-stats', methods=['GET'])
def agent_stats():
    """GET /api/dashboard/agent-stats - agent activity statistics"""
    try:
        stats = dashboard_service.get_agent_stats()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

#Ispravan
# ===== REVIEW ENDPOINTS (Moderators submit feedback) =====

@app.route('/api/reviews', methods=['POST'])
def submit_review():
    try:
        data = request.get_json(silent=True) or {}
        review_id = review_service.submit_review_api(data)
        return jsonify({'success': True, 'review_id': review_id, 'message': 'Review saved'}), 201
    except Exception as e:
        logger.error(f"Review submission error: {e}")
        return jsonify({'error': str(e)}), 400

#Ispravan

# ===== PROFILE ENDPOINTS (Subreddit settings) =====

@app.route('/api/profiles/<subreddit>', methods=['GET'])
def get_profile(subreddit):
    """GET /api/profiles/news - get subreddit profile"""
    try:
        payload = profile_service.get_profile_api(subreddit)
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

#Ispravan


@app.route('/api/profiles/<subreddit>/threshold', methods=['PUT'])
def update_threshold(subreddit):
    """PUT /api/profiles/news/threshold - update decision threshold"""
    try:
        data = request.get_json(silent=True) or {}
        payload = profile_service.update_threshold_api(subreddit, data)
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

#Ispravan

@app.route('/api/profiles/<subreddit>/sensitivity', methods=['PUT'])
def update_sensitivity(subreddit):
    """PUT /api/profiles/news/sensitivity - update sensitivity multiplier"""
    try:
        data = request.get_json(silent=True) or {}
        payload = profile_service.update_sensitivity_api(subreddit, data)
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

#Ispravan

# ===== TRAINING ENDPOINTS =====

    
@app.route('/api/training/status', methods=['GET'])
def training_status():
    """GET /api/training/status - check retraining status"""
    try:
        payload = training_service.get_training_status_api()
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

#Ispravan

@app.route('/api/training/disable', methods=['POST'])
def disable_training():
    """POST /api/training/disable - disable automatic retraining"""
    try:
        payload = training_service.set_retraining_enabled_api(False)
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400
#Ispravan

@app.route('/api/training/enable', methods=['POST'])
def enable_training():
    """POST /api/training/enable - enable automatic retraining"""
    try:
        payload = training_service.set_retraining_enabled_api(True)
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400
#Ispravan


@app.route('/api/training/history', methods=['GET'])
def training_history():
    """GET /api/training/history - get model training history"""
    try:
        payload = advanced_training_service.get_model_history_api()
        return jsonify(payload), 200
    except Exception as e:
        logger.error(f"Training history error: {e}")
        return jsonify({'error': str(e)}), 400
    
#Ispravan

@app.route('/api/training/performance', methods=['GET'])
def training_performance():
    """GET /api/training/performance - get current model performance metrics"""
    try:
        payload = advanced_training_service.analyze_model_performance_api()
        return jsonify(payload), 200
    except Exception as e:
        logger.error(f"Training performance error: {e}")
        return jsonify({'error': str(e)}), 400

# ===== QUEUE ENDPOINTS =====

@app.route('/api/queue/submit', methods=['POST'])
def submit_comment():
    try:
        data = request.get_json(silent=True) or {}
        payload, status_code = queue_service.submit_comment_api(data)
        return jsonify(payload), status_code
    except Exception as e:
        logger.error(f"Queue submission error: {e}")
        return jsonify({'error': str(e)}), 400

#Ispravan

@app.route('/api/queue/stats', methods=['GET'])
def get_queue_stats():
    """GET /api/queue/stats - get queue statistics"""
    try:
        stats = queue_service.get_queue_stats()
        return jsonify(stats), 200
    except Exception as e:
        logger.error(f"Queue stats error: {e}")
        return jsonify({'error': str(e)}), 400

#Ispravan

# ===== PHASE 5: MODERATION INTERFACE =====

@app.route('/moderation', methods=['GET'])
def moderation_dashboard():
    """Serve the moderation interface"""
    return render_template('moderation.html')
#Ispravan


@app.route('/api/moderation/pending', methods=['GET'])
def get_pending_comments():
    """GET /api/moderation/pending - get pending comments for review"""
    try:
        limit_param = request.args.get('limit')
        offset_param = request.args.get('offset')
        author_param = request.args.get('author')
        subreddit_param = request.args.get('subreddit')

        payload = moderation_service.get_pending_comments_api(
            limit_param, offset_param, author_param, subreddit_param
        )
        return jsonify(payload), 200

    except Exception as e:
        logger.error(f"Pending comments error: {e}")
        return jsonify({'error': str(e)}), 400

#Ispravan


@app.route('/api/moderation/resolve/<int:comment_id>', methods=['POST'])
def resolve_comment(comment_id):
    """POST /api/moderation/resolve/<id> - moderator teaching action"""
    try:
        data = request.get_json() or {}
        payload, status_code = moderation_service.resolve_comment_api(comment_id, data)
        return jsonify(payload), status_code
    except Exception as e:
        logger.error(f"Resolve comment error: {e}")
        return jsonify({'error': str(e)}), 400

#Ispravan

# ===== PHASE 5: REDDIT SCRAPER =====


@app.route('/api/reddit/scrape', methods=['POST'])
def scrape_reddit():
    """POST /api/reddit/scrape - scrape comments from Reddit URL"""
    try:
        data = request.get_json()
        payload, status_code = reddit_scrape_service.scrape_reddit_api(data)
        return jsonify(payload), status_code
    except Exception as e:
        logger.error(f"Reddit scrape error: {e}")
        return jsonify({'error': f'Failed to scrape Reddit: {str(e)}'}), 400

#Ispravan

# ===== PHASE 5: USER PROFILE TRACKING =====


@app.route('/api/users/<author>', methods=['GET'])
def get_user_profile(author):
    """GET /api/users/username - get user toxicity profile"""
    try:
        payload = user_service.get_user_profile_api(author)
        return jsonify(payload), 200
    except Exception as e:
        logger.error(f"User profile error: {e}")
        return jsonify({'error': str(e)}), 400

#Ispravan

# ===== PHASE 5: TOXICITY METER (0-100 scale) =====


@app.route('/api/comments/<int:comment_id>/toxicity', methods=['GET'])
def get_toxicity_meter(comment_id):
    """GET /api/comments/<id>/toxicity - get detailed toxicity meter"""
    try:
        payload, status_code = toxicity_meter_service.get_toxicity_meter_api(comment_id)
        return jsonify(payload), status_code
    except Exception as e:
        logger.error(f"Toxicity meter error: {e}")
        return jsonify({'error': str(e)}), 400

#Ispravan

# ===== PHASE 5: ADMIN CONTROLS =====

@app.route('/admin', methods=['GET'])
def admin_dashboard():
    """Serve admin dashboard"""
    return render_template('admin.html')
#Ispravan


@app.route('/api/admin/training/delete-history', methods=['POST'])
def delete_training_history():
    """POST /api/admin/training/delete-history - delete all training"""
    try:
        payload, status_code = admin_training_service.delete_training_history_api()
        return jsonify(payload), status_code
    except Exception as e:
        logger.error(f"Delete training error: {e}")
        return jsonify({'error': str(e)}), 400

#Ispravan

@app.route('/api/admin/training/manual-train', methods=['POST'])
def manual_train():
    """POST /api/admin/training/manual-train - trigger manual training"""
    try:
        payload, status_code = admin_training_service.manual_train_api()
        return jsonify(payload), status_code
    except Exception as e:
        logger.error(f"Manual training error: {e}")
        return jsonify({'error': str(e)}), 400
    
#Ispravan


@app.route('/api/admin/export-gold-labels', methods=['GET'])
def export_gold_labels():
    """GET /api/admin/export-gold-labels - export gold labels as CSV"""
    try:
        csv_text, status_code, headers = admin_training_service.export_gold_labels_api()
        return csv_text, status_code, headers
    except Exception as e:
        logger.error(f"Export error: {e}")
        return jsonify({'error': str(e)}), 400

#Ispravan


@app.route('/api/profiles/<subreddit>/allowed-terms', methods=['PUT'])
def update_allowed_terms(subreddit):
    """PUT /api/profiles/<subreddit>/allowed-terms - replace allowed terms list"""
    try:
        data = request.get_json(silent=True) or {}
        payload = profile_service.update_allowed_terms_api(subreddit, data)
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ===== ERROR HANDLERS =====

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    logger.info("Starting ReTox API...")
    app.run(host='0.0.0.0', port=5000, debug=False)