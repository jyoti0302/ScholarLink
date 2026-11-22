import asyncio
import threading
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.main import app, get_cancellation_registry, get_search_service
from backend.database.connection import get_db
from backend.database.models import Base
from backend.search.cancellation import CancellationRegistry, CancellationToken, SearchCancelledError
from backend.search.embedding import DeterministicHashEmbeddingProvider
from backend.search.query_understanding import ExpandedQuery, QueryExpansionService
from backend.search.ranking import SearchService
from backend.search.retrieval import HybridRetrievalService, QueryEmbeddingService


def test_cancellation_registry_isolation_and_cleanup():
    reg = CancellationRegistry()
    tok_a = reg.register("req-a")
    tok_b = reg.register("req-b")
    assert reg.active_count() == 2

    assert reg.cancel("req-a") is True
    assert tok_a.is_cancelled() is True
    assert tok_b.is_cancelled() is False
    assert reg.cancel("req-unknown") is False

    reg.unregister("req-a")
    reg.unregister("req-b")
    assert reg.active_count() == 0


def test_hybrid_retrieval_stops_after_embedding_and_between_dense_and_sparse():
    class FakeIndexManager:
        def __init__(self, cancel_on_dense: CancellationToken = None):
            self.dense_calls = 0
            self.sparse_calls = 0
            self.cancel_on_dense = cancel_on_dense

        def dense_search(self, **kwargs):
            self.dense_calls += 1
            if self.cancel_on_dense is not None:
                self.cancel_on_dense.cancel()
            return []

        def sparse_search(self, **kwargs):
            self.sparse_calls += 1
            return []

    # Case 1: cancelled during embedding -> embedding finishes safely, zero Qdrant calls run
    tok1 = CancellationToken("req-1")
    embed_completed = False

    class CancellingProvider(DeterministicHashEmbeddingProvider):
        def encode(self, texts):
            nonlocal embed_completed
            out = super().encode(texts)
            tok1.cancel()
            embed_completed = True
            return out

    idx1 = FakeIndexManager()
    svc1 = HybridRetrievalService(
        index_manager=idx1,
        query_embedding_service=QueryEmbeddingService(CancellingProvider()),
    )
    with pytest.raises(SearchCancelledError) as exc1:
        svc1.retrieve(
            expanded_queries=[ExpandedQuery(query_text="NLP", query_kind="original", weight=1.0)],
            cancel_token=tok1,
        )
    assert embed_completed is True
    assert exc1.value.stage == "after_query_embedding"
    assert idx1.dense_calls == 0
    assert idx1.sparse_calls == 0

    # Case 2: cancelled during first dense_search -> sparse_search never starts
    tok2 = CancellationToken("req-2")
    idx2 = FakeIndexManager(cancel_on_dense=tok2)
    svc2 = HybridRetrievalService(
        index_manager=idx2,
        query_embedding_service=QueryEmbeddingService(DeterministicHashEmbeddingProvider()),
    )
    with pytest.raises(SearchCancelledError) as exc2:
        svc2.retrieve(
            expanded_queries=[ExpandedQuery(query_text="NLP", query_kind="original", weight=1.0)],
            cancel_token=tok2,
        )
    assert exc2.value.stage == "sparse_retrieval"
    assert idx2.dense_calls == 1
    assert idx2.sparse_calls == 0


def test_fastapi_cancel_endpoint_and_registry_cleanup():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    registry = CancellationRegistry()

    allow_continue = threading.Event()
    loop_holder: dict = {}
    entered_holder: dict = {}

    class CooperativeStubSearchService:
        def search(
            self,
            db,
            query,
            top_k=10,
            use_expansion=True,
            department_ids=None,
            include_candidate_publications=True,
            cancel_token=None,
        ):
            loop = loop_holder.get("loop")
            entered_evt = entered_holder.get("evt")
            if loop is not None and entered_evt is not None:
                loop.call_soon_threadsafe(entered_evt.set)
            allow_continue.wait(timeout=2.0)
            if cancel_token is not None:
                cancel_token.check("dense_retrieval")
            return {"query": query, "expansion": None, "status": "ok", "message": None, "results": []}

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_search_service] = lambda: CooperativeStubSearchService()
    app.dependency_overrides[get_cancellation_registry] = lambda: registry

    async def _run_concurrent_cancel_flow():
        loop_holder["loop"] = asyncio.get_running_loop()
        entered_evt = asyncio.Event()
        entered_holder["evt"] = entered_evt
        search_task = None
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=5.0) as client:
                # Unknown request_id returns not_found safely
                r_nf = await client.post("/search/cancel/does-not-exist")
                assert r_nf.status_code == 200
                assert r_nf.json() == {"request_id": "does-not-exist", "cancelled": False, "status": "not_found"}

                search_task = asyncio.create_task(
                    client.post(
                        "/search",
                        json={"query": "NLP for Indian languages", "limit": 5, "request_id": "req-live-cancel"},
                    )
                )

                # Wait with bounded timeout for POST /search to enter SearchService.search()
                await asyncio.wait_for(entered_evt.wait(), timeout=2.0)
                assert registry.active_count() == 1

                r_cancel = await client.post("/search/cancel/req-live-cancel")
                assert r_cancel.status_code == 200
                assert r_cancel.json() == {"request_id": "req-live-cancel", "cancelled": True, "status": "cancelled"}

                allow_continue.set()
                r_search = await asyncio.wait_for(search_task, timeout=2.0)
                assert r_search.status_code == 499
                assert r_search.json()["status"] == "cancelled"
                # Registry entry cleaned up in finally block (no memory leak)
                assert registry.active_count() == 0
        finally:
            allow_continue.set()
            if search_task is not None and not search_task.done():
                search_task.cancel()
                try:
                    await asyncio.wait_for(search_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

    try:
        asyncio.run(asyncio.wait_for(_run_concurrent_cancel_flow(), timeout=5.0))
    finally:
        allow_continue.set()
        app.dependency_overrides.clear()
        engine.dispose()
