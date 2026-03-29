import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from backend.src.config import get_database_url

# ---------------------------------------------------
# Logger Setup
# ---------------------------------------------------
logger = logging.getLogger("DatabaseConnector")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

formatter = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
console_handler.setFormatter(formatter)

if not logger.hasHandlers():
    logger.addHandler(console_handler)


class DatabaseConnector:
    """
    Singleton class to manage the connection to the PostgreSQL database using SQLAlchemy.
    """

    _instance = None

    @staticmethod
    def _ensure_schema_compatibility(engine) -> None:
        """Apply lightweight additive migrations required by the current codebase."""
        try:
            inspector = inspect(engine)
            if "stock_analysis_results" not in inspector.get_table_names():
                return

            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE stock_analysis_results "
                        "ADD COLUMN IF NOT EXISTS model_used TEXT"
                    )
                )
        except Exception:
            logger.exception("💥 Failed to apply schema compatibility checks.")
            raise

    def __new__(cls):
        if cls._instance is None:
            db_url = get_database_url()
            if not db_url:
                logger.error("❌ DATABASE_URL is not set in the environment variables.")
                raise ValueError("DATABASE_URL is not set in the environment variables.")

            logger.info("🔄 Creating new database engine instance...")
            cls._instance = super(DatabaseConnector, cls).__new__(cls)
            try:
                cls._instance.engine = create_engine(db_url)
                cls._ensure_schema_compatibility(cls._instance.engine)
                cls._instance.SessionLocal = sessionmaker(
                    autocommit=False, autoflush=False, bind=cls._instance.engine
                )
                logger.info("✅ Database engine initialized successfully.")
            except Exception as e:
                logger.exception("💥 Failed to initialize the database engine.")
                raise e
        return cls._instance

    def get_session(self):
        return self._instance.SessionLocal()

    def get_engine(self):
        return self._instance.engine


# Example of how to use it (for testing the file directly)
if __name__ == "__main__":
    try:
        db = DatabaseConnector()
        engine = db.get_engine()
        with engine.connect() as connection:
            logger.info("🎉 Successfully connected to the local PostgreSQL database!")
    except Exception as e:
        logger.exception("🚨 Failed to connect to the database.")
