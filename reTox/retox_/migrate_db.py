# migrate_db.py - Add missing columns to model_versions table

import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from infrastructure.database import Database
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_model_versions_table():
    """Add missing columns to model_versions table"""
    db = Database()
    conn = db._get_connection()
    cursor = conn.cursor()
    
    logger.info("Checking model_versions table structure...")
    
    try:
        # Get existing columns
        cursor.execute("PRAGMA table_info(model_versions)")
        columns = {row[1] for row in cursor.fetchall()}
        
        logger.info(f"Existing columns: {columns}")
        
        # Add missing columns if they don't exist
        if 'base_model' not in columns:
            logger.info("Adding 'base_model' column...")
            cursor.execute("ALTER TABLE model_versions ADD COLUMN base_model TEXT DEFAULT 'detoxify-original'")
            logger.info("✓ Added base_model")
        
        if 'notes' not in columns:
            logger.info("Adding 'notes' column...")
            cursor.execute("ALTER TABLE model_versions ADD COLUMN notes TEXT DEFAULT ''")
            logger.info("✓ Added notes")
        
        if 'training_date' not in columns:
            logger.info("Adding 'training_date' column...")
            cursor.execute("ALTER TABLE model_versions ADD COLUMN training_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            logger.info("✓ Added training_date")
        
        # Rename old columns if needed
        if 'false_positives_before' in columns and 'false_positives' not in columns:
            logger.info("Renaming false_positives columns...")
            cursor.execute("ALTER TABLE model_versions RENAME COLUMN false_positives_before TO false_positives")
            logger.info("✓ Renamed false_positives_before")
        
        if 'false_negatives_before' in columns and 'false_negatives' not in columns:
            cursor.execute("ALTER TABLE model_versions RENAME COLUMN false_negatives_before TO false_negatives")
            logger.info("✓ Renamed false_negatives_before")
        
        conn.commit()
        logger.info("✅ Migration complete!")
        return True
    
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
    
    finally:
        conn.close()

if __name__ == '__main__':
    success = migrate_model_versions_table()
    sys.exit(0 if success else 1)