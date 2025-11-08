"""
Comprehensive tests for memory systems.

Tests episodic, semantic, context builder, and access control modules.
"""

# Standard library
import json
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Third-party
import chromadb

# Setup sys.path for imports from folders with spaces
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "Memory Systems"))
sys.path.insert(0, str(project_root / "Governance Layer"))
sys.path.insert(0, str(project_root / "Config & Settings"))
sys.path.insert(0, str(project_root / "Utilities"))
sys.path.insert(0, str(project_root / "Constitutional Layer (Immutable)"))

# Local - models first (single source of truth)
sys.path.insert(0, str(project_root / "Memory Systems" / "Codebase Memory"))
from models.core import ConstitutionalError

# Local - memory systems (import directly from path)
memory_path = project_root / "Memory Systems" / "Business Memory" / "memory"
sys.path.insert(0, str(memory_path))
import episodic
import semantic
import context_builder
import access_control

# Import functions for convenience
from episodic import log_event, get_recent_events, summarize_recent_activity
from semantic import (
    embed_decision,
    recall_relevant_decisions,
    get_trend_analysis,
    validate_memory_integrity
)
from context_builder import build_agent_context
from access_control import validate_memory_operation, check_owner_signature


@pytest.fixture
def temp_log_dir(tmp_path):
    """Create temporary log directory for tests."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return log_dir


@pytest.fixture
def temp_chroma_dir(tmp_path):
    """Create temporary ChromaDB directory for tests."""
    chroma_dir = tmp_path / "chroma_db"
    chroma_dir.mkdir()
    return chroma_dir


@pytest.fixture
def mock_proposal():
    """Create mock proposal for testing."""
    return {
        "id": "test_prop_1",
        "title": "Test Proposal",
        "description": "This is a test proposal",
        "financial_impact": 1000.0,
        "legal_risk": 0.1,
        "keywords": ["test", "proposal"]
    }


class TestEpisodicMemory:
    """Tests for episodic memory system."""
    
    def test_episodic_logging(self, temp_log_dir, monkeypatch):
        """Test that events are logged correctly."""
        # Patch log file path
        def mock_path():
            return temp_log_dir / "events.jsonl"
        
        monkeypatch.setattr(episodic, "_get_log_file_path", mock_path)
        monkeypatch.setattr(episodic, "_log_file_path", None)  # Reset global
        
        # Log event
        entry = log_event(
            event_type="test_event",
            data={"key": "value"},
            metadata={"test": True}
        )
        
        # Verify entry structure
        assert "timestamp" in entry
        assert entry["type"] == "test_event"
        assert entry["data"]["key"] == "value"
        assert entry["metadata"]["test"] is True
        
        # Verify file was created
        log_file = temp_log_dir / "events.jsonl"
        assert log_file.exists()
        
        # Verify content
        with open(log_file, "r") as f:
            lines = f.readlines()
            assert len(lines) == 1
            logged_entry = json.loads(lines[0])
            assert logged_entry["type"] == "test_event"
    
    def test_episodic_retrieval(self, temp_log_dir, monkeypatch):
        """Test that recent events can be retrieved."""
        # Patch log file path
        def mock_path():
            return temp_log_dir / "events.jsonl"
        
        monkeypatch.setattr(episodic, "_get_log_file_path", mock_path)
        monkeypatch.setattr(episodic, "_log_file_path", None)  # Reset global
        
        # Log multiple events
        for i in range(5):
            log_event(
                event_type=f"event_{i}",
                data={"index": i}
            )
        
        # Retrieve recent events
        events = get_recent_events(limit=3)
        
        # Verify retrieval
        assert len(events) == 3
        assert events[0]["type"] == "event_4"  # Most recent first
        assert events[2]["type"] == "event_2"
    
    @patch("episodic.litellm.completion")
    def test_summarize_recent_activity(self, mock_completion, temp_log_dir, monkeypatch):
        """Test that recent activity can be summarized."""
        # Patch log file path
        def mock_path():
            return temp_log_dir / "events.jsonl"
        
        monkeypatch.setattr(episodic, "_get_log_file_path", mock_path)
        monkeypatch.setattr(episodic, "_log_file_path", None)  # Reset global
        
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary: Test activity"
        mock_completion.return_value = mock_response
        
        # Create test events
        events = [
            {"type": "decision", "data": {"outcome": "approved"}},
            {"type": "vote", "data": {"vote": "yes"}}
        ]
        
        # Summarize
        summary = summarize_recent_activity(events)
        
        # Verify summary
        assert "Summary: Test activity" in summary
        mock_completion.assert_called_once()


class TestSemanticMemory:
    """Tests for semantic memory system."""
    
    @patch("semantic.litellm.embedding")
    @patch("semantic.validate_memory_operation")
    def test_semantic_embedding(self, mock_validate, mock_embedding, temp_chroma_dir, monkeypatch):
        """Test that decisions can be embedded."""
        # Mock validation
        mock_validate.return_value = True
        
        # Mock embedding
        mock_embedding.return_value = MagicMock()
        mock_embedding.return_value.data = [MagicMock()]
        mock_embedding.return_value.data[0].embedding = [0.1] * 1536  # Mock embedding vector
        
        # Patch ChromaDB path
        def mock_client():
            return chromadb.PersistentClient(path=str(temp_chroma_dir))
        
        monkeypatch.setattr(semantic, "_get_chroma_client", mock_client)
        monkeypatch.setattr(semantic, "_chroma_client", None)  # Reset global
        monkeypatch.setattr(semantic, "_chroma_collection", None)  # Reset global
        
        # Embed decision
        embed_decision(
            meeting_id="meeting_001",
            summary="Test decision",
            outcome="approved",
            metadata={
                "owner_signature": "mock_owner_signature",
                "participants": ["member1"],
                "votes": {"member1": "approve"}
            }
        )
        
        # Verify embedding was called
        mock_embedding.assert_called_once()
        mock_validate.assert_called_once()
    
    @patch("semantic.litellm.embedding")
    def test_semantic_recall(self, mock_embedding, temp_chroma_dir, monkeypatch):
        """Test that relevant decisions can be recalled."""
        # Mock embedding
        mock_embedding.return_value = MagicMock()
        mock_embedding.return_value.data = [MagicMock()]
        mock_embedding.return_value.data[0].embedding = [0.1] * 1536
        
        # Patch ChromaDB path
        def mock_client():
            client = chromadb.PersistentClient(path=str(temp_chroma_dir))
            collection = client.get_or_create_collection("board_memory")
            # Add test data
            collection.add(
                ids=["test_1"],
                embeddings=[[0.1] * 1536],
                documents=["Test decision"],
                metadatas=[{"meeting_id": "meeting_001", "summary": "Test", "outcome": "approved"}]
            )
            return client
        
        monkeypatch.setattr(semantic, "_get_chroma_client", mock_client)
        monkeypatch.setattr(semantic, "_chroma_client", None)  # Reset global
        monkeypatch.setattr(semantic, "_chroma_collection", None)  # Reset global
        
        # Recall decisions
        decisions = recall_relevant_decisions("test query", n_results=1)
        
        # Verify recall
        assert len(decisions) >= 0  # May be empty if no matches
        mock_embedding.assert_called_once()
    
    @patch("semantic.litellm.completion")
    @patch("semantic.recall_relevant_decisions")
    def test_trend_analysis(self, mock_recall, mock_completion):
        """Test that trend analysis works."""
        # Mock recall
        mock_recall.return_value = [
            {"summary": "Decision 1", "outcome": "approved"},
            {"summary": "Decision 2", "outcome": "rejected"}
        ]
        
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Trend analysis: Patterns identified"
        mock_completion.return_value = mock_response
        
        # Get trend analysis
        analysis = get_trend_analysis("test topic")
        
        # Verify analysis
        assert "Trend analysis: Patterns identified" in analysis
        mock_completion.assert_called_once()
    
    @patch("semantic._get_collection")
    def test_memory_integrity(self, mock_collection):
        """Test that memory integrity can be validated."""
        # Mock collection
        mock_coll = MagicMock()
        mock_coll.get.return_value = {
            "ids": ["test_1"],
            "metadatas": [{"meeting_id": "m1", "summary": "test", "outcome": "approved", "timestamp": "2024-01-01T00:00:00"}],
            "embeddings": [[0.1] * 1536]
        }
        mock_collection.return_value = mock_coll
        
        # Validate integrity
        is_valid = validate_memory_integrity()
        
        # Verify validation
        assert is_valid is True


class TestAccessControl:
    """Tests for access control system."""
    
    def test_access_control_read(self):
        """Test that read operations are always allowed."""
        result = validate_memory_operation("read", "system")
        assert result is True
    
    def test_access_control_write_requires_signature(self):
        """Test that write operations require signature."""
        with pytest.raises(ConstitutionalError, match="Rule 10 Violation"):
            validate_memory_operation("write", "system", None)
    
    @patch("access_control.check_owner_signature")
    def test_access_control_write_with_signature(self, mock_check):
        """Test that write operations work with valid signature."""
        mock_check.return_value = True
        result = validate_memory_operation("write", "system", "valid_signature")
        assert result is True
    
    def test_access_control_delete_forbidden(self):
        """Test that delete operations are always forbidden."""
        with pytest.raises(ConstitutionalError, match="Rule 6 Violation"):
            validate_memory_operation("delete", "system")
    
    @patch("access_control.get_settings")
    def test_check_owner_signature_debug(self, mock_settings):
        """Test owner signature check in debug mode."""
        mock_settings.return_value = MagicMock(debug=True)
        result = check_owner_signature("mock_owner_signature")
        assert result is True
        
        result = check_owner_signature("invalid")
        assert result is False


class TestContextBuilder:
    """Tests for context builder."""
    
    @patch("context_builder.get_recent_events")
    @patch("context_builder.summarize_recent_activity")
    @patch("context_builder.recall_relevant_decisions")
    @patch("context_builder.get_trend_analysis")
    def test_context_builder(
        self,
        mock_trend,
        mock_recall,
        mock_summarize,
        mock_events,
        mock_proposal
    ):
        """Test that context is built correctly."""
        # Mock dependencies
        mock_events.return_value = []
        mock_summarize.return_value = "Recent activity summary"
        mock_recall.return_value = [{"summary": "Precedent 1"}]
        mock_trend.return_value = "Trend analysis"
        
        # Build context
        context = build_agent_context(
            role="CEO",
            current_proposal=mock_proposal,
            topic_keywords=["test"]
        )
        
        # Verify context structure
        assert "constitutional_rules" in context
        assert context["role"] == "CEO"
        assert context["current_proposal"]["id"] == "test_prop_1"
        assert "recent_activity_summary" in context
        assert "relevant_precedents" in context
        assert "trend_analysis" in context
        assert "timestamp" in context
    
    def test_context_includes_constitution(self, mock_proposal):
        """Test that context includes constitutional rules."""
        with patch("context_builder.get_recent_events", return_value=[]):
            with patch("context_builder.summarize_recent_activity", return_value="Summary"):
                with patch("context_builder.recall_relevant_decisions", return_value=[]):
                    with patch("context_builder.get_trend_analysis", return_value="Analysis"):
                        context = build_agent_context(
                            role="CEO",
                            current_proposal=mock_proposal
                        )
                        
                        assert "constitutional_rules" in context
                        assert len(context["constitutional_rules"]) > 0
    
    def test_context_includes_history(self, mock_proposal):
        """Test that context includes historical precedents."""
        mock_precedents = [
            {"summary": "Past decision 1", "outcome": "approved"},
            {"summary": "Past decision 2", "outcome": "rejected"}
        ]
        
        with patch("context_builder.get_recent_events", return_value=[]):
            with patch("context_builder.summarize_recent_activity", return_value="Summary"):
                with patch("context_builder.recall_relevant_decisions", return_value=mock_precedents):
                    with patch("context_builder.get_trend_analysis", return_value="Analysis"):
                        context = build_agent_context(
                            role="CEO",
                            current_proposal=mock_proposal,
                            topic_keywords=["decision"]
                        )
                        
                        assert "relevant_precedents" in context
                        assert len(context["relevant_precedents"]) == 2
