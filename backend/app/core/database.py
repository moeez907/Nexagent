"""
Database connection, session management, and SQLAlchemy ORM models.
PostgreSQL is required for persistent application storage.
"""
import os
import subprocess
import uuid
import asyncio
from datetime import datetime
from typing import AsyncGenerator
import logging

from sqlalchemy import String, DateTime, Text, JSON, Integer, Boolean, ForeignKey, LargeBinary
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import settings
from app.core.state_machine import TaskStatus, HumanInterventionStatus, HumanInterventionType

logger = logging.getLogger("web_agent.database")


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    auth_sessions: Mapped[list["AuthSessionModel"]] = relationship("AuthSessionModel", back_populates="user", cascade="all, delete-orphan")
    tasks: Mapped[list["TaskModel"]] = relationship("TaskModel", back_populates="user")
    conversations: Mapped[list["ConversationModel"]] = relationship("ConversationModel", back_populates="user")


class AuthSessionModel(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="auth_sessions")


class ConversationModel(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New task")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="conversations")
    messages: Mapped[list["ConversationMessageModel"]] = relationship("ConversationMessageModel", back_populates="conversation", cascade="all, delete-orphan")
    tasks: Mapped[list["TaskModel"]] = relationship("TaskModel", back_populates="conversation")


class ConversationMessageModel(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped["ConversationModel"] = relationship("ConversationModel", back_populates="messages")


class TaskModel(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default=TaskStatus.CREATED.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    step_count: Mapped[int] = mapped_column(Integer, default=0)
    current_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("conversations.id"), nullable=True, index=True)
    guest_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    parent_task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=True, index=True)

    user: Mapped["UserModel | None"] = relationship("UserModel", back_populates="tasks")
    conversation: Mapped["ConversationModel | None"] = relationship("ConversationModel", back_populates="tasks")
    checkpoint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    file_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    session: Mapped["BrowserSessionModel"] = relationship("BrowserSessionModel", back_populates="task", uselist=False, cascade="all, delete-orphan")
    events: Mapped[list["TaskEventModel"]] = relationship("TaskEventModel", back_populates="task", cascade="all, delete-orphan")
    result: Mapped["TaskResultModel | None"] = relationship("TaskResultModel", back_populates="task", uselist=False, cascade="all, delete-orphan")
    interventions: Mapped[list["HumanInterventionModel"]] = relationship("HumanInterventionModel", back_populates="task", cascade="all, delete-orphan")


class BrowserSessionModel(Base):
    __tablename__ = "browser_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), unique=True, nullable=False)
    session_dir: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped["TaskModel"] = relationship("TaskModel", back_populates="session")


class TaskEventModel(Base):
    __tablename__ = "task_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generated_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped["TaskModel"] = relationship("TaskModel", back_populates="events")


class TaskResultModel(Base):
    __tablename__ = "task_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), unique=True, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_time_seconds: Mapped[float] = mapped_column(JSON, default=0.0)
    pages_visited: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped["TaskModel"] = relationship("TaskModel", back_populates="result")


class HumanInterventionModel(Base):
    __tablename__ = "human_interventions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    intervention_type: Mapped[str] = mapped_column(String(50), default=HumanInterventionType.CAPTCHA.value)
    status: Mapped[str] = mapped_column(String(50), default=HumanInterventionStatus.PENDING.value)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    action_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    user_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    task: Mapped["TaskModel"] = relationship("TaskModel", back_populates="interventions")


# PostgreSQL is the only supported application database.
engine = create_async_engine(
    settings.POSTGRES_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"timeout": settings.POSTGRES_CONNECT_TIMEOUT_SECONDS},
)
_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def async_session_factory() -> AsyncSession:
    """Dynamically returns an AsyncSession bound to the active database engine."""
    return _session_factory()


async def _create_postgres_db_if_missing():
    try:
        from urllib.parse import urlparse, urlunparse
        from sqlalchemy import text
        parsed = urlparse(settings.POSTGRES_URL)
        default_db_url = urlunparse((parsed.scheme, parsed.netloc, '/postgres', parsed.params, parsed.query, parsed.fragment))
        admin_engine = create_async_engine(default_db_url, isolation_level="AUTOCOMMIT", echo=False)
        async with admin_engine.connect() as conn:
            await conn.execute(text("CREATE DATABASE web_agent"))
        await admin_engine.dispose()
        logger.info("Auto-created PostgreSQL database 'web_agent' successfully.")
        return True
    except Exception as ex:
        logger.debug(f"Could not auto-create PostgreSQL DB: {ex}")
        return False


def _start_postgres_if_needed() -> bool:
    if not settings.POSTGRES_AUTO_START:
        return False
    data_dir = os.path.abspath(settings.POSTGRES_DATA_DIR)
    ctl_path = settings.POSTGRES_CTL_PATH
    log_path = os.path.abspath(settings.POSTGRES_LOG_PATH)
    if not os.path.exists(ctl_path) or not os.path.exists(data_dir):
        logger.error("PostgreSQL auto-start paths unavailable: ctl=%s data=%s", ctl_path, data_dir)
        return False
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    creationflags = 0
    startupinfo = None
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    try:
        result = subprocess.run(
            [ctl_path, "start", "-D", data_dir, "-l", log_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
    except subprocess.TimeoutExpired:
        logger.error("PostgreSQL auto-start timed out after 60 seconds.")
        return False
    if result.returncode == 0:
        logger.info("PostgreSQL server started automatically.")
        return True
    logger.warning("PostgreSQL auto-start failed with exit code %s.", result.returncode)
    return False


async def _wait_for_postgres(max_attempts: int = 12, delay_seconds: float = 1.0) -> bool:
    """Wait briefly for PostgreSQL to accept connections after an automatic start."""
    for attempt in range(max_attempts):
        try:
            async with engine.connect():
                return True
        except Exception as exc:
            if attempt == max_attempts - 1:
                logger.error("PostgreSQL did not become ready after %s attempts: %s", max_attempts, exc)
                return False
            await asyncio.sleep(delay_seconds)
    return False


async def _ensure_schema_compatibility():
    """Apply small additive changes needed by existing development databases."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            await conn.execute(text("ALTER TABLE task_events ADD COLUMN IF NOT EXISTS screenshot_path TEXT"))
            await conn.execute(text("ALTER TABLE task_events ADD COLUMN IF NOT EXISTS screenshot_data BYTEA"))
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS user_id VARCHAR(36)"))
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS conversation_id VARCHAR(36)"))
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS checkpoint JSON"))
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS file_context TEXT"))
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS guest_id VARCHAR(64)"))
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS parent_task_id VARCHAR(36)"))
            await conn.execute(text("ALTER TABLE human_interventions ADD COLUMN IF NOT EXISTS action_payload JSONB"))

async def init_db():
    """Create all tables asynchronously; fail startup when PostgreSQL is unavailable."""
    global engine, _session_factory
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _ensure_schema_compatibility()
        logger.info("Connected to PostgreSQL database successfully.")
    except Exception as e:
        err_str = str(e).lower()
        if "connection refused" in err_str or "winerror 1225" in err_str:
            if await asyncio.to_thread(_start_postgres_if_needed):
                if await _wait_for_postgres():
                    try:
                        async with engine.begin() as conn:
                            await conn.run_sync(Base.metadata.create_all)
                        await _ensure_schema_compatibility()
                        logger.info("Connected to PostgreSQL after automatic server start.")
                        return
                    except Exception as retry_error:
                        logger.error("PostgreSQL retry after auto-start failed: %s", retry_error)
        if "does not exist" in err_str or "invalidcatalogname" in err_str:
            created = await _create_postgres_db_if_missing()
            if created:
                engine = create_async_engine(
                    settings.POSTGRES_URL,
                    echo=False,
                    pool_pre_ping=True,
                    connect_args={"timeout": settings.POSTGRES_CONNECT_TIMEOUT_SECONDS},
                )
                _session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                await _ensure_schema_compatibility()
                logger.info("Connected to newly created PostgreSQL database successfully.")
                return

        logger.error("PostgreSQL is required but unavailable: %s", e)
        raise RuntimeError("PostgreSQL is required to start the application.") from e


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining async DB session."""
    async with async_session_factory() as session:
        yield session


