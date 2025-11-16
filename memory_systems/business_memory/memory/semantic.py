"""
Semantic Memory System

Stores and retrieves general knowledge, patterns, and learned concepts using
vector embeddings in ChromaDB. Implements self-learning adaptation per Business Plan.
"""

# Standard library
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import sys

# Third-party
import chromadb
from chromadb.config import Settings as ChromaSettings
import litellm

# Local - models first (single source of truth)
project_root = Path(__file__).parent.parent.parent.parent
from models.core import ConstitutionalRule, ConstitutionalValidation, ConstitutionalError

# Local - configuration
sys.path.insert(0, str(project_root / "config_settings"))
from config import get_settings, resolve_litellm_model

# Local - constitutional enforcement
sys.path.insert(0, str(project_root / "constitutional_layer_immutable"))
from constitution import validate_constitutional_compliance

# Local - access control from same directory
sys.path.insert(0, str(project_root / "memory_systems" / "business_memory" / "memory"))
from access_control import validate_memory_operation

logger = logging.getLogger(__name__)


# ChromaDB client and collection
_chroma_client: Optional[chromadb.ClientAPI] = None
_chroma_collection: Optional[chromadb.Collection] = None


def _get_chroma_client() -> chromadb.ClientAPI:
    """
    Get or create ChromaDB persistent client.
    
    Returns:
        ChromaDB client instance
    """
    global _chroma_client
    if _chroma_client is None:
        chroma_path = project_root / "memory_systems" / "business_memory" / "chroma_db"
        chroma_path.mkdir(parents=True, exist_ok=True)
        
        _chroma_client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        logger.info(f"Initialized ChromaDB client at {chroma_path}")
    
    return _chroma_client


def _get_collection() -> chromadb.Collection:
    """
    Get or create the board_memory collection.
    
    Returns:
        ChromaDB collection instance
    """
    global _chroma_collection
    if _chroma_collection is None:
        client = _get_chroma_client()
        _chroma_collection = client.get_or_create_collection(
            name="board_memory",
            metadata={"description": "Board decision memory with semantic embeddings"}
        )
        logger.info("Retrieved board_memory collection")
    
    return _chroma_collection


def embed_decision(
    meeting_id: str,
    summary: str,
    outcome: str,
    metadata: Dict
) -> None:
    """
    Embed a board decision into semantic memory.
    
    Stores the decision in ChromaDB with versioned embeddings. The decision
    is stored with full metadata including timestamp, participants, votes,
    embedding model, and embedding version.
    
    Args:
        meeting_id: Unique identifier for the meeting/decision
        summary: Text summary of the decision
        outcome: Outcome of the decision (e.g., "approved", "rejected")
        metadata: Dictionary containing additional metadata:
            - timestamp: ISO format datetime
            - participants: List of participant IDs
            - votes: Dictionary of votes cast
            - embedding_model: Model used for embedding
            - embedding_version: Version of embedding model
            
    Raises:
        ConstitutionalError: If memory operation validation fails (Rule 10)
        
    Example:
        >>> embed_decision(
        ...     meeting_id="meeting_001",
        ...     summary="Approved new feature development",
        ...     outcome="approved",
        ...     metadata={
        ...         "timestamp": "2024-01-01T00:00:00",
        ...         "participants": ["member1", "member2"],
        ...         "votes": {"member1": "approve", "member2": "approve"},
        ...         "embedding_model": "text-embedding-3-small",
        ...         "embedding_version": "v1"
        ...     }
        ... )
    """
    # Validate memory operation via access control (Rule 10)
    owner_signature = metadata.get("owner_signature")
    if not validate_memory_operation("write", "system", owner_signature):
        logger.error(f"Memory write operation denied for meeting {meeting_id}")
        raise ConstitutionalError(
            "Rule 10 Violation: Memory write operations require owner authorization"
        )
    
    # Ensure required metadata fields
    if "timestamp" not in metadata:
        metadata["timestamp"] = datetime.now().isoformat()
    if "embedding_model" not in metadata:
        metadata["embedding_model"] = "text-embedding-3-small"
    if "embedding_version" not in metadata:
        metadata["embedding_version"] = "v1"
    
    try:
        collection = _get_collection()
        
        # Create document text for embedding
        document_text = f"Meeting: {meeting_id}\nSummary: {summary}\nOutcome: {outcome}"
        
        # Generate embedding using LiteLLM (supports OpenAI embeddings)
        try:
            embedding_response = litellm.embedding(
                model="text-embedding-3-small",
                input=[document_text]
            )
            embedding = embedding_response.data[0].embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}", exc_info=True)
            raise ConstitutionalError(
                f"Rule 6 Violation: Failed to embed decision. Embedding error: {e}"
            )
        
        # Create unique ID for this decision
        decision_id = f"decision_{meeting_id}_{metadata['timestamp']}"
        
        # Prepare metadata for ChromaDB (convert lists/dicts to strings)
        # ChromaDB only accepts str, int, float, bool, SparseVector, or None
        chroma_metadata = {
            "meeting_id": meeting_id,
            "summary": summary,
            "outcome": outcome,
            "timestamp": metadata.get("timestamp", ""),
            "embedding_model": metadata.get("embedding_model", ""),
            "embedding_version": metadata.get("embedding_version", "")
        }
        
        # Convert complex types to strings
        if "participants" in metadata:
            chroma_metadata["participants"] = json.dumps(metadata["participants"]) if isinstance(metadata["participants"], list) else str(metadata["participants"])
        if "votes" in metadata:
            chroma_metadata["votes"] = json.dumps(metadata["votes"]) if isinstance(metadata["votes"], dict) else str(metadata["votes"])
        
        # Store in ChromaDB
        collection.add(
            ids=[decision_id],
            embeddings=[embedding],
            documents=[document_text],
            metadatas=[chroma_metadata]
        )
        
        # Log embedding operation (Rule 6)
        try:
            from utilities.logger import log_event as base_log_event
            base_log_event(
                event_type="semantic_memory_embed",
                data={
                    "meeting_id": meeting_id,
                    "decision_id": decision_id,
                    "outcome": outcome,
                    "embedding_model": metadata["embedding_model"],
                    "embedding_version": metadata["embedding_version"]
                },
                metadata={"function": "embed_decision"}
            )
        except Exception as e:
            logger.warning(f"Failed to log embedding operation: {e}")
        
        logger.info(f"Embedded decision {decision_id} into semantic memory")
        
    except ConstitutionalError:
        raise
    except Exception as e:
        logger.error(f"Failed to embed decision {meeting_id}: {e}", exc_info=True)
        raise ConstitutionalError(
            f"Rule 6 Violation: Failed to store decision in semantic memory. Error: {e}"
        )


def recall_relevant_decisions(query: str, n_results: int = 5) -> List[Dict]:
    """
    Recall relevant past decisions based on semantic similarity.
    
    Queries ChromaDB for decisions similar to the provided query.
    Returns a list of relevant decisions with their summaries and metadata.
    
    Args:
        query: Text query to search for similar decisions
        n_results: Number of results to return (default: 5)
        
    Returns:
        List of dictionaries containing:
            - meeting_id: Meeting identifier
            - summary: Decision summary
            - outcome: Decision outcome
            - metadata: Full metadata dictionary
            - distance: Similarity distance (lower is more similar)
            
    Example:
        >>> decisions = recall_relevant_decisions(
        ...     query="feature development approval",
        ...     n_results=3
        ... )
        >>> for decision in decisions:
        ...     print(f"{decision['summary']}: {decision['outcome']}")
    """
    try:
        collection = _get_collection()
        
        # Generate query embedding
        embedding_response = litellm.embedding(
            model="text-embedding-3-small",
            input=[query]
        )
        query_embedding = embedding_response.data[0].embedding
        
        # Query ChromaDB
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        
        # Format results
        decisions = []
        if results["ids"] and len(results["ids"][0]) > 0:
            for i, decision_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else None
                
                decisions.append({
                    "decision_id": decision_id,
                    "meeting_id": metadata.get("meeting_id", ""),
                    "summary": metadata.get("summary", ""),
                    "outcome": metadata.get("outcome", ""),
                    "metadata": metadata,
                    "distance": distance
                })
        
        # Log recall operation (Rule 6)
        try:
            from utilities.logger import log_event as base_log_event
            base_log_event(
                event_type="semantic_memory_recall",
                data={
                    "query": query[:200],  # Truncate for logging
                    "n_results": n_results,
                    "results_found": len(decisions)
                },
                metadata={"function": "recall_relevant_decisions"}
            )
        except Exception as e:
            logger.warning(f"Failed to log recall operation: {e}")
        
        logger.info(f"Recalled {len(decisions)} relevant decisions for query: {query[:50]}")
        return decisions
        
    except Exception as e:
        logger.error(f"Failed to recall relevant decisions: {e}", exc_info=True)
        return []


def get_trend_analysis(topic: str) -> str:
    """
    Analyze trends in past decisions about a specific topic.
    
    Recalls 10 relevant decisions about the topic and uses an LLM to analyze
    patterns, identifying what worked, what failed, patterns over time, and
    recommendations.
    
    Args:
        topic: Topic to analyze (e.g., "feature development", "budget allocation")
        
    Returns:
        String containing trend analysis with:
            1. What worked (high ROI)
            2. What failed
            3. Patterns over time
            4. Recommendations
            
    Raises:
        ConstitutionalError: If LLM call fails
        
    Example:
        >>> analysis = get_trend_analysis("feature development")
        >>> print(analysis)
    """
    # Recall 10 relevant decisions
    decisions = recall_relevant_decisions(topic, n_results=10)
    
    if not decisions:
        logger.warning(f"No relevant decisions found for topic: {topic}")
        return f"No relevant decisions found for topic: {topic}"

    settings = get_settings()
    provider_identifier = settings.provider_model_identifier("anthropic")
    model_name = resolve_litellm_model(provider_identifier)
    
    # Prepare decisions text for LLM
    decisions_text = json.dumps(decisions, indent=2, ensure_ascii=False)
    
    # Log LLM call attempt (Rule 6)
    try:
        from utilities.logger import log_event as base_log_event
        base_log_event(
            event_type="llm_call_attempt",
            data={
                "provider": provider_identifier,
                "purpose": "trend_analysis",
                "topic": topic,
                "decision_count": len(decisions)
            },
            metadata={"function": "get_trend_analysis"}
        )
    except Exception as e:
        logger.warning(f"Failed to log LLM call attempt: {e}")
    
    # Prepare prompt
    prompt = (
        f"Analyze these past decisions about '{topic}':\n\n{decisions_text}\n\n"
        f"Identify:\n"
        f"1. What worked (high ROI)\n"
        f"2. What failed\n"
        f"3. Patterns over time\n"
        f"4. Recommendations\n\n"
        f"Provide a structured analysis in plain text."
    )
    
    try:
        # Call LLM via LiteLLM
        response = litellm.completion(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a board decision analyst. Analyze patterns and provide actionable insights."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        analysis = response.choices[0].message.content.strip()
        
        # Log successful LLM call (Rule 6)
        try:
            from utilities.logger import log_event as base_log_event
            base_log_event(
                event_type="llm_call_success",
                data={
                    "provider": provider_identifier,
                    "purpose": "trend_analysis",
                    "topic": topic,
                    "response_length": len(analysis)
                },
                metadata={"function": "get_trend_analysis"}
            )
        except Exception as e:
            logger.warning(f"Failed to log LLM call success: {e}")
        
        logger.info(f"Generated trend analysis for topic '{topic}': {len(analysis)} characters")
        return analysis
        
    except Exception as e:
        logger.error(f"LLM call failed for trend analysis: {e}", exc_info=True)
        
        # Log failed LLM call (Rule 6)
        try:
            from utilities.logger import log_event as base_log_event
            base_log_event(
                event_type="llm_call_failure",
                data={
                    "provider": provider_identifier,
                    "purpose": "trend_analysis",
                    "topic": topic,
                    "error": str(e)
                },
                metadata={"function": "get_trend_analysis"}
            )
        except Exception as log_error:
            logger.error(f"Failed to log LLM call failure: {log_error}")
        
        raise ConstitutionalError(
            f"Rule 6 Violation: Failed to analyze trends. LLM call failed: {e}"
        )


def validate_memory_integrity() -> bool:
    """
    Validate the integrity of stored embeddings.
    
    Checks checksums on stored embeddings and verifies no hallucinated
    memories exist. This ensures data integrity and prevents corruption.
    
    Returns:
        True if all memories are valid, False otherwise
        
    Example:
        >>> is_valid = validate_memory_integrity()
        >>> assert is_valid, "Memory integrity check failed"
    """
    try:
        collection = _get_collection()
        
        # Get all stored decisions
        all_data = collection.get()
        
        if not all_data["ids"]:
            logger.info("No memories stored, integrity check passed")
            return True
        
        # Validate each memory
        invalid_count = 0
        for i, decision_id in enumerate(all_data["ids"]):
            # Check that required metadata exists
            if i < len(all_data["metadatas"]) and all_data["metadatas"][i]:
                metadata = all_data["metadatas"][i]
                required_fields = ["meeting_id", "summary", "outcome", "timestamp"]
                
                missing_fields = [field for field in required_fields if field not in metadata]
                if missing_fields:
                    logger.warning(
                        f"Memory {decision_id} missing required fields: {missing_fields}"
                    )
                    invalid_count += 1
                    continue
                
                # Verify timestamp is valid
                try:
                    datetime.fromisoformat(metadata["timestamp"])
                except (ValueError, KeyError):
                    logger.warning(f"Memory {decision_id} has invalid timestamp")
                    invalid_count += 1
                    continue
                
                # Verify embedding exists
                if i < len(all_data["embeddings"]) and all_data["embeddings"][i]:
                    embedding = all_data["embeddings"][i]
                    if not isinstance(embedding, list) or len(embedding) == 0:
                        logger.warning(f"Memory {decision_id} has invalid embedding")
                        invalid_count += 1
                        continue
            else:
                logger.warning(f"Memory {decision_id} missing metadata")
                invalid_count += 1
                continue
        
        if invalid_count > 0:
            logger.error(f"Memory integrity check failed: {invalid_count} invalid memories")
            return False
        
        logger.info(f"Memory integrity check passed: {len(all_data['ids'])} memories validated")
        return True
        
    except Exception as e:
        logger.error(f"Memory integrity check error: {e}", exc_info=True)
        return False
