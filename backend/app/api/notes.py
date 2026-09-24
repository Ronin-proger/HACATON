from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import obsidian as obs

router = APIRouter(prefix="/api/notes", tags=["notes"])


class NoteIn(BaseModel):
    path: str | None = None
    title: str = ""
    body: str = ""
    content: str | None = None
    author: str = "crew"
    folder: str = "Inbox"


class AiIn(BaseModel):
    units: list[str] = Field(default_factory=list)


@router.get("/status")
def status():
    st = obs.api_status()
    notes = obs.list_notes()
    return {
        "api": st,
        "vault": str(obs.vault_root()),
        "notes": len(notes),
        "shared": True,
    }


@router.get("")
def catalog():
    notes = obs.list_notes()
    graph = obs.build_graph(notes)
    return {
        "notes": [{k: n[k] for k in n if k != "content"} for n in notes],
        "graph": graph,
        "analytics": obs.analytics(notes),
        "api": obs.api_status(),
    }


@router.get("/item")
def item(path: str):
    try:
        return obs.get_note(path)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("")
def upsert(payload: NoteIn):
    if payload.content and payload.path:
        path, content = payload.path, payload.content
    elif payload.title and payload.body:
        path, content = obs.compose_user_note(payload.title, payload.body, payload.author, payload.folder)
    else:
        raise HTTPException(400, "нужны title+body или path+content")
    try:
        note = obs.write_note(path, content, sync_api=True)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    notes = obs.list_notes()
    return {"note": note, "graph": obs.build_graph(notes), "analytics": obs.analytics(notes)}


@router.post("/ai")
def ai_doc(payload: AiIn | None = None):
    path, content = obs.compose_ai_doc({"units": (payload.units if payload else [])})
    note = obs.write_note(path, content, sync_api=True)
    notes = obs.list_notes()
    return {"note": note, "graph": obs.build_graph(notes), "analytics": obs.analytics(notes)}
