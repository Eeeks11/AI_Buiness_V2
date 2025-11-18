# LLM Model Health Check Implementation

**Date**: 2025-01-XX  
**Status**: ✅ **COMPLETE**

---

## Overview

Implemented a comprehensive LLM model health check system that validates model availability before running governance cycles. The system identifies why models are unavailable and displays diagnostic information on the dashboard.

---

## Features Implemented

### 1. Model Health Check Module
**File**: `governance_layer/orchestrator/model_health_check.py`

**Key Components:**
- **`ModelHealthStatus` class**: Stores health status for individual models
  - Provider identifier
  - Model name
  - Health status (healthy/unhealthy)
  - Error message and error type
  - Response time
  - Timestamp

- **`check_model_health()`**: Tests a single model
  - Performs minimal test API call
  - Measures response time
  - Classifies errors into categories:
    - `api_key_missing`: API key invalid or missing
    - `network_error`: Connectivity issues
    - `rate_limit`: Rate limit exceeded
    - `model_not_found`: Model doesn't exist
    - `service_unavailable`: Service down/maintenance
    - `billing_error`: Billing/quota issues
    - `unknown_error`: Other errors

- **`check_all_models_health()`**: Checks all configured models
  - Iterates through all active models
  - Performs health check for each
  - Logs results to audit trail (Rule 6)
  - Returns dictionary of health statuses

- **`validate_models_before_governance()`**: Validates models before governance cycle
  - Checks if minimum 5 models are healthy (Rule 8)
  - Returns validation result, health statuses, and error messages
  - Used by governance cycle to prevent failures

- **`get_model_health_summary()`**: Quick summary for dashboard
  - Fast health check (3s timeout)
  - Returns summary with counts and model details
  - Used by dashboard for display

---

### 2. Governance Cycle Integration
**File**: `governance_layer/orchestrator/langgraph_state_machine.py`

**Changes:**
- Added health check validation at the start of `conduct_ideation()`
- Validates that at least 5 models are healthy before proceeding
- Raises `ConstitutionalError` if insufficient healthy models
- Stores health check results in state for dashboard display
- Prevents governance cycle from starting if models are down

**Flow:**
```
IDEATION Phase Start
  ↓
Validate Models (minimum 5 healthy)
  ↓
If insufficient → Raise ConstitutionalError
  ↓
If sufficient → Store results in state → Continue ideation
```

---

### 3. Dashboard Integration
**File**: `owner_control/dashboard/app.py`

**New Features:**

#### A. Model Health Tab (New Tab 4)
- **Header**: "🤖 LLM Model Health Status"
- **Refresh Button**: Manual health check trigger
- **Overall Metrics**:
  - Total Models count
  - Healthy count with delta (unhealthy count)
  - Can Run Governance status (Yes/No with color indicator)

- **Detailed Model Status**:
  - For each model:
    - Status icon (✅/❌)
    - Provider name and model name
    - Health status badge (Healthy/Unhealthy)
    - Response time (if healthy)
    - Error details (if unhealthy) with color-coded error types:
      - 🔑 API Key Issue (red)
      - 🌐 Network Error (yellow)
      - ⏱️ Rate Limit (yellow)
      - 🔍 Model Not Found (red)
      - 🔧 Service Unavailable (yellow)
      - 💳 Billing Issue (red)
      - ❓ Unknown Error (red)
    - Check timestamp

- **Warning Message**: If governance cannot run, displays warning with count

#### B. Sidebar Health Indicator
- Quick health status in sidebar
- Shows "✅ X/Y Healthy" or "❌ X/Y Healthy"
- Warning caption if governance may fail
- Updates automatically on page load

#### C. Proposal Creation Warnings
- **Before Form**: Checks health and displays warning if insufficient models
- **After Creation**: Double-checks before running governance cycle
- Prevents cycle from starting if models are unhealthy
- Clear error messages directing user to Model Health tab

---

## Error Classification

The system classifies errors into user-friendly categories:

| Error Type | Description | Common Causes |
|-----------|-------------|---------------|
| `api_key_missing` | API key invalid or missing | Missing env var, expired key, wrong key |
| `network_error` | Connectivity issues | No internet, DNS failure, firewall |
| `rate_limit` | Rate limit exceeded | Too many requests, quota exceeded |
| `model_not_found` | Model doesn't exist | Wrong model name, model deprecated |
| `service_unavailable` | Service down/maintenance | Provider outage, maintenance window |
| `billing_error` | Billing/quota issues | Insufficient credits, payment failed |
| `unknown_error` | Other errors | Unexpected errors, parse failures |

---

## Constitutional Compliance

- **Rule 6 (Full Transparency)**: All health checks are logged to audit trail
- **Rule 8 (Minimum 5 Models)**: Validation enforces minimum 5 healthy models
- **Rule 10 (Owner Authority)**: Dashboard displays health status for owner review

---

## Usage

### For Users (Dashboard)
1. **Check Model Health**: Go to "🤖 Model Health" tab
2. **View Status**: See overall metrics and detailed model status
3. **Identify Issues**: Error messages explain why models are unhealthy
4. **Fix Issues**: Based on error type, fix API keys, network, etc.
5. **Create Proposals**: System warns if models are unhealthy

### For Developers
```python
from governance_layer.orchestrator.model_health_check import (
    check_model_health,
    check_all_models_health,
    validate_models_before_governance,
    get_model_health_summary
)

# Check single model
status = check_model_health("openai/gpt-4o")
print(f"Healthy: {status.is_healthy}, Error: {status.error}")

# Check all models
all_statuses = check_all_models_health()

# Validate before governance
is_valid, health_results, errors = validate_models_before_governance()
if not is_valid:
    print(f"Errors: {errors}")

# Get summary for dashboard
summary = get_model_health_summary()
print(f"Healthy: {summary['healthy_count']}/{summary['total_models']}")
```

---

## Performance

- **Health Check Timeout**: 5 seconds per model (configurable)
- **Dashboard Check Timeout**: 3 seconds per model (faster for UI)
- **Parallel Checks**: Can be optimized to run in parallel (future enhancement)
- **Caching**: Results not cached (always fresh, but can add caching if needed)

---

## Testing

### Manual Testing Steps:
1. **Start Dashboard**: Run Streamlit app
2. **Check Health Tab**: Navigate to "🤖 Model Health" tab
3. **Verify Display**: Check that all models show status
4. **Test Unhealthy Model**: 
   - Remove/invalidate an API key
   - Refresh health check
   - Verify error message appears
5. **Test Governance Block**:
   - Ensure < 5 models healthy
   - Try to create proposal
   - Verify warning appears
   - Verify cycle doesn't start

---

## Files Modified/Created

### Created:
1. **`governance_layer/orchestrator/model_health_check.py`** (364 lines)
   - Complete health check system
   - ModelHealthStatus class
   - Health check functions
   - Error classification
   - Dashboard summary function

### Modified:
1. **`governance_layer/orchestrator/langgraph_state_machine.py`**
   - Added health check import
   - Added validation in `conduct_ideation()`
   - Stores health check results in state

2. **`owner_control/dashboard/app.py`**
   - Added health check import
   - Added "🤖 Model Health" tab
   - Added sidebar health indicator
   - Added proposal creation warnings

---

## Future Enhancements

1. **Parallel Health Checks**: Run checks in parallel for faster results
2. **Health Check Caching**: Cache results for 30-60 seconds to reduce API calls
3. **Automatic Retry**: Auto-retry failed models after delay
4. **Health History**: Track health over time, show trends
5. **Alert System**: Notify owner when models go down
6. **Fallback Models**: Automatically switch to backup models if primary fails
7. **Health Check API**: REST endpoint for external monitoring

---

## Error Messages Examples

### API Key Missing:
```
🔑 API Key Issue: API key missing or invalid: Invalid API key provided
```

### Network Error:
```
🌐 Network Error: Network connectivity issue: Connection timeout
```

### Rate Limit:
```
⏱️ Rate Limit: Rate limit exceeded: Too many requests
```

### Model Not Found:
```
🔍 Model Not Found: Model not found or unavailable: Model 'gpt-5' not found
```

---

## Summary

✅ **Complete Implementation**:
- Health check module with error classification
- Governance cycle integration (blocks if unhealthy)
- Dashboard display with detailed diagnostics
- Sidebar quick status indicator
- Proposal creation warnings

✅ **Constitutional Compliance**:
- Rule 6: All checks logged
- Rule 8: Enforces minimum 5 models
- Rule 10: Owner can view status

✅ **User Experience**:
- Clear error messages
- Color-coded error types
- Actionable diagnostics
- Prevents failures before they happen

---

**Last Updated**: 2025-01-XX  
**Status**: ✅ **READY FOR USE**
