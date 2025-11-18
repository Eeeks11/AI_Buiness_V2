# Investigation Notes - Dashboard & Approval Workflow Issues

**Date**: 2025-01-XX

## Problem 1: Dashboard Shows Wrong/Missing Data

### Root Cause Analysis

**Issue**: Dashboard displays "Unknown Proposal" and empty fields

**Investigation Findings:**

1. **Data Retrieval Logic** (`data_retrieval.py::get_all_proposals()`):
   - Function looks for proposal data in log events
   - Defaults to "Unknown Proposal" when title not found: `data.get("title", "Unknown Proposal")`
   - Problem: When governance cycle runs, proposal data might be in `state["proposal"]` but not logged with all fields

2. **Proposal Creation** (`app.py::_create_proposal_form()`):
   - Creates proposal dict and logs as "proposal_created" event
   - But when `run_governance_cycle()` is called, it passes the proposal dict directly
   - The state machine stores it in `state["proposal"]` but may not log all fields

3. **Data Source Mismatch**:
   - Dashboard reads from logs via `get_recent_logs()`
   - But proposal data might be in state machine state, not fully logged
   - Need to ensure proposal data is logged with all fields at creation

**Fix Required:**
- Ensure proposal data is logged with all fields when created
- Update `get_all_proposals()` to also check for proposal data in state machine results
- Add fallback to read from proposal files if they exist

---

## Problem 2: Owner Approval Workflow Incomplete

### Root Cause Analysis

**Issue**: Proposal tries to execute immediately after voting, hits Rule 10 error, gets stuck

**Investigation Findings:**

1. **Missing Status**: `ProposalStatus` enum doesn't have `PENDING_APPROVAL`
   - Current statuses: DRAFT, DELIBERATION, VOTING, APPROVED, REJECTED, VETOED, EXECUTED
   - Need to add: PENDING_APPROVAL

2. **State Machine Flow**: 
   - Current: VOTING → EXECUTION → RETROSPECTIVE
   - Should be: VOTING → PENDING_APPROVAL → (wait for owner) → EXECUTION → RETROSPECTIVE

3. **Execution Function** (`execute_decision()`):
   - Has `@require_owner_approval` decorator
   - But state machine tries to call it immediately after voting
   - No check to see if approval is needed before calling

4. **Voting Phase** (`conduct_voting()`):
   - Doesn't check if proposal needs owner approval
   - Doesn't set status to pending_approval
   - Just creates voting result and moves to next phase

5. **Missing Approval Phase**:
   - No `PENDING_APPROVAL` phase in `GovernancePhase` enum
   - No function to handle pending approval state
   - No way to resume from pending approval

**Fix Required:**
1. Add `PENDING_APPROVAL` to `ProposalStatus` enum
2. Add `PENDING_APPROVAL` phase to `GovernancePhase` enum
3. Modify voting phase to check if approval needed and set status
4. Add conditional edge: VOTING → PENDING_APPROVAL (if approved) or VOTING → END (if rejected/vetoed)
5. Create approval handler function
6. Add approval UI to dashboard
7. Create function to resume governance cycle from pending approval

---

## Problem 3: Status Not Updating Through Governance Cycle

### Root Cause Analysis

**Issue**: Proposal status remains "draft" throughout entire cycle

**Investigation Findings:**

1. **Status Updates** (`data_retrieval.py::get_all_proposals()`):
   - Status is set based on phase: `if phase == "IDEATION": proposal["status"] = ProposalStatus.DRAFT.value`
   - But this only happens when reading from logs
   - If proposal data is updated elsewhere, status might not be synced

2. **State Machine**:
   - Doesn't explicitly update proposal status in state
   - Status is inferred from phase, not explicitly set
   - No logging of status changes

3. **Proposal Model**:
   - `Proposal` model has `status` field
   - But when using dict in state machine, status might not be updated

**Fix Required:**
1. Explicitly update proposal status at each phase transition
2. Log status changes to audit trail
3. Ensure status is persisted correctly
4. Update dashboard to read current status from logs

---

## Files That Need Modification

1. **models/core.py**:
   - Add `PENDING_APPROVAL = "pending_approval"` to `ProposalStatus` enum

2. **governance_layer/orchestrator/langgraph_state_machine.py**:
   - Add `PENDING_APPROVAL` to `GovernancePhase` enum
   - Modify `conduct_voting()` to check approval requirement and set status
   - Add conditional routing: VOTING → PENDING_APPROVAL or VOTING → END
   - Create `handle_pending_approval()` function
   - Create `resume_from_approval()` function
   - Update status at each phase

3. **owner_control/dashboard/app.py**:
   - Add "Pending Approvals" tab
   - Add approve/reject buttons
   - Connect to resume function

4. **owner_control/dashboard/data_retrieval.py**:
   - Fix `get_all_proposals()` to read proposal data correctly
   - Ensure status is read from logs correctly
   - Add better fallback for missing data

5. **governance_layer/governance/board.py**:
   - Ensure voting function returns approval requirement
   - Log status changes

---

## Test Plan

1. Create test proposal
2. Run through governance cycle
3. Verify it stops at pending_approval
4. Verify it appears in dashboard
5. Approve it
6. Verify execution proceeds
7. Verify final status is executed

---

## Next Steps

1. Add PENDING_APPROVAL status
2. Fix state machine to stop at approval
3. Fix data retrieval
4. Add approval UI
5. Test end-to-end
