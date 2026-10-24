"""
FastAPI REST Routes for Task Management and Human-in-the-Loop Interventions.
"""
import os
import glob
import time
import hashlib
import secrets
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, BackgroundTasks, Response, File, UploadFile, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session, TaskModel, TaskEventModel, TaskResultModel, HumanInterventionModel, BrowserSessionModel, UserModel, AuthSessionModel, ConversationModel, ConversationMessageModel
from app.core.config import settings
from app.auth.service import SESSION_COOKIE, create_session, get_optional_user, get_user_from_token, hash_password, verify_password
from app.core.redis import redis_client
from app.core.state_machine import TaskStatus, HumanInterventionType
from app.task_manager.manager import task_manager
from app.human_loop.controller import human_controller
from app.browser.session_manager import session_manager
from app.browser.observer import observer

logger = logging.getLogger("web_agent.api.routes")
router = APIRouter(prefix="/api")


# Pydantic Schemas
class CreateTaskRequest(BaseModel):
    goal: str = Field(..., description="Natural language goal instructions for the web agent.")
    conversation_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    file_text: Optional[str] = None
    file_name: Optional[str] = None


class HumanResponseRequest(BaseModel):
    approved: bool = Field(..., description="Whether human user approved or resolved intervention.")
    response_data: Optional[dict] = Field(None, description="Optional extra data or text response.")


async def ensure_task_access(task_id: str, db: AsyncSession, user: UserModel | None, guest_id: str | None = None):
    task = await db.get(TaskModel, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    if user:
        if task.user_id and task.user_id != user.id:
            raise HTTPException(status_code=403, detail="Access denied to this task.")
    elif guest_id:
        if task.guest_id and task.guest_id != guest_id:
            raise HTTPException(status_code=403, detail="Access denied to this task.")
    return task


class AuthRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=120)


async def optional_user(
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: AsyncSession = Depends(get_db_session),
):
    return await get_optional_user(db, token)


@router.post("/auth/signup", status_code=201)
async def signup(payload: AuthRequest, response: Response, db: AsyncSession = Depends(get_db_session)):
    email = payload.email.strip().lower()
    name = payload.name.strip() if payload.name and payload.name.strip() else None
    user = UserModel(email=email, name=name, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    token = await create_session(db, user)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=30 * 24 * 60 * 60)
    return {"id": user.id, "email": user.email, "name": user.name}


@router.post("/auth/login")
async def login(payload: AuthRequest, response: Response, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(UserModel).where(UserModel.email == payload.email.strip().lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = await create_session(db, user)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=30 * 24 * 60 * 60)
    return {"id": user.id, "email": user.email, "name": user.name}


@router.post("/auth/logout")
async def logout(response: Response, token: str | None = Cookie(default=None, alias=SESSION_COOKIE), db: AsyncSession = Depends(get_db_session)):
    user_session = None
    if token:
        result = await db.execute(select(AuthSessionModel).where(AuthSessionModel.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        user_session = result.scalar_one_or_none()
    if user_session:
        user_session.revoked_at = datetime.utcnow()
        await db.commit()
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "success"}


@router.get("/auth/me")
async def current_user(token: str | None = Cookie(default=None, alias=SESSION_COOKIE), db: AsyncSession = Depends(get_db_session)):
    user = await get_user_from_token(db, token)
    if not user:
        return None
    return {"id": user.id, "email": user.email, "name": user.name}


@router.post("/auth/guest")
async def create_guest_session(response: Response, guest_id: str | None = Cookie(default=None, alias="awa_guest")):
    guest_id = guest_id or secrets.token_urlsafe(24)
    await redis_client.set_json(
        f"guest:{guest_id}:session",
        {"guest_id": guest_id, "created_at": datetime.utcnow().isoformat(), "messages": [], "tasks": []},
        ttl_seconds=settings.GUEST_SESSION_TTL_SECONDS,
    )
    response.set_cookie("awa_guest", guest_id, httponly=True, samesite="lax", max_age=settings.GUEST_SESSION_TTL_SECONDS)
    return {"guest": True, "guest_id": guest_id}


@router.delete("/auth/guest")
@router.post("/auth/guest/close")
async def close_guest_session(response: Response, guest_id: str | None = Cookie(default=None, alias="awa_guest"), db: AsyncSession = Depends(get_db_session)):
    if guest_id:
        try:
            tasks_res = await db.execute(select(TaskModel).where(TaskModel.guest_id == guest_id))
            tasks = tasks_res.scalars().all()
            for t in tasks:
                try:
                    await session_manager.close_session(t.id)
                except Exception:
                    pass
                await db.delete(t)
            await db.commit()
            await redis_client.delete(f"guest:{guest_id}:session")
        except Exception as e:
            await db.rollback()
            logger.warning(f"Error closing guest session: {e}")
    response.delete_cookie("awa_guest")
    return {"status": "success"}


@router.get("/conversations")
async def list_conversations(db: AsyncSession = Depends(get_db_session), user: UserModel | None = Depends(optional_user)):
    if not user:
        return []
    result = await db.execute(select(ConversationModel).where(ConversationModel.user_id == user.id).order_by(ConversationModel.updated_at.desc()))
    return [{"id": item.id, "title": item.title, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()} for item in result.scalars().all()]


@router.post("/conversations", status_code=201)
async def create_conversation(payload: dict | None = None, db: AsyncSession = Depends(get_db_session), user: UserModel | None = Depends(optional_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Login required to save conversations.")
    title = (payload or {}).get("title", "New task")[:200]
    conversation = ConversationModel(user_id=user.id, title=title or "New task")
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return {"id": conversation.id, "title": conversation.title}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db_session), user: UserModel | None = Depends(optional_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Login required.")
    result = await db.execute(select(ConversationModel).where(ConversationModel.id == conversation_id, ConversationModel.user_id == user.id))
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    messages = await db.execute(select(ConversationMessageModel).where(ConversationMessageModel.conversation_id == conversation_id).order_by(ConversationMessageModel.created_at.asc()))
    return {"id": conversation.id, "title": conversation.title, "messages": [{"role": message.role, "content": message.content, "created_at": message.created_at.isoformat()} for message in messages.scalars().all()]}


@router.post("/tasks", status_code=201)
async def create_and_start_task(
    payload: CreateTaskRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
    user: UserModel | None = Depends(optional_user),
    guest_id: str | None = Cookie(default=None, alias="awa_guest"),
):
    if not payload.goal or not payload.goal.strip():
        raise HTTPException(status_code=400, detail="Task goal cannot be empty.")

    conversation_id = payload.conversation_id
    if user:
        if conversation_id:
            conversation_result = await db.execute(select(ConversationModel).where(ConversationModel.id == conversation_id, ConversationModel.user_id == user.id))
            conversation = conversation_result.scalar_one_or_none()
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found.")
        else:
            conversation = ConversationModel(user_id=user.id, title=payload.goal.strip()[:200])
            db.add(conversation)
            await db.flush()
            conversation_id = conversation.id
        db.add(ConversationMessageModel(conversation_id=conversation_id, role="user", content=payload.goal.strip()))
        await db.commit()

    file_context = (payload.file_text or "").strip() or None
    task_id = await task_manager.create_task(
        payload.goal.strip(),
        user_id=user.id if user else None,
        conversation_id=conversation_id,
        guest_id=guest_id if not user else None,
        file_context=file_context,
        parent_task_id=payload.parent_task_id,
    )
    # Start task autonomously in background task
    task_manager.start_task(task_id, payload.goal.strip(), file_context=file_context, parent_task_id=payload.parent_task_id)

    return {
        "task_id": task_id,
        "goal": payload.goal,
        "status": TaskStatus.CREATED.value,
        "message": "Task created and execution loop started.",
        "has_file_context": bool(file_context),
    }


@router.post("/tasks/upload", status_code=201)
async def create_and_start_task_with_upload(
    goal: str = Form(...),
    conversation_id: Optional[str] = Form(None),
    parent_task_id: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db_session),
    user: UserModel | None = Depends(optional_user),
    guest_id: str | None = Cookie(default=None, alias="awa_guest"),
):
    if not goal or not goal.strip():
        raise HTTPException(status_code=400, detail="Task goal cannot be empty.")

    file_context = None
    if file:
        filename = file.filename or ""
        if not filename.lower().endswith(".txt"):
            raise HTTPException(status_code=400, detail="Only .txt text files are supported.")
        content_bytes = await file.read()
        try:
            file_context = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            file_context = content_bytes.decode("latin-1", errors="replace")

    if user:
        if conversation_id:
            conversation_result = await db.execute(select(ConversationModel).where(ConversationModel.id == conversation_id, ConversationModel.user_id == user.id))
            conversation = conversation_result.scalar_one_or_none()
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found.")
        else:
            conversation = ConversationModel(user_id=user.id, title=goal.strip()[:200])
            db.add(conversation)
            await db.flush()
            conversation_id = conversation.id
        db.add(ConversationMessageModel(conversation_id=conversation_id, role="user", content=goal.strip()))
        await db.commit()

    task_id = await task_manager.create_task(
        goal.strip(),
        user_id=user.id if user else None,
        conversation_id=conversation_id,
        guest_id=guest_id if not user else None,
        file_context=file_context,
        parent_task_id=parent_task_id,
    )
    task_manager.start_task(task_id, goal.strip(), file_context=file_context, parent_task_id=parent_task_id)

    return {
        "task_id": task_id,
        "goal": goal,
        "status": TaskStatus.CREATED.value,
        "message": "Task created and execution loop started.",
        "has_file_context": bool(file_context),
    }


@router.get("/tasks")
async def list_tasks(limit: int = 30, db: AsyncSession = Depends(get_db_session), user: UserModel | None = Depends(optional_user), guest_id: str | None = Cookie(default=None, alias="awa_guest")):
    stmt = select(TaskModel).order_by(TaskModel.created_at.asc())
    if user:
        stmt = stmt.where(TaskModel.user_id == user.id)
    else:
        stmt = stmt.where(TaskModel.guest_id == guest_id) if guest_id else stmt.where(TaskModel.id == "")
    res = await db.execute(stmt)
    all_tasks = res.scalars().all()

    # Group tasks by root session so continuation turns do not create extra sessions on sidebar
    task_map = {t.id: t for t in all_tasks}

    def find_root(t):
        curr = t
        visited = set()
        while curr.parent_task_id and curr.parent_task_id in task_map and curr.id not in visited:
            visited.add(curr.id)
            curr = task_map[curr.parent_task_id]
        return curr

    sessions_dict = {}
    for t in all_tasks:
        root = find_root(t)
        if root.id not in sessions_dict:
            sessions_dict[root.id] = {
                "root": root,
                "latest": root,
                "task_ids": [root.id]
            }
        else:
            sessions_dict[root.id]["task_ids"].append(t.id)
            if t.created_at >= sessions_dict[root.id]["latest"].created_at:
                sessions_dict[root.id]["latest"] = t

    # Sort sessions by latest activity descending
    session_list = sorted(
        sessions_dict.values(),
        key=lambda s: s["latest"].updated_at or s["latest"].created_at,
        reverse=True
    )[:limit]

    return [
        {
            "id": s["root"].id,
            "session_id": s["root"].id,
            "active_task_id": s["latest"].id,
            "session_task_ids": s["task_ids"],
            "goal": s["root"].goal,
            "latest_goal": s["latest"].goal,
            "status": s["latest"].status,
            "current_url": s["latest"].current_url or s["root"].current_url,
            "created_at": (s["root"].created_at.isoformat() + "Z") if s["root"].created_at else None,
            "updated_at": ((s["latest"].updated_at or s["latest"].created_at).isoformat() + "Z") if (s["latest"].updated_at or s["latest"].created_at) else None,
            "completed_at": (s["latest"].completed_at.isoformat() + "Z") if s["latest"].completed_at else None,
        }
        for s in session_list
    ]


@router.delete("/tasks")
async def clear_all_tasks_history(db: AsyncSession = Depends(get_db_session)):
    """
    Deletes all task history records, events, results, interventions, and sessions from PostgreSQL database.
    """
    try:
        await db.execute(delete(TaskEventModel))
        await db.execute(delete(TaskResultModel))
        await db.execute(delete(HumanInterventionModel))
        await db.execute(delete(BrowserSessionModel))
        await db.execute(delete(TaskModel))
        await db.commit()

        # Reset in-memory active task manager states and active browser sessions
        task_manager.active_tasks.clear()
        task_manager.paused_tasks.clear()
        await session_manager.shutdown()

        return {
            "status": "success",
            "message": "All task history deleted successfully from database."
        }
    except Exception as e:
        logger.error(f"Error clearing task history: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to clear task history: {str(e)}")


@router.delete("/tasks/{task_id}")
async def delete_single_task(task_id: str, db: AsyncSession = Depends(get_db_session)):
    """
    Deletes a session task and all related continuation tasks, events, results, and browser sessions.
    """
    try:
        # Collect all task IDs in this thread/session
        to_delete = {task_id}
        changed = True
        while changed:
            res = await db.execute(select(TaskModel.id).where(TaskModel.parent_task_id.in_(list(to_delete))))
            child_ids = set(res.scalars().all()) - to_delete
            if child_ids:
                to_delete.update(child_ids)
            else:
                changed = False

        for tid in to_delete:
            await session_manager.close_session(tid)
            task_manager.active_tasks.pop(tid, None)
            task_manager.paused_tasks.discard(tid)

        await db.execute(delete(TaskEventModel).where(TaskEventModel.task_id.in_(list(to_delete))))
        await db.execute(delete(TaskResultModel).where(TaskResultModel.task_id.in_(list(to_delete))))
        await db.execute(delete(HumanInterventionModel).where(HumanInterventionModel.task_id.in_(list(to_delete))))
        await db.execute(delete(BrowserSessionModel).where(BrowserSessionModel.task_id.in_(list(to_delete))))
        await db.execute(delete(TaskModel).where(TaskModel.id.in_(list(to_delete))))
        await db.commit()
        return {"status": "success", "message": f"Task session {task_id} and related continuation tasks deleted successfully."}
    except Exception as e:
        logger.error(f"Error deleting task {task_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete task: {str(e)}")


@router.get("/tasks/{task_id}")

async def get_task_details(task_id: str, db: AsyncSession = Depends(get_db_session), user: UserModel | None = Depends(optional_user), guest_id: str | None = Cookie(default=None, alias="awa_guest")):
    task = await db.get(TaskModel, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    if (user and task.user_id != user.id) or (not user and task.guest_id != guest_id):
        raise HTTPException(status_code=404, detail="Task not found.")

    # Events query
    evt_stmt = select(TaskEventModel).where(TaskEventModel.task_id == task_id).order_by(TaskEventModel.step.asc())
    evt_res = await db.execute(evt_stmt)
    events = evt_res.scalars().all()

    # Result query
    res_stmt = select(TaskResultModel).where(TaskResultModel.task_id == task_id)
    res_res = await db.execute(res_stmt)
    result = res_res.scalar_one_or_none()

    # Pending intervention check
    pending_intervention = human_controller.get_pending_intervention(task_id)
    if not pending_intervention:
        intervention_stmt = select(HumanInterventionModel).where(
            HumanInterventionModel.task_id == task_id,
            HumanInterventionModel.status == "PENDING",
        ).order_by(HumanInterventionModel.created_at.desc())
        intervention_res = await db.execute(intervention_stmt)
        stored_intervention = intervention_res.scalars().first()
        if stored_intervention:
            pending_intervention = {
                "id": stored_intervention.id,
                "task_id": stored_intervention.task_id,
                "intervention_type": stored_intervention.intervention_type,
                "status": stored_intervention.status,
                "prompt": stored_intervention.prompt,
                "action_payload": stored_intervention.action_payload or {},
                "created_at": stored_intervention.created_at.isoformat() if stored_intervention.created_at else None,
            }
    if pending_intervention:
        action_payload = pending_intervention.get("action_payload") or {}
        pending_intervention = {
            **pending_intervention,
            "fields": action_payload.get("fields") or [],
            "active_field": action_payload.get("active_field") or {},
            "context": action_payload.get("context") or {},
            "suggested_value": action_payload.get("suggested_value") or "",
            "upload_mode": action_payload.get("upload_mode") or "file",
        }

    return {
        "id": task.id,
        "goal": task.goal,
        "status": task.status,
        "current_url": task.current_url,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "events": [
            {
                "step": e.step,
                "type": e.event_type,
                "intent": e.intent,
                "code": e.generated_code,
                "url": e.url,
                "screenshot_path": e.screenshot_path,
                "success": e.success,
                "error": e.error,
                "timestamp": e.timestamp.isoformat()
            }
            for e in events
        ],
        "result": {
            "success": result.success,
            "summary": result.summary,
            "extracted_data": result.data,
            "reason": result.reason,
            "execution_time_seconds": result.execution_time_seconds,
            "pages_visited": result.pages_visited
        } if result else None,
        "pending_intervention": pending_intervention
    }


@router.post("/tasks/{task_id}/resume")
@router.post("/tasks/{task_id}/approve")
async def resume_human_intervention(
    task_id: str,
    payload: HumanResponseRequest,
    db: AsyncSession = Depends(get_db_session),
    user: UserModel | None = Depends(optional_user),
    guest_id: str | None = Cookie(default=None, alias="awa_guest"),
):
    await ensure_task_access(task_id, db, user, guest_id)
    pending = human_controller.get_pending_intervention(task_id)
    resp_data = payload.response_data or {}
    has_text = bool(str(resp_data.get("text") or "").strip())
    has_file = bool(str(resp_data.get("file_text") or "").strip())
    if (
        pending
        and pending.get("intervention_type") == HumanInterventionType.FORM_INPUT_REQUIRED.value
        and payload.approved
        and not has_text
        and not has_file
    ):
        raise HTTPException(
            status_code=400,
            detail="Please provide the requested form value or attach a text file before continuing.",
        )
    success = human_controller.resolve_intervention(
        task_id=task_id,
        approved=payload.approved,
        response_data=payload.response_data
    )
    if not success:
        raise HTTPException(status_code=400, detail="No pending human intervention found for this task.")

    intervention_stmt = select(HumanInterventionModel).where(
        HumanInterventionModel.task_id == task_id,
        HumanInterventionModel.status == "PENDING",
    ).order_by(HumanInterventionModel.created_at.desc())
    intervention_res = await db.execute(intervention_stmt)
    stored_intervention = intervention_res.scalars().first()
    if stored_intervention:
        stored_intervention.status = "APPROVED" if payload.approved else "CANCELLED"
        stored_intervention.user_response = payload.response_data or {}
        stored_intervention.resolved_at = datetime.utcnow()
        await db.commit()

    return {"status": "success", "message": "Human intervention resolved. Resuming task execution."}


@router.post("/tasks/{task_id}/intervention/upload")
async def upload_intervention_file(
    task_id: str,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db_session),
    user: UserModel | None = Depends(optional_user),
    guest_id: str | None = Cookie(default=None, alias="awa_guest"),
):
    """Store a user-selected file in the isolated task session and resume upload intervention."""
    await ensure_task_access(task_id, db, user, guest_id)
    session = session_manager.get_session(task_id)
    pending = human_controller.get_pending_intervention(task_id)
    if not session or not pending or pending.get("intervention_type") != "FILE_UPLOAD_REQUIRED":
        raise HTTPException(status_code=400, detail="No pending file upload intervention found for this task.")

    upload_paths = []
    filenames = []
    try:
        for file in files:
            filename = os.path.basename(file.filename or "upload.bin")
            safe_name = f"{secrets.token_hex(8)}_{filename}"
            upload_path = os.path.join(session.session_dir, "downloads", safe_name)
            os.makedirs(os.path.dirname(upload_path), exist_ok=True)
            with open(upload_path, "wb") as destination:
                while chunk := await file.read(1024 * 1024):
                    destination.write(chunk)
            upload_paths.append(upload_path)
            filenames.append(filename)
    finally:
        for file in files:
            await file.close()

    if not upload_paths:
        raise HTTPException(status_code=400, detail="At least one file is required.")
    if not human_controller.resolve_intervention(
        task_id,
        True,
        {"file_paths": upload_paths, "file_path": upload_paths[0], "filenames": filenames, "filename": filenames[0]},
    ):
        raise HTTPException(status_code=400, detail="File upload intervention is no longer pending.")
    intervention_stmt = select(HumanInterventionModel).where(
        HumanInterventionModel.task_id == task_id,
        HumanInterventionModel.status == "PENDING",
    ).order_by(HumanInterventionModel.created_at.desc())
    intervention_res = await db.execute(intervention_stmt)
    stored_intervention = intervention_res.scalars().first()
    if stored_intervention:
        stored_intervention.status = "APPROVED"
        stored_intervention.user_response = {"filenames": filenames, "filename": filenames[0]}
        stored_intervention.resolved_at = datetime.utcnow()
        await db.commit()
    return {"status": "success", "filenames": filenames, "message": "File uploaded. Resuming task execution."}


@router.post("/tasks/{task_id}/pause")
async def pause_task_execution(
    task_id: str,
    db: AsyncSession = Depends(get_db_session),
    user: UserModel | None = Depends(optional_user),
    guest_id: str | None = Cookie(default=None, alias="awa_guest")
):
    """
    Pauses an active task execution loop.
    """
    task = await ensure_task_access(task_id, db, user, guest_id)
    if task.status in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
        return {"status": task.status, "message": f"Task is already {task.status.lower()}."}
    if task.status == TaskStatus.PAUSED.value:
        return {"status": TaskStatus.PAUSED.value, "message": "Task is already paused."}
    success = await task_manager.pause_task(task_id)
    if not success:
        return {"status": task.status, "message": "Task is not currently running."}
    return {"status": TaskStatus.PAUSED.value, "message": "Task execution paused."}


@router.post("/tasks/{task_id}/unpause")
@router.post("/tasks/{task_id}/resume_execution")
async def resume_task_execution(
    task_id: str,
    db: AsyncSession = Depends(get_db_session),
    user: UserModel | None = Depends(optional_user),
    guest_id: str | None = Cookie(default=None, alias="awa_guest")
):
    """
    Resumes a paused task execution loop.
    """
    task = await ensure_task_access(task_id, db, user, guest_id)
    if task.status == TaskStatus.RUNNING.value:
        return {"status": "RUNNING", "message": "Task is already running."}
    success = await task_manager.resume_task(task_id)
    if not success:
        return {"status": task.status, "message": "Task is not in a paused state."}
    return {"status": "RUNNING", "message": "Task execution resumed."}


@router.post("/tasks/{task_id}/continue")
async def continue_saved_task(
    task_id: str,
    db: AsyncSession = Depends(get_db_session),
    user: UserModel | None = Depends(optional_user),
    guest_id: str | None = Cookie(default=None, alias="awa_guest")
):
    task = await ensure_task_access(task_id, db, user, guest_id)
    if task.status in [TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value]:
        raise HTTPException(status_code=400, detail="Finished tasks cannot be continued.")
    if not await task_manager.continue_task(task.id, task.goal):
        raise HTTPException(status_code=400, detail="Task is already running.")
    return {"status": "RUNNING", "message": "Saved task workflow resumed."}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    db: AsyncSession = Depends(get_db_session),
    user: UserModel | None = Depends(optional_user),
    guest_id: str | None = Cookie(default=None, alias="awa_guest")
):
    task = await ensure_task_access(task_id, db, user, guest_id)

    if task.status in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
        return {"status": task.status, "message": "Task is already finished."}

    # Cancel active loop task
    loop_task = task_manager.active_tasks.pop(task_id, None)
    task_manager.paused_tasks.discard(task_id)
    if loop_task:
        loop_task.cancel()

    await session_manager.close_session(task_id)
    await task_manager._update_task_status(task_id, TaskStatus.CANCELLED)

    return {"status": TaskStatus.CANCELLED.value, "message": "Task cancelled."}


class BrowserInteractionRequest(BaseModel):
    action: str = Field(..., description="Action type: 'click', 'type', 'press', 'scroll', 'back', 'forward', 'reload', or 'navigate'")
    x_ratio: Optional[float] = Field(None, description="Click X coordinate ratio (0.0 to 1.0)")
    y_ratio: Optional[float] = Field(None, description="Click Y coordinate ratio (0.0 to 1.0)")
    text: Optional[str] = Field(None, description="Text to type into focused input")
    key: Optional[str] = Field(None, description="Key to press (e.g. 'Enter', 'Tab', 'Escape')")
    delta_y: Optional[int] = Field(None, description="Scroll pixel offset")
    url: Optional[str] = Field(None, description="URL to navigate directly to")


@router.post("/tasks/{task_id}/interact")
async def interact_with_live_browser(
    task_id: str,
    payload: BrowserInteractionRequest,
    db: AsyncSession = Depends(get_db_session),
    user: UserModel | None = Depends(optional_user),
    guest_id: str | None = Cookie(default=None, alias="awa_guest")
):
    """
    Receives interactive user mouse/keyboard input from embedded frontend canvas and forwards it to Playwright.
    """
    await ensure_task_access(task_id, db, user, guest_id)
    session = session_manager.get_session(task_id)
    if not session:
        session = await session_manager.get_or_create_interactive_session(task_id)
    if not session or not session.page or session.page.is_closed():
        raise HTTPException(status_code=404, detail="Active browser session not found for this task.")

    try:
        if payload.action == "click":
            if payload.x_ratio is None or payload.y_ratio is None:
                raise HTTPException(status_code=400, detail="x_ratio and y_ratio are required for click action.")
            await session.click_at_ratio(payload.x_ratio, payload.y_ratio)

        elif payload.action == "double_click":
            if payload.x_ratio is None or payload.y_ratio is None:
                raise HTTPException(status_code=400, detail="x_ratio and y_ratio are required for double_click action.")
            await session.double_click_at_ratio(payload.x_ratio, payload.y_ratio)

        elif payload.action == "mousedown":
            if payload.x_ratio is None or payload.y_ratio is None:
                raise HTTPException(status_code=400, detail="x_ratio and y_ratio are required for mousedown action.")
            await session.mouse_down(payload.x_ratio, payload.y_ratio)

        elif payload.action == "mousemove":
            if payload.x_ratio is None or payload.y_ratio is None:
                raise HTTPException(status_code=400, detail="x_ratio and y_ratio are required for mousemove action.")
            await session.mouse_move(payload.x_ratio, payload.y_ratio)

        elif payload.action == "mouseup":
            await session.mouse_up(payload.x_ratio, payload.y_ratio)

        elif payload.action == "type":
            if not payload.text:
                raise HTTPException(status_code=400, detail="text is required for type action.")
            await session.type_text(payload.text)

        elif payload.action == "press":
            key = payload.key or "Enter"
            await session.press_key(key)

        elif payload.action == "scroll":
            delta = payload.delta_y or 400
            await session.scroll_by(delta, payload.x_ratio, payload.y_ratio)

        elif payload.action == "back":
            await session.go_back()

        elif payload.action == "forward":
            await session.go_forward()

        elif payload.action == "reload":
            await session.reload()

        elif payload.action == "navigate":
            if not payload.url:
                raise HTTPException(status_code=400, detail="url is required for navigate action.")
            await session.navigate_to(payload.url)

        elif payload.action == "bring_to_front":
            await session.bring_to_front()

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action '{payload.action}'.")

        # For fast cursor actions (mousemove, mousedown, mouseup, scroll), return immediately (<2ms)
        # CDP screencast streams updated frames over WebSocket automatically.
        if payload.action in ("mousemove", "mousedown", "mouseup", "scroll"):
            return {
                "status": "success",
                "url": session.page.url if (session.page and not session.page.is_closed()) else "",
            }

        frame_data = await session.capture_base64_frame()
        if frame_data:
            await task_manager._broadcast(task_id, "BROWSER_FRAME", {"frame_data": frame_data}, persist=False)

        current_page_url = session.page.url if (session.page and not session.page.is_closed()) else ""
        if "google.com" in current_page_url.lower() and await session.is_google_signed_in():
            asyncio.create_task(session.persist_storage_state())

        return {
            "status": "success",
            "url": current_page_url,
            "frame_data": frame_data
        }

    except Exception as e:
        logger.error(f"Error executing manual browser interaction for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/live_frame")
async def get_task_live_frame(
    task_id: str,
    db: AsyncSession = Depends(get_db_session),
    user: UserModel | None = Depends(optional_user),
    guest_id: str | None = Cookie(default=None, alias="awa_guest")
):
    """
    Returns high-speed in-memory JPEG frame data URI for real-time live browser canvas streaming.
    """
    await ensure_task_access(task_id, db, user, guest_id)
    session = session_manager.get_session(task_id)
    if not session or not session.page or session.page.is_closed():
        raise HTTPException(status_code=404, detail="Active browser session not found for this task.")

    try:
        frame_data = await session.capture_base64_frame()
        page_title = ""
        page_url = ""
        if session.page and not session.page.is_closed():
            try:
                page_url = session.page.url
                page_title = await session.page.title()
            except Exception:
                pass
        return {
            "url": page_url,
            "title": page_title,
            "frame_data": frame_data
        }
    except Exception as e:
        if "closed" in str(e).lower():
            raise HTTPException(status_code=404, detail="Browser session has ended.")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/screenshot/{filename}")
async def get_task_screenshot(
    task_id: str,
    filename: str,
    db: AsyncSession = Depends(get_db_session),
    user: UserModel | None = Depends(optional_user),
    guest_id: str | None = Cookie(default=None, alias="awa_guest"),
):
    await ensure_task_access(task_id, db, user, guest_id)
    if os.path.basename(filename) != filename:
        raise HTTPException(status_code=400, detail="Invalid screenshot filename.")
    session = session_manager.get_session(task_id)
    filepath = None
    if session:
        filepath = os.path.join(session.session_dir, "screenshots", filename)

    if not filepath or not os.path.exists(filepath):
        session_result = await db.execute(select(BrowserSessionModel).where(BrowserSessionModel.task_id == task_id))
        stored_session = session_result.scalar_one_or_none()
        if stored_session:
            filepath = os.path.join(stored_session.session_dir, "screenshots", filename)

    if not filepath or not os.path.exists(filepath):
        events_result = await db.execute(
            select(TaskEventModel).where(
                TaskEventModel.task_id == task_id,
                TaskEventModel.screenshot_path.is_not(None),
            )
        )
        for ev in events_result.scalars().all():
            if ev.screenshot_path and os.path.basename(ev.screenshot_path) == filename and os.path.exists(ev.screenshot_path):
                filepath = ev.screenshot_path
                break

    if not filepath or not os.path.exists(filepath):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "sessions"))
        fallback_path = os.path.join(base_dir, task_id, "screenshots", filename)
        if os.path.exists(fallback_path):
            filepath = fallback_path

    if not filepath or not os.path.exists(filepath):
        session_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "sessions"))
        matches = glob.glob(os.path.join(session_root, "*", "screenshots", filename))
        if matches:
            filepath = matches[0]

    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Screenshot image not found.")

    media_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    return FileResponse(filepath, media_type=media_type)


@router.get("/tasks/{task_id}/events/{step}/screenshot")
async def get_event_screenshot(
    task_id: str,
    step: int,
    db: AsyncSession = Depends(get_db_session),
    user: UserModel | None = Depends(optional_user),
    guest_id: str | None = Cookie(default=None, alias="awa_guest"),
):
    await ensure_task_access(task_id, db, user, guest_id)
    result = await db.execute(
        select(TaskEventModel).where(
            TaskEventModel.task_id == task_id,
            TaskEventModel.step == step,
            TaskEventModel.screenshot_data.is_not(None),
        ).order_by(TaskEventModel.timestamp.desc())
    )
    event = result.scalars().first()
    if not event:
        raise HTTPException(status_code=404, detail="Screenshot artifact not found.")
    return Response(content=event.screenshot_data, media_type="image/jpeg")


# RAG and Automation Templates Endpoints
from app.rag.playwright_rag import rag_service
from app.agent.templates import template_registry


class RagQueryRequest(BaseModel):
    query: str = Field(..., description="Query string to search Playwright documentation semantically.")
    top_k: Optional[int] = Field(4, description="Number of top semantic search results to return.")
    category_filter: Optional[str] = Field(None, description="Optional doc category filter (e.g. locators, assertions, auth).")


@router.post("/rag/index")
async def trigger_rag_indexing(background_tasks: BackgroundTasks):
    """
    Triggers re-indexing of Playwright HTML documentation into ChromaDB vector store.
    """
    background_tasks.add_task(rag_service.index_documentation)
    return {
        "status": "started",
        "message": "Playwright documentation indexing task started in background."
    }


@router.post("/rag/query")
async def query_rag_knowledge(payload: RagQueryRequest):
    """
    Queries Playwright knowledge RAG semantically using ChromaDB and BAAI/bge-m3 embeddings.
    """
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    results = rag_service.search_knowledge(
        query=payload.query.strip(),
        top_k=payload.top_k or 4,
        category_filter=payload.category_filter
    )
    return {
        "query": payload.query,
        "results_count": len(results),
        "results": results
    }


@router.get("/rag/stats")
async def get_rag_statistics():
    """
    Retrieves ChromaDB vector store statistics, embedding model info, and status.
    """
    return rag_service.get_rag_stats()


@router.get("/templates")
async def list_automation_templates():
    """
    Returns list of available reusable Playwright automation templates.
    """
    return {
        "count": len(template_registry.list_templates()),
        "templates": template_registry.list_templates()
    }
