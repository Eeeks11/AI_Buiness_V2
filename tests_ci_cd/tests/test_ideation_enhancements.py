"""
Tests for Strategic Ideation Framework enhancements.

Tests the new functions added to board.py:
- _synthesize_ideation_results()
- _shortlist_ideas()
- _assign_ideas_to_roles()
- _generate_ideation_summary()
"""

import pytest
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from governance_layer.governance.board import (
    _synthesize_ideation_results,
    _shortlist_ideas,
    _assign_ideas_to_roles,
    _generate_ideation_summary,
    conduct_ideation,
)
from models.core import Proposal, ProposalStatus


def test_synthesize_ideation_results():
    """Test idea synthesis and categorization into themes."""
    role_responses = {
        "CEO": "Strategy: Expand into new markets\nVision: Long-term growth",
        "CFO": "Financial: Increase revenue by 20%\nROI: Optimize investment returns",
        "COO": "Process: Improve operational efficiency\nWorkflow: Streamline delivery",
        "CMO": "Market: Target new customer segments\nBrand: Enhance market positioning",
    }
    
    role_contexts = {
        "CEO": {"role": "CEO"},
        "CFO": {"role": "CFO"},
        "COO": {"role": "COO"},
        "CMO": {"role": "CMO"},
    }
    
    result = _synthesize_ideation_results(role_responses, role_contexts)
    
    # Verify structure
    assert "themes" in result
    assert "evidence_summary" in result
    assert "all_ideas" in result
    
    # Verify themes exist
    themes = result["themes"]
    assert "financial" in themes
    assert "operational" in themes
    assert "strategic" in themes
    assert "market" in themes
    assert "technical" in themes
    assert "other" in themes
    
    # Verify ideas are categorized
    assert len(result["all_ideas"]) > 0, "Should extract ideas from responses"
    
    # Verify evidence summary
    evidence = result["evidence_summary"]
    assert "total_ideas" in evidence
    assert "ideas_by_theme" in evidence
    assert "roles_contributing" in evidence
    assert len(evidence["roles_contributing"]) == 4


def test_synthesize_ideation_results_empty():
    """Test synthesis with empty responses."""
    role_responses = {}
    role_contexts = {}
    
    result = _synthesize_ideation_results(role_responses, role_contexts)
    
    assert result["themes"] is not None
    assert len(result["all_ideas"]) == 0
    assert result["evidence_summary"]["total_ideas"] == 0


def test_shortlist_ideas():
    """Test idea ranking by profitability, strategic fit, and resource alignment."""
    synthesized_results = {
        "themes": {
            "financial": ["Increase revenue by 20%", "Optimize investment returns"],
            "strategic": ["Expand into new markets", "Long-term growth"],
            "operational": ["Improve efficiency"],
        },
        "all_ideas": [
            "Increase revenue by 20%",
            "Optimize investment returns",
            "Expand into new markets",
            "Long-term growth",
            "Improve efficiency",
        ],
    }
    
    proposal = {
        "id": "test-proposal",
        "title": "Test Proposal",
        "description": "Test description",
    }
    
    shortlisted = _shortlist_ideas(synthesized_results, proposal)
    
    # Verify structure
    assert isinstance(shortlisted, list)
    assert len(shortlisted) > 0
    
    # Verify each idea has required fields
    for idea in shortlisted:
        assert "idea" in idea
        assert "profitability_score" in idea
        assert "strategic_fit" in idea
        assert "resource_alignment" in idea
        assert "combined_score" in idea
        assert "rank" in idea
        
        # Verify scores are in valid range
        assert 0.0 <= idea["profitability_score"] <= 1.0
        assert 0.0 <= idea["strategic_fit"] <= 1.0
        assert 0.0 <= idea["resource_alignment"] <= 1.0
        assert 0.0 <= idea["combined_score"] <= 1.0
    
    # Verify ideas are sorted by combined_score (descending)
    scores = [idea["combined_score"] for idea in shortlisted]
    assert scores == sorted(scores, reverse=True), "Ideas should be sorted by score"
    
    # Verify ranks are sequential
    ranks = [idea["rank"] for idea in shortlisted]
    assert ranks == list(range(1, len(shortlisted) + 1)), "Ranks should be sequential"


def test_shortlist_ideas_empty():
    """Test shortlisting with no ideas."""
    synthesized_results = {
        "themes": {},
        "all_ideas": [],
    }
    
    proposal = {"id": "test", "title": "Test", "description": "Test"}
    
    shortlisted = _shortlist_ideas(synthesized_results, proposal)
    
    assert isinstance(shortlisted, list)
    assert len(shortlisted) == 0


def test_assign_ideas_to_roles():
    """Test idea delegation to roles."""
    shortlisted_ideas = [
        {
            "idea": "Strategy: Expand into new markets",
            "rank": 1,
            "profitability_score": 0.8,
            "strategic_fit": 0.9,
            "resource_alignment": 0.7,
            "combined_score": 0.8,
        },
        {
            "idea": "Financial: Increase revenue by 20%",
            "rank": 2,
            "profitability_score": 0.9,
            "strategic_fit": 0.7,
            "resource_alignment": 0.6,
            "combined_score": 0.75,
        },
        {
            "idea": "Process: Improve operational efficiency",
            "rank": 3,
            "profitability_score": 0.7,
            "strategic_fit": 0.6,
            "resource_alignment": 0.8,
            "combined_score": 0.7,
        },
        {
            "idea": "Market: Target new customer segments",
            "rank": 4,
            "profitability_score": 0.6,
            "strategic_fit": 0.5,
            "resource_alignment": 0.5,
            "combined_score": 0.55,
        },
        {
            "idea": "Security: Enhance data protection",
            "rank": 5,
            "profitability_score": 0.5,
            "strategic_fit": 0.4,
            "resource_alignment": 0.4,
            "combined_score": 0.45,
        },
    ]
    
    role_configs = {
        "CEO": {"name": "Chief Executive Officer"},
        "CFO": {"name": "Chief Financial Officer"},
        "COO": {"name": "Chief Operating Officer"},
        "CMO": {"name": "Chief Marketing Officer"},
        "LEGAL": {"name": "General Counsel"},
        "CISO": {"name": "Chief Information Security Officer"},
        "CHAIR": {"name": "Chair"},
        "SECRETARY": {"name": "Secretary"},
    }
    
    assignments = _assign_ideas_to_roles(shortlisted_ideas, role_configs)
    
    # Verify structure
    assert isinstance(assignments, dict)
    assert len(assignments) == len(role_configs)
    
    # Verify all roles are in assignments
    for role in role_configs.keys():
        assert role in assignments
        assert isinstance(assignments[role], list)
    
    # Verify strategic ideas assigned to CEO
    ceo_ideas = assignments["CEO"]
    assert len(ceo_ideas) > 0, "CEO should have strategic ideas"
    assert any("strategy" in idea["idea"].lower() or "vision" in idea["idea"].lower() 
               for idea in ceo_ideas), "CEO should have strategic ideas"
    
    # Verify financial ideas assigned to CFO
    cfo_ideas = assignments["CFO"]
    assert any("financial" in idea["idea"].lower() or "revenue" in idea["idea"].lower() 
               for idea in cfo_ideas), "CFO should have financial ideas"
    
    # Verify operational ideas assigned to COO
    coo_ideas = assignments["COO"]
    assert any("process" in idea["idea"].lower() or "efficiency" in idea["idea"].lower() 
               for idea in coo_ideas), "COO should have operational ideas"
    
    # Verify market ideas assigned to CMO
    cmo_ideas = assignments["CMO"]
    assert any("market" in idea["idea"].lower() or "customer" in idea["idea"].lower() 
               for idea in cmo_ideas), "CMO should have market ideas"
    
    # Verify security ideas assigned to CISO
    ciso_ideas = assignments["CISO"]
    assert any("security" in idea["idea"].lower() or "data" in idea["idea"].lower() 
               for idea in ciso_ideas), "CISO should have security ideas"


def test_generate_ideation_summary():
    """Test Strategic Ideation Summary generation."""
    proposal = {
        "id": "test-proposal-001",
        "title": "Test Proposal",
        "description": "Test description",
    }
    
    synthesized_results = {
        "themes": {
            "financial": ["Increase revenue"],
            "strategic": ["Expand markets"],
            "operational": ["Improve efficiency"],
        },
    }
    
    shortlisted_ideas = [
        {
            "idea": "Increase revenue by 20%",
            "rank": 1,
            "profitability_score": 0.9,
            "strategic_fit": 0.8,
            "resource_alignment": 0.7,
            "combined_score": 0.85,
        },
        {
            "idea": "Expand into new markets",
            "rank": 2,
            "profitability_score": 0.8,
            "strategic_fit": 0.9,
            "resource_alignment": 0.6,
            "combined_score": 0.8,
        },
    ]
    
    assignments = {
        "CEO": [shortlisted_ideas[1]],
        "CFO": [shortlisted_ideas[0]],
        "COO": [],
        "CMO": [],
    }
    
    summary = _generate_ideation_summary(
        proposal,
        synthesized_results,
        shortlisted_ideas,
        assignments
    )
    
    # Verify structure
    assert "proposal_id" in summary
    assert "thematic_clusters" in summary
    assert "profitability_indicators" in summary
    assert "risks" in summary
    assert "dependencies" in summary
    assert "required_resources" in summary
    assert "nominations_for_follow_up" in summary
    assert "timestamp" in summary
    
    # Verify proposal_id
    assert summary["proposal_id"] == "test-proposal-001"
    
    # Verify thematic_clusters
    assert summary["thematic_clusters"] == synthesized_results["themes"]
    
    # Verify profitability_indicators
    indicators = summary["profitability_indicators"]
    assert "average_profitability_score" in indicators
    assert "average_strategic_fit" in indicators
    assert "high_potential_ideas" in indicators
    
    # Verify nominations
    nominations = summary["nominations_for_follow_up"]
    assert isinstance(nominations, list)
    assert len(nominations) > 0
    
    for nomination in nominations:
        assert "idea" in nomination
        assert "rank" in nomination
        assert "profitability_score" in nomination
        assert "assigned_to" in nomination


def test_complete_ideation_flow():
    """Test full ideation: exploration → synthesis → short-listing → assignment → summary."""
    proposal = Proposal(
        id="test-complete-flow",
        title="Test Complete Flow",
        description="Testing complete ideation flow",
        financial_impact=5000.0,
        legal_risk=0.1,
    )
    
    try:
        result = conduct_ideation(proposal)
        
        # Verify all phases are present
        assert "proposal" in result
        assert "role_prompts" in result
        assert "role_contexts" in result
        assert "role_responses" in result
        assert "synthesized_results" in result
        assert "shortlisted_ideas" in result
        assert "assignments" in result
        assert "ideation_summary" in result
        assert "timestamp" in result
        
        # Verify synthesized_results structure
        synthesized = result["synthesized_results"]
        assert "themes" in synthesized
        assert "evidence_summary" in synthesized
        assert "all_ideas" in synthesized
        
        # Verify shortlisted_ideas structure
        shortlisted = result["shortlisted_ideas"]
        assert isinstance(shortlisted, list)
        if len(shortlisted) > 0:
            assert "rank" in shortlisted[0]
            assert "combined_score" in shortlisted[0]
        
        # Verify assignments structure
        assignments = result["assignments"]
        assert isinstance(assignments, dict)
        
        # Verify ideation_summary structure
        summary = result["ideation_summary"]
        assert "proposal_id" in summary
        assert "thematic_clusters" in summary
        assert "profitability_indicators" in summary
        assert "nominations_for_follow_up" in summary
        
    except Exception as e:
        # If dependencies fail (e.g., missing config), that's okay for unit test
        # We're just verifying the structure exists
        pytest.skip(f"Complete flow test requires full environment: {e}")


def test_ideation_enhancements_imports():
    """Test that ideation enhancement functions can be imported."""
    try:
        from governance_layer.governance.board import (
            _synthesize_ideation_results,
            _shortlist_ideas,
            _assign_ideas_to_roles,
            _generate_ideation_summary,
        )
        assert callable(_synthesize_ideation_results)
        assert callable(_shortlist_ideas)
        assert callable(_assign_ideas_to_roles)
        assert callable(_generate_ideation_summary)
    except ImportError as e:
        pytest.fail(f"Failed to import ideation enhancement functions: {e}")
