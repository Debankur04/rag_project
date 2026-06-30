def prompt_builder(query, memory=None):
    system_rules = """
You are an information retrieval assistant.

You MUST answer strictly and only using the information provided
in the GROUND TRUTH CONTEXT section.

Rules you must follow:
- Do NOT use prior knowledge.
- Do NOT guess or infer.
- Do NOT add details not present in the context.
- If the answer is not explicitly stated, respond exactly with:
  "I don't have that information."
""".strip()

    prompt = f"""
SYSTEM RULES:
{system_rules}

GROUND TRUTH CONTEXT:
{{{{context}}}}
""".strip()

    if memory:
        prompt += f"""

CONVERSATION MEMORY:
{memory}
"""

    prompt += f"""

USER QUERY:
{query}
"""

    return prompt
