from __future__ import annotations

from unittest.mock import MagicMock

from app.mempalace import chroma_store


def test_delete_by_user_calls_collection_delete(monkeypatch):
    coll = MagicMock()
    monkeypatch.setattr(chroma_store, "_get_collection", lambda: coll)

    chroma_store.delete_by_user("Sancho")

    coll.delete.assert_called_once_with(where={"user_id": "Sancho"})
