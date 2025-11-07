"""
FastAPI Application Entry Point

This module provides the main FastAPI application with startup validation
and constitutional compliance checking.

On startup, the system:
1. Loads and validates constitutional rules
2. Verifies active models (Rule 8: 5+ models)
3. Validates vote weights (Rule 9: all ≤ 0.25)
4. Logs system startup event
"""

# Standard library
import logging
import sys
from pathlib import Path

# Third-party
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

# Local - models first (single source of truth)
# Add Codebase Memory to path for imports
project_root = Path(__file__).parent
codebase_memory = project_root / "Memory Systems" / "Codebase Memory"
if str(codebase_memory) not in sys.path:
    sys.path.insert(0, str(codebase_memory))

from models.core import ConstitutionalRule

# Local - configuration and logging
import importlib.util
config_path = project_root / "Config & Settings" / "config.py"
config_spec = importlib.util.spec_from_file_location("config", config_path)
config_module = importlib.util.module_from_spec(config_spec)
config_spec.loader.exec_module(config_module)
get_settings = config_module.get_settings

logger_path = project_root / "Utilities" / "logger.py"
logger_spec = importlib.util.spec_from_file_location("logger", logger_path)
logger_module = importlib.util.module_from_spec(logger_spec)
logger_spec.loader.exec_module(logger_module)
log_event = logger_module.log_event

# Local - constitution
constitution_path = project_root / "Constitutional Layer (Immutable)"
if str(constitution_path) not in sys.path:
    sys.path.insert(0, str(constitution_path))

# Import constitution module
try:
    from constitution import validate_constitutional_compliance
except ImportError:
    # Fallback if import fails
    validate_constitutional_compliance = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AI Business Governance System",
    description="Constitutional framework for autonomous AI decision-making",
    version="week2"
)


@app.on_event("startup")
async def startup_event() -> None:
    """
    Startup event handler that validates constitutional compliance.
    
    This function:
    1. Prints all 10 constitutional rules
    2. Prints active models from settings
    3. Validates constitutional compliance
    4. Logs system startup event
    """
    logger.info("Starting AI Business Governance System...")
    
    # Get settings (will validate on first access)
    try:
        settings = get_settings()
    except ValueError as e:
        logger.error(f"Settings validation failed: {e}")
        raise
    
    # Print constitutional rules
    logger.info("=" * 60)
    logger.info("CONSTITUTIONAL RULES (10 Rules)")
    logger.info("=" * 60)
    for rule in ConstitutionalRule:
        rule_name = rule.name.replace("_", " ").title()
        logger.info(f"Rule {rule.value}: {rule_name}")
    logger.info("=" * 60)
    
    # Print active models
    active_models = settings.active_models
    logger.info(f"Active Models ({len(active_models)}): {', '.join(active_models)}")
    
    # Validate constitutional compliance
    try:
        settings.validate_constitutional_compliance()
        logger.info("✓ Constitutional compliance validated")
    except ValueError as e:
        logger.error(f"✗ Constitutional compliance validation failed: {e}")
        raise
    
    # Log system startup event
    log_event(
        event_type="system_startup",
        data={
            "models": active_models,
            "model_count": len(active_models),
            "rule_count": len(ConstitutionalRule),
            "vote_weights": settings.vote_weights
        },
        metadata={
            "version": "week2",
            "status": "started"
        }
    )
    
    logger.info("System startup complete")


@app.get("/")
async def root() -> JSONResponse:
    """
    Root endpoint returning system status.
    
    Returns:
        JSON response with system status information
    """
    try:
        settings = get_settings()
        return JSONResponse({
            "status": "operational",
            "system": "AI Business Governance System",
            "version": "week2",
            "active_models": settings.active_models,
            "model_count": len(settings.active_models),
            "constitutional_rules": len(ConstitutionalRule)
        })
    except Exception as e:
        logger.error(f"Error in root endpoint: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )


@app.get("/health")
async def health_check() -> JSONResponse:
    """
    Health check endpoint.
    
    Checks:
    - models_active: bool (5+ models for Rule 8)
    - constitution_loaded: bool (10 rules)
    
    Returns:
        JSON response with health status
    """
    try:
        settings = get_settings()
        active_models = settings.active_models
        
        # Check Rule 8: Minimum 5 models
        models_active = len(active_models) >= 5
        
        # Check constitution: 10 rules
        constitution_loaded = len(ConstitutionalRule) == 10
        
        health_status = {
            "status": "healthy" if (models_active and constitution_loaded) else "unhealthy",
            "models_active": models_active,
            "model_count": len(active_models),
            "constitution_loaded": constitution_loaded,
            "rule_count": len(ConstitutionalRule),
            "checks": {
                "rule_8_compliant": models_active,
                "constitution_loaded": constitution_loaded
            }
        }
        
        status_code = 200 if health_status["status"] == "healthy" else 503
        return JSONResponse(content=health_status, status_code=status_code)
        
    except Exception as e:
        logger.error(f"Error in health check: {e}", exc_info=True)
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": str(e)
            }
        )


if __name__ == "__main__":
    """
    Run the FastAPI application using uvicorn.
    """
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )

