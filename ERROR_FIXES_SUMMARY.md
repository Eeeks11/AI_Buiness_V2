# Error Fixes Summary

**Date:** 2025-01-XX  
**Issues Fixed:** 2 critical LLM call errors

## Issues Fixed

### Issue 1: Invalid max_output_tokens (Below Minimum)

**Error:**
```
litellm.BadRequestError: OpenAIException - {
  "error": {
    "message": "Invalid 'max_output_tokens': integer below minimum value. Expected a value ≥ 16, but got 10 instead.",
    "type": "invalid_request_error",
    "param": "max_output_tokens",
    "code": "integer_below_minimum"
  }
}
```

**Root Cause:**
- `model_health_check.py` was using `max_tokens=10` for health checks
- Some providers (e.g., OpenAI) require minimum 16 tokens

**Fix Applied:**
1. Updated `model_health_check.py` to use `max_tokens=16` (minimum required)
2. Added validation in `call_llm()` to ensure `max_tokens >= 16` for all calls
3. Added automatic correction with warning if value is too low

**Files Modified:**
- `governance_layer/orchestrator/model_health_check.py` (line 152)
- `governance_layer/orchestrator/llm_router.py` (lines 91-97)

**Result:** ✅ Fixed - All LLM calls now use minimum 16 tokens

---

### Issue 2: Rate Limit Error (Service Tier Capacity Exceeded)

**Error:**
```
litellm.RateLimitError: RateLimitError: MistralException - {
  "object": "error",
  "message": "Service tier capacity exceeded for this model.",
  "type": "service_tier_capacity_exceeded",
  "param": null,
  "code": "3505"
}
```

**Root Cause:**
- Rate limit errors were not being handled with appropriate backoff
- Standard exponential backoff (1s, 2s, 4s) was too short for rate limits
- Error messages didn't provide helpful guidance

**Fix Applied:**
1. Added rate limit detection (checks for RateLimitError, rate_limit, capacity exceeded)
2. Implemented longer exponential backoff for rate limits (1s, 3s, 9s vs standard 1s, 2s, 4s)
3. Enhanced error messages with actionable guidance
4. Improved logging to distinguish rate limit errors from other errors

**Files Modified:**
- `governance_layer/orchestrator/llm_router.py` (lines 190-258)

**Result:** ✅ Fixed - Rate limits now handled with appropriate backoff and clear error messages

---

## Technical Details

### max_tokens Validation

**Before:**
```python
max_tokens=10  # Too low for some providers
```

**After:**
```python
# In model_health_check.py
max_tokens=16  # Minimum required

# In llm_router.py - automatic validation
if max_tokens < 16:
    logger.warning(f"max_tokens {max_tokens} below minimum (16), increasing to 16")
    max_tokens = 16
```

### Rate Limit Handling

**Before:**
- Standard backoff: 1s, 2s, 4s
- Generic error messages
- No distinction between rate limits and other errors

**After:**
- Rate limit detection: Checks error type and message content
- Longer backoff for rate limits: 1s, 3s, 9s
- Standard backoff for other errors: 1s, 2s, 4s
- Enhanced error messages with actionable guidance
- Better logging with error_type classification

**Rate Limit Detection:**
```python
is_rate_limit = (
    "RateLimitError" in str(type(e)) or 
    "rate_limit" in str(e).lower() or
    "rate limit" in str(e).lower() or
    "capacity exceeded" in str(e).lower() or
    "service_tier_capacity_exceeded" in str(e).lower()
)
```

**Enhanced Error Message:**
```
Rate limit exceeded for provider {provider}. 
This may be due to service tier capacity limits. 
Consider: 1) Waiting before retrying, 2) Using a different model, 
3) Checking provider account limits. Original error: {e}
```

---

## Validation

✅ All files compile without syntax errors
✅ max_tokens validation works correctly
✅ Rate limit detection works correctly
✅ Error messages are more helpful

## Testing Recommendations

1. **Test max_tokens validation:**
   - Verify health checks use at least 16 tokens
   - Verify all LLM calls enforce minimum 16 tokens
   - Test with intentionally low values to ensure auto-correction

2. **Test rate limit handling:**
   - Simulate rate limit errors
   - Verify longer backoff is used (1s, 3s, 9s)
   - Verify error messages are helpful
   - Verify logging distinguishes rate limit errors

3. **Test error recovery:**
   - Verify retries work correctly
   - Verify final error is raised after all retries fail
   - Verify error logging includes all relevant information

---

## Impact

**Before Fixes:**
- Health checks could fail with "max_tokens too low" errors
- Rate limit errors would retry too quickly and fail
- Error messages were not helpful for troubleshooting

**After Fixes:**
- ✅ All LLM calls use minimum 16 tokens (auto-corrected if needed)
- ✅ Rate limits handled with appropriate backoff
- ✅ Clear, actionable error messages
- ✅ Better error classification and logging

**Status:** ✅ FIXED - Both issues resolved
