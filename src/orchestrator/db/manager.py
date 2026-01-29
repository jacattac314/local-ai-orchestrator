"""Database connection manager with SQLite WAL mode support."""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from orchestrator.db.base import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and sessions with SQLite optimizations."""

    def __init__(
        self,
        database_url: str = "sqlite:///data/orchestrator.db",
        echo: bool = False,
    ) -> None:
        """
        Initialize the database manager.

        Args:
            database_url: SQLAlchemy database URL
            echo: Enable SQL echo logging
        """
        self._database_url = database_url
        self._echo = echo
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def engine(self) -> Engine:
        """Get or create the database engine."""
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    def _create_engine(self) -> Engine:
        """Create a new SQLAlchemy engine with SQLite optimizations."""
        # Ensure data directory exists for SQLite
        if self._database_url.startswith("sqlite:///"):
            db_path = self._database_url.replace("sqlite:///", "")
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        engine = create_engine(
            self._database_url,
            echo=self._echo,
            pool_pre_ping=True,  # Enable connection health checks
        )

        # Configure SQLite pragmas for performance
        if self._database_url.startswith("sqlite"):
            self._configure_sqlite_pragmas(engine)

        return engine

    def _configure_sqlite_pragmas(self, engine: Engine) -> None:
        """Configure SQLite-specific pragmas for performance."""

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore
            cursor = dbapi_connection.cursor()
            # Enable WAL mode for better concurrency
            cursor.execute("PRAGMA journal_mode=WAL")
            # Enable foreign key enforcement
            cursor.execute("PRAGMA foreign_keys=ON")
            # Faster synchronous mode (still safe with WAL)
            cursor.execute("PRAGMA synchronous=NORMAL")
            # Memory-mapped I/O for better read performance
            cursor.execute("PRAGMA mmap_size=268435456")  # 256MB
            # Increase cache size
            cursor.execute("PRAGMA cache_size=-64000")  # 64MB
            cursor.close()

        logger.info("SQLite pragmas configured for optimal performance")

    @property
    def session_factory(self) -> sessionmaker[Session]:
        """Get or create the session factory."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
            )
        return self._session_factory

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Get a database session with automatic cleanup.

        Yields:
            SQLAlchemy Session instance

        Usage:
            with db_manager.get_session() as session:
                session.query(Model).all()
        """
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def init_db(self) -> None:
        """Create all tables if they don't exist."""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created/verified")

    def drop_db(self) -> None:
        """Drop all tables. Use with caution!"""
        Base.metadata.drop_all(bind=self.engine)
        logger.warning("All database tables dropped")

    def health_check(self) -> bool:
        """
        Check if the database connection is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    def vacuum(self) -> None:
        """Run VACUUM to optimize the SQLite database."""
        if not self._database_url.startswith("sqlite"):
            logger.warning("VACUUM is only applicable to SQLite databases")
            return

        with self.engine.connect() as conn:
            conn.execute(text("VACUUM"))
            conn.commit()
        logger.info("Database vacuum completed")

    def close(self) -> None:
        """Close the database engine and release resources."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database connection closed")
