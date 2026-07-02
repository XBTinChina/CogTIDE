# JSON contract

Output strictly valid JSON. No trailing commas. No comments. No `NaN` or
`Infinity`. Strings must be properly escaped. Lists must be JSON arrays
even when they contain a single item — never collapse a one-element list
to a bare string.
