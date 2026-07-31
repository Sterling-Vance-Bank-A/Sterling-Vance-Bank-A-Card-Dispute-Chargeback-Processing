"""
Part 3 (Person C): Prompts — a reusable, fill-in-the-blank starting point.

Analysts draft denial explanations constantly. Rather than everyone
free-handing the wording, the server offers a discoverable template that
just needs a dispute_id plugged in. This is intentionally a *prompt*, not a
tool: it doesn't return an answer, it returns a starting instruction for the
model (or analyst) to work from.

Registers against the SAME low-level `Server` instance as server.py — call
`register_prompts(app)` once, before `app.run()`.

Uses add_request_handler with the correct 3-argument signature:
(method_name, params_type, handler_fn).
"""

import mcp.types as types

DENIAL_PROMPT_NAME = "draft_denial_explanation"


def register_prompts(app):
    async def handle_list_prompts(ctx, params) -> types.ListPromptsResult:
        return types.ListPromptsResult(
            prompts=[
                types.Prompt(
                    name=DENIAL_PROMPT_NAME,
                    description=(
                        "Draft a clear, professional, customer-facing "
                        "explanation for why a dispute was denied."
                    ),
                    arguments=[
                        types.PromptArgument(
                            name="dispute_id",
                            description="The dispute ID being denied, e.g. 'DISP-003'",
                            required=True,
                        )
                    ],
                )
            ]
        )

    async def handle_get_prompt(ctx, params) -> types.GetPromptResult:
        if params.name != DENIAL_PROMPT_NAME:
            raise ValueError(f"Unknown prompt: {params.name}")

        dispute_id = (params.arguments or {}).get("dispute_id", "<dispute_id>")

        instruction = (
            f"Write a clear, professional, empathetic explanation to the "
            f"customer for why dispute {dispute_id} was denied.\n\n"
            f"1. First call get_dispute_details for {dispute_id} to get its "
            "reason_code, amount, and evidence_notes.\n"
            "2. Read the dispute reason-code policy resource "
            "(policy://disputes/reason-codes) to find the specific "
            "evidence requirement tied to that reason_code.\n"
            "3. Explain in plain, non-technical language: (a) what was "
            "reviewed, (b) the specific policy reason the dispute did not "
            "qualify, and (c) what the customer can do next (e.g. submit "
            "additional evidence, contact the merchant directly).\n\n"
            "Keep it under 150 words. Do not use accusatory language and do "
            "not imply the customer acted in bad faith."
        )

        return types.GetPromptResult(
            description=f"Denial explanation template for {dispute_id}",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(type="text", text=instruction),
                )
            ],
        )

    app.add_request_handler(
        "prompts/list",
        types.ListPromptsRequest,
        handle_list_prompts,
    )
    app.add_request_handler(
        "prompts/get",
        types.GetPromptRequestParams,
        handle_get_prompt,
    )
