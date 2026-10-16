# Observability

Every turn writes a few JSON lines to `logs/events.jsonl`, all sharing one `turn_id`, each with
`ms` since the turn started:

```
turn_start  {node, text}                       ms=0
tool_call   {tool, args, result}               ms=4676   (from the SDK's PostToolUse hook)
tool_call   ...
turn_end    {reply, node_after}                ms=8366
error       {error}                            (if something broke; the user hears a voice.py line)
```

That's enough to answer, for any turn: what the user said, which node handled it, which tools ran
with what input and result, how long each step took, and whether the node changed. Evals compute
latency and tool usage from this file.

The user never sees a raw error. `app/voice.py` holds short in-character lines for errors and
missing setup, picked at random so they don't feel canned.
