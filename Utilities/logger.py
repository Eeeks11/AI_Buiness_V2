"""
Logging Utility for Rule 6 Compliance (Full Transparency)

This module provides structured logging functionality to ensure all decisions,
actions, and operations are logged to a persistent, accessible record.

All log entries are written to logs/events.jsonl in JSONL format.
"""

# Standard library
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# Log file path
_log_file_path: Optional[Path] = None


def _get_log_file_path() -> Path:
    """
    Get the path to the events log file, creating directory if needed.
    
    Returns:
        Path to logs/events.jsonl
    """
    global _log_file_path
    if _log_file_path is None:
        project_root = Path(__file__).parent.parent
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        _log_file_path = log_dir / "events.jsonl"
    return _log_file_path


def log_event(
    event_type: str,
    data: Dict,
    metadata: Optional[Dict] = None
) -> None:
    """
    Log an event to the persistent event log (Rule 6: Full Transparency).
    
    All events are written to logs/events.jsonl in JSONL format with:
    - timestamp: ISO format datetime
    - type: Event type identifier
    - data: Event data dictionary
    - metadata: Optional metadata dictionary
    
    Args:
        event_type: Type identifier for the event (e.g., 'system_startup', 'proposal_created')
        data: Dictionary containing event data
        metadata: Optional dictionary with additional metadata
        
    Example:
        >>> log_event(
        ...     event_type="system_startup",
        ...     data={"models": ["openai", "anthropic"], "rule_count": 10},
        ...     metadata={"version": "week2", "environment": "development"}
        ... )
    """
    log_path = _get_log_file_path()
    
    # Create log entry
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        "data": data,
        "metadata": metadata or {}
    }
    
    # Append to JSONL file
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        
        logger.debug(f"Logged event: {event_type}")
    except Exception as e:
        logger.error(f"Failed to log event {event_type}: {e}", exc_info=True)
        raise
    
    # TODO: Week 9 - Add Arweave pinning here for immutable storage


def get_recent_logs(limit: int = 100) -> List[Dict]:
    """
    Retrieve the most recent log entries from the event log.
    
    Args:
        limit: Maximum number of entries to retrieve (default: 100)
        
    Returns:
        List of log entry dictionaries, most recent first
        
    Example:
        >>> logs = get_recent_logs(limit=10)
        >>> for log in logs:
        ...     print(f"{log['timestamp']}: {log['type']}")
    """
    log_path = _get_log_file_path()
    
    if not log_path.exists():
        logger.warning(f"Log file does not exist: {log_path}")
        return []
    
    entries = []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            # Read all lines
            lines = f.readlines()
            
            # Parse JSON from each line (JSONL format)
            for line in lines:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        entries.append(entry)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse log entry: {e}")
                        continue
        
        # Return most recent entries first
        entries.reverse()
        return entries[:limit]
        
    except Exception as e:
        logger.error(f"Failed to read log file: {e}", exc_info=True)
        return []

