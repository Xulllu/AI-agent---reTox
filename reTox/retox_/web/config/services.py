from dataclasses import dataclass
import os

from infrastructure.database import Database

from application.services.queue_service import QueueService
from application.services.review_service import ReviewService
from application.services.profile_service import ProfileService
from application.services.training_service import TrainingService
from application.services.dashboard_service import DashboardService
from application.services.advanced_training_service import AdvancedTrainingService
from application.services.agent_service import AgentService
from application.services.moderation_service import ModerationService
from application.services.reddit_scrape_service import RedditScrapeService
from application.services.user_service import UserService
from application.services.toxicity_meter_service import ToxicityMeterService
from application.services.admin_training_service import AdminTrainingService

from application.runners.classification_runner import ClassificationRunner
from application.runners.learning_runner import LearningRunner
from application.runners.collection_runner import CollectionRunner


@dataclass
class AppServices:
    db: Database
    queue_service: QueueService
    review_service: ReviewService
    profile_service: ProfileService
    training_service: TrainingService
    dashboard_service: DashboardService
    advanced_training_service: AdvancedTrainingService
    agent_service: AgentService
    moderation_service: ModerationService
    reddit_scrape_service: RedditScrapeService
    user_service: UserService
    toxicity_meter_service: ToxicityMeterService
    admin_training_service: AdminTrainingService
    classification_runner: ClassificationRunner
    learning_runner: LearningRunner
    collection_runner: CollectionRunner


def build_services() -> AppServices:
    db = Database(db_path=os.getenv("DATABASE_PATH", "retox.db"))

    queue_service = QueueService(db)
    review_service = ReviewService(db)
    profile_service = ProfileService(db)
    training_service = TrainingService(db)
    dashboard_service = DashboardService(db)
    advanced_training_service = AdvancedTrainingService(db)
    agent_service = AgentService(db)
    moderation_service = ModerationService(db, review_service)
    reddit_scrape_service = RedditScrapeService(db, queue_service)
    user_service = UserService(db)
    toxicity_meter_service = ToxicityMeterService(db)
    admin_training_service = AdminTrainingService(db, advanced_training_service)

    classification_runner = ClassificationRunner(db)
    learning_runner = LearningRunner(db)
    collection_runner = CollectionRunner(db)

    return AppServices(
        db=db,
        queue_service=queue_service,
        review_service=review_service,
        profile_service=profile_service,
        training_service=training_service,
        dashboard_service=dashboard_service,
        advanced_training_service=advanced_training_service,
        agent_service=agent_service,
        moderation_service=moderation_service,
        reddit_scrape_service=reddit_scrape_service,
        user_service=user_service,
        toxicity_meter_service=toxicity_meter_service,
        admin_training_service=admin_training_service,
        classification_runner=classification_runner,
        learning_runner=learning_runner,
        collection_runner=collection_runner,
    )