"""
Iterative Deliberation Engine

Implements multi-round iterative discussion where AI board members:
- Read and respond to each other's arguments
- Build upon good ideas from other members
- Challenge weak reasoning
- Update positions when persuaded
- Reference specific points made by others
- Continue until convergence or natural exhaustion
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from governance_layer.governance.board import get_role_provider_map, get_model_assignment
from governance_layer.orchestrator.llm_router import call_llm
from governance_layer.roles.prompt_templates import load_role_configs

logger = logging.getLogger(__name__)

BOARD_ROLES = tuple(load_role_configs().keys())


def detect_convergence(
    current_round: Dict[str, str],
    previous_round: Dict[str, str],
    min_rounds: int = 2
) -> Tuple[bool, str]:
    """
    Detect if deliberation has converged by analyzing position changes.
    
    Args:
        current_round: Current round responses (role -> response)
        previous_round: Previous round responses (role -> response)
        min_rounds: Minimum rounds before checking convergence
        
    Returns:
        Tuple of (converged: bool, reason: str)
    """
    if len(current_round) == 0 or len(previous_round) == 0:
        return False, "Insufficient data"
    
    # Check for explicit convergence phrases
    convergence_phrases = [
        "i agree with",
        "consensus",
        "no further concerns",
        "ready to vote",
        "no additional points",
        "we are aligned"
    ]
    
    convergence_count = 0
    for role, response in current_round.items():
        response_lower = response.lower()
        if any(phrase in response_lower for phrase in convergence_phrases):
            convergence_count += 1
    
    convergence_ratio = convergence_count / len(current_round) if current_round else 0
    
    if convergence_ratio > 0.6:
        return True, f"High convergence language detected ({convergence_ratio:.0%} of responses)"
    
    # Check for significant position changes (simplified - look for approve/reject keywords)
    position_changes = 0
    for role in current_round.keys():
        if role not in previous_round:
            continue
        
        current_lower = current_round[role].lower()
        previous_lower = previous_round[role].lower()
        
        # Simple heuristic: check if approve/reject sentiment changed
        current_approve = "approve" in current_lower or "support" in current_lower
        current_reject = "reject" in current_lower or "oppose" in current_lower
        previous_approve = "approve" in previous_lower or "support" in previous_lower
        previous_reject = "reject" in previous_lower or "oppose" in previous_lower
        
        if (current_approve != previous_approve) or (current_reject != previous_reject):
            position_changes += 1
    
    # If fewer than 2 members changed position, consider converged
    if position_changes < 2 and len(current_round) >= min_rounds:
        return True, f"Few position changes ({position_changes} members changed)"
    
    return False, "No convergence detected"


def detect_exhaustion(
    current_round: Dict[str, str],
    previous_round: Dict[str, str],
    all_rounds: List[Dict[str, str]]
) -> Tuple[bool, str]:
    """
    Detect if discussion has naturally exhausted.
    
    Args:
        current_round: Current round responses
        previous_round: Previous round responses
        all_rounds: All previous rounds
        
    Returns:
        Tuple of (exhausted: bool, reason: str)
    """
    if len(current_round) == 0 or len(previous_round) == 0:
        return False, "Insufficient data"
    
    # Calculate average response length
    current_avg_length = sum(len(r) for r in current_round.values()) / len(current_round) if current_round else 0
    previous_avg_length = sum(len(r) for r in previous_round.values()) / len(previous_round) if previous_round else 0
    
    # Check for significant drop in response length (>40% decrease)
    if previous_avg_length > 0:
        length_ratio = current_avg_length / previous_avg_length
        if length_ratio < 0.6:
            return True, f"Response length dropped significantly ({length_ratio:.0%} of previous)"
    
    # Check for convergence phrases (indicates natural conclusion)
    convergence_phrases = [
        "ready to vote",
        "no additional points",
        "no further discussion needed"
    ]
    
    exhaustion_count = 0
    for response in current_round.values():
        response_lower = response.lower()
        if any(phrase in response_lower for phrase in convergence_phrases):
            exhaustion_count += 1
    
    if exhaustion_count > len(current_round) * 0.6:
        return True, f"High exhaustion language ({exhaustion_count}/{len(current_round)} responses)"
    
    return False, "No exhaustion detected"


def build_iterative_prompt(
    role: str,
    proposal: Dict[str, Any],
    round_number: int,
    all_previous_rounds: List[Dict[str, str]],
    role_context: Dict[str, Any]
) -> str:
    """
    Build a prompt for iterative deliberation that includes all previous rounds.
    
    Args:
        role: Board role identifier
        proposal: Proposal dictionary
        round_number: Current round number (1-indexed)
        all_previous_rounds: List of all previous rounds (each is role -> response dict)
        role_context: Context from memory system
        
    Returns:
        Prompt string for the role
    """
    base_prompt = (
        f"You are the {role} on the AI governance board.\n\n"
        f"Proposal ID: {proposal.get('id', 'UNKNOWN')}\n"
        f"Title: {proposal.get('title', 'No title')}\n"
        f"Description: {proposal.get('description', 'No description')}\n"
        f"Financial Impact: ${proposal.get('financial_impact', 0):,.2f}\n\n"
    )
    
    if round_number == 1:
        # Round 1: Initial analysis, no previous context
        base_prompt += (
            f"This is ROUND 1 of deliberation.\n"
            f"Provide your initial analysis from your domain perspective.\n"
            f"Identify opportunities, risks, questions, and your initial recommendation.\n\n"
        )
    else:
        # Round 2+: Include all previous rounds
        base_prompt += (
            f"This is ROUND {round_number} of deliberation.\n"
            f"You have seen responses from all board members in previous rounds.\n\n"
            f"PREVIOUS ROUNDS:\n"
        )
        
        for prev_round_num, prev_round in enumerate(all_previous_rounds, 1):
            base_prompt += f"\n--- ROUND {prev_round_num} ---\n"
            for other_role, other_response in prev_round.items():
                base_prompt += f"\n{other_role}:\n{other_response[:500]}\n"
        
        base_prompt += (
            f"\n\nYour task in this round:\n"
            f"- Respond to specific arguments raised by other members\n"
            f"- Reference other members by name when agreeing or disagreeing (e.g., 'I agree with CFO's point about...')\n"
            f"- Update your position if you've been persuaded by valid concerns\n"
            f"- Challenge reasoning you disagree with and explain why\n"
            f"- Build on good ideas from others\n"
            f"- Raise new concerns if others missed something\n\n"
        )
    
    # Add role-specific instructions
    if role == "CHAIR":
        base_prompt += (
            f"As CHAIR, facilitate discussion, synthesize key points, and ensure all perspectives are considered.\n"
        )
    elif role == "SECRETARY":
        base_prompt += (
            f"As SECRETARY, document the discussion process and key points raised.\n"
        )
    elif role in ["LEGAL", "CISO"]:
        base_prompt += (
            f"As {role}, focus on {'legal/constitutional compliance' if role == 'LEGAL' else 'security/data risks'}.\n"
        )
    else:
        base_prompt += (
            f"As {role}, provide your domain expertise and voting perspective.\n"
        )
    
    return base_prompt


def conduct_iterative_deliberation(
    proposal: Dict[str, Any],
    role_contexts: Dict[str, Dict[str, Any]],
    max_rounds: int = 5,
    mode: str = "full"
) -> Dict[str, Any]:
    """
    Conduct iterative multi-round deliberation.
    
    Args:
        proposal: Proposal dictionary
        role_contexts: Dictionary mapping roles to their context data
        max_rounds: Maximum number of rounds (5 for ideation, 2 for proposals)
        mode: "full" for ideation (many rounds) or "streamlined" for proposals (fewer rounds)
        
    Returns:
        Dictionary containing:
        - rounds: List of round responses
        - total_rounds: Number of rounds completed
        - converged: Whether convergence was detected
        - exhausted: Whether discussion exhausted
        - position_evolution: How positions changed
        - synthesis: Summary of deliberation
    """
    if mode == "streamlined":
        max_rounds = min(max_rounds, 2)  # Limit to 2 rounds for proposals
    
    logger.info(
        f"Starting iterative deliberation",
        extra={
            "proposal_id": proposal.get("id"),
            "max_rounds": max_rounds,
            "mode": mode
        }
    )
    
    role_providers = get_role_provider_map()
    all_rounds: List[Dict[str, str]] = []
    position_evolution: Dict[str, List[str]] = {role: [] for role in BOARD_ROLES}
    
    converged = False
    exhausted = False
    convergence_reason = ""
    exhaustion_reason = ""
    
    for round_num in range(1, max_rounds + 1):
        logger.info(f"Deliberation Round {round_num}/{max_rounds}", extra={"proposal_id": proposal.get("id")})
        
        round_responses: Dict[str, str] = {}
        
        # Get responses from all roles for this round
        for role in BOARD_ROLES:
            role_context = role_contexts.get(role, {})
            
            # Build iterative prompt with previous rounds
            prompt = build_iterative_prompt(
                role=role,
                proposal=proposal,
                round_number=round_num,
                all_previous_rounds=all_rounds,
                role_context=role_context
            )
            
            provider = role_providers.get(role)
            if not provider:
                logger.error(f"No provider for {role}", extra={"proposal_id": proposal.get("id")})
                continue
            
            # Get model-specific configuration
            model_config = get_model_assignment(role)
            temperature = model_config.get("temperature", 0.7) if model_config else 0.7
            max_tokens = model_config.get("max_tokens", 2000) if model_config else 2000
            
            try:
                response = call_llm(
                    provider=provider,
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                if not response or len(response.strip()) == 0:
                    logger.warning(f"Empty response from {role} in round {round_num}")
                    response = f"{role} deliberation: No response in round {round_num}"
                
                round_responses[role] = response
                
                # Track position evolution (simplified - extract approve/reject sentiment)
                response_lower = response.lower()
                if "approve" in response_lower or "support" in response_lower:
                    position_evolution[role].append("APPROVE")
                elif "reject" in response_lower or "oppose" in response_lower:
                    position_evolution[role].append("REJECT")
                else:
                    position_evolution[role].append("NEUTRAL")
                
            except Exception as e:
                logger.error(f"Failed to get response from {role} in round {round_num}: {e}", exc_info=True)
                round_responses[role] = f"{role} deliberation error: {str(e)}"
        
        all_rounds.append(round_responses)
        
        # Check for convergence (after at least 2 rounds)
        if round_num >= 2:
            converged, convergence_reason = detect_convergence(
                current_round=round_responses,
                previous_round=all_rounds[-2],
                min_rounds=2
            )
            
            if converged:
                logger.info(
                    f"Convergence detected in round {round_num}",
                    extra={"reason": convergence_reason, "proposal_id": proposal.get("id")}
                )
                break
        
        # Check for exhaustion
        if round_num >= 2:
            exhausted, exhaustion_reason = detect_exhaustion(
                current_round=round_responses,
                previous_round=all_rounds[-2],
                all_rounds=all_rounds[:-1]
            )
            
            if exhausted:
                logger.info(
                    f"Discussion exhausted in round {round_num}",
                    extra={"reason": exhaustion_reason, "proposal_id": proposal.get("id")}
                )
                break
    
    # Generate synthesis
    synthesis = _generate_deliberation_synthesis(
        proposal=proposal,
        all_rounds=all_rounds,
        position_evolution=position_evolution,
        converged=converged,
        exhausted=exhausted
    )
    
    return {
        "rounds": all_rounds,
        "total_rounds": len(all_rounds),
        "converged": converged,
        "exhausted": exhausted,
        "convergence_reason": convergence_reason if converged else None,
        "exhaustion_reason": exhaustion_reason if exhausted else None,
        "position_evolution": position_evolution,
        "synthesis": synthesis,
        "timestamp": datetime.now().isoformat()
    }


def _generate_deliberation_synthesis(
    proposal: Dict[str, Any],
    all_rounds: List[Dict[str, str]],
    position_evolution: Dict[str, List[str]],
    converged: bool,
    exhausted: bool
) -> Dict[str, Any]:
    """
    Generate a synthesis of the iterative deliberation.
    
    Args:
        proposal: Proposal dictionary
        all_rounds: All rounds of deliberation
        position_evolution: How each role's position evolved
        converged: Whether convergence was reached
        exhausted: Whether discussion exhausted
        
    Returns:
        Synthesis dictionary
    """
    # Count position changes
    position_changes = {}
    for role, positions in position_evolution.items():
        changes = 0
        for i in range(1, len(positions)):
            if positions[i] != positions[i-1]:
                changes += 1
        position_changes[role] = changes
    
    # Identify members who changed position
    members_who_changed = [
        role for role, changes in position_changes.items() if changes > 0
    ]
    
    # Extract final positions
    final_positions = {}
    for role, positions in position_evolution.items():
        if positions:
            final_positions[role] = positions[-1]
        else:
            final_positions[role] = "UNKNOWN"
    
    return {
        "proposal_id": proposal.get("id"),
        "rounds_conducted": len(all_rounds),
        "converged": converged,
        "exhausted": exhausted,
        "members_who_changed_position": members_who_changed,
        "position_changes": position_changes,
        "final_positions": final_positions,
        "summary": f"Conducted {len(all_rounds)} rounds of deliberation. "
                   f"{'Converged' if converged else 'Exhausted' if exhausted else 'Completed'} "
                   f"with {len(members_who_changed)} members changing position."
    }
