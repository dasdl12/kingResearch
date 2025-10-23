#!/usr/bin/env python3
"""
Initialize Railway PostgreSQL database with required tables.
This script will be run automatically on first deployment.
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def init_database():
    """Initialize database with all required tables."""
    db_url = os.getenv("LANGGRAPH_CHECKPOINT_DB_URL")
    
    if not db_url:
        logger.error("❌ LANGGRAPH_CHECKPOINT_DB_URL environment variable not set")
        sys.exit(1)
    
    if not db_url.startswith("postgresql://"):
        logger.error("❌ Only PostgreSQL is supported for Railway deployment")
        sys.exit(1)
    
    logger.info("🔄 Connecting to Railway PostgreSQL database...")
    logger.info(f"📍 Database: {db_url.split('@')[1] if '@' in db_url else 'unknown'}")
    
    try:
        import psycopg
        
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                logger.info("✅ Database connection successful")
                
                # Check if tables already exist
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name IN ('users', 'research_replays')
                """)
                existing_tables = [row[0] for row in cur.fetchall()]
                
                if 'users' in existing_tables and 'research_replays' in existing_tables:
                    logger.info("✅ Database tables already exist, skipping initialization")
                    return
                
                logger.info("📝 Creating database tables...")
                
                # Read and execute migration files
                migrations_dir = Path(__file__).parent.parent / "migrations"
                
                if not migrations_dir.exists():
                    logger.error(f"❌ Migrations directory not found: {migrations_dir}")
                    sys.exit(1)
                
                migration_files = sorted(migrations_dir.glob("*.sql"))
                
                if not migration_files:
                    logger.error("❌ No migration files found")
                    sys.exit(1)
                
                for migration_file in migration_files:
                    logger.info(f"📄 Executing migration: {migration_file.name}")
                    
                    with open(migration_file, 'r', encoding='utf-8') as f:
                        sql = f.read()
                        
                    # Execute the migration
                    cur.execute(sql)
                    conn.commit()
                    
                    logger.info(f"✅ Migration {migration_file.name} completed")
                
                # Verify tables were created
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
                
                tables = [row[0] for row in cur.fetchall()]
                logger.info(f"📊 Database tables: {', '.join(tables)}")
                
                logger.info("✅ Database initialization completed successfully!")
                logger.info("🎉 DeerFlow is ready to use on Railway!")
                
    except ImportError:
        logger.error("❌ psycopg package not installed. Run: pip install psycopg[binary]")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    logger.info("🚀 Starting Railway database initialization...")
    init_database()

