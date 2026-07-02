# Output contract

When the task asks for structured output, respond with a single JSON object
or array, and nothing else. No prose before or after, no markdown code
fences. The downstream parser will reject extra commentary.

If the task asks for an array, return an array at the top level. Do not
wrap arrays in `{"theories": [...]}`, `{"results": [...]}`, or any similar
wrapper object — the parser tolerates this but it adds noise to logs.

All field names must match exactly the schema given in the task. Do not
invent fields. Do not omit required fields.
