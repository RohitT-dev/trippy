# Quick Reference: Anti-Hallucination Guardrails

**TL;DR:** You can't guess prices in agent outputs. Use tools only. If tools have no data, output `INSUFFICIENT_DATA`.

---

## One-Minute Summary

**Problem:** LLMs make up pricing when they don't have data  
**Solution:** Temperature=0.0 + Pydantic validators + Tool-only prompting  
**Result:** Agents fail safely with `INSUFFICIENT_DATA` instead of fabricating costs

---

## For Developers Adding New Agents

### If your agent deals with pricing:
1. Add `temperature=0.0` to agent creation
2. Add explicit instruction: "NEVER estimate costs without tool data"
3. Enable `INSUFFICIENT_DATA` as a valid output option

### If you're creating a new crew with an agent that outputs prices:
1. Assign an `output_pydantic` model to the task
2. Attach a `guardrail` validator function
3. Set `guardrail_max_retries=2`

### Example:
```python
task = Task(
    description="...",
    agent=my_pricing_agent,
    output_pydantic=MyPricingOutput,      # ← Add this
    guardrail=_validate_pricing_honesty,  # ← Add validator
    guardrail_max_retries=2,              # ← Set retries
)
```

---

## Common Validator Patterns

### Pattern 1: Reject unsourced $ amounts
```python
def _validate_pricing_honesty(result):
    text = result.pydantic.my_output_field.lower()
    if any(char in text for char in ["$", "USD"]):
        # Does it cite a tool or have a fallback?
        if "INSUFFICIENT_DATA" not in text and "tool" not in text:
            return (False, "All prices must cite tool data or say INSUFFICIENT_DATA")
    return (True, result)
```

### Pattern 2: Validate structured fields
```python
def _validate_price_range(result):
    for price in result.pydantic.prices:
        if not (price.startswith("$") or price == "INSUFFICIENT_DATA"):
            return (False, f"Invalid price format: {price}")
    return (True, result)
```

---

## Testing Your Guardrails

```bash
# 1. Simulate a hallucination (should fail)
from src.agents import _validate_no_hallucination_flights
result = Mock()
result.pydantic.flight_options = [
    Mock(price_range="probably around $600")
]
valid, msg = _validate_no_hallucination_flights(result)
assert not valid, "Should reject 'probably'"

# 2. Simulate valid output (should pass)
result.pydantic.flight_options = [
    Mock(price_range="$450-650")
]
valid, msg = _validate_no_hallucination_flights(result)
assert valid, "Should accept real price range"

# 3. Simulate INSUFFICIENT_DATA (should pass)
result.pydantic.flight_options = [
    Mock(price_range="INSUFFICIENT_DATA")
]
valid, msg = _validate_no_hallucination_flights(result)
assert valid, "Should accept INSUFFICIENT_DATA"
```

---

## Debugging Failed Tasks

When a task fails guardrail validation:

1. **Check the error message** in logs
   ```
   GuardrailError: "Flight prices must come from tool data or say INSUFFICIENT_DATA"
   ```

2. **Examine agent output** before guardrail
   - Did the agent call its tool?
   - What did the tool return?
   - Did the agent synthesize extra numbers?

3. **Verify setup:**
   ```python
   # Make sure agent has:
   - temperature=0.0
   - Tool access (check tools=[...])
   - No "typically"/"usually"/"probably" in backstory
   
   # Make sure task has:
   - output_pydantic model
   - guardrail validator
   - guardrail_max_retries > 0
   ```

4. **Check frontend** — does it handle `INSUFFICIENT_DATA` gracefully?

---

## Temperature Settings

| Agent Type | Temperature | Reason |
|------------|-------------|--------|
| Pricing-related | 0.0 | Must be deterministic, zero creativity |
| Research specialists | 0.0 | Facts, not speculation |
| Synthesizers | 0.0 | Don't invent data |
| Interpreters | 0.0 | Consistent logic, no guessing |
| Generic agents | 0.3-0.7 | Some creativity OK if no pricing |

**Rule of thumb:** If your agent outputs numbers that users will act on, set `temperature=0.0`.

---

## INSUFFICIENT_DATA Propagation

**When to output it:**
- Tool call failed or returned no data
- User didn't provide required context
- Can't make a judgment without real data

**Where it goes:**
1. Agent output → `price_range="INSUFFICIENT_DATA"`
2. Pydantic model → Field accepts it
3. Frontend → Shows "Data not available" message
4. User → Knows this isn't an estimate, it's unknown

**Example flow:**
```
User: "Plan a trip to Japan"
↓
Flight Scout calls get_flight_availability (no results)
↓
Flight Scout outputs: price_range="INSUFFICIENT_DATA"
↓
Guardrail validates: ✅ (INSUFFICIENT_DATA is acceptable)
↓
Frontend displays: "Flight pricing data not available"
↓
User knows: Not an estimate, just no data right now
```

---

## OWASP & Security Notes

**Relevance to LLM Hallucination:**
- **Input Validation:** Guardrails validate agent output ✅
- **Output Encoding:** INSUFFICIENT_DATA is safe string ✅
- **Trust Boundaries:** Agent can't bypass validator ✅
- **Audit Trail:** Guardrail logs rejections ✅

This pattern also mitigates:
- **Prompt Injection:** Guardrail rejects suspicious patterns
- **Data Leakage:** Agents can't invent data to share
- **Misinformation:** Users can't get confident but false prices

---

## Checklist for New Pricing Features

- [ ] Agent has `temperature=0.0`
- [ ] Agent can access relevant tool(s)
- [ ] Agent backstory says "NEVER guess prices"
- [ ] Task description has "CRITICAL:" pricing section
- [ ] Task has `output_pydantic` model
- [ ] Task has `guardrail` validator
- [ ] Validator catches unsourced $ amounts
- [ ] INSUFFICIENT_DATA is valid in pydantic field
- [ ] Frontend handles INSUFFICIENT_DATA gracefully
- [ ] Test with both real and absent tool data
- [ ] Log validator rejections for debugging

