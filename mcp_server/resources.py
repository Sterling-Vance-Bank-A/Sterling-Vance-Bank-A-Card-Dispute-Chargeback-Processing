"""
Part 2 (Person B): Resources — a read-only policy document the model can
fetch instead of calling a tool.

Exposes the Sterling Vance dispute reason-code policy via the MCP
resources/list and resources/read message types.

Uses add_request_handler with the correct 3-argument signature:
(method_name, params_type, handler_fn).
"""

import mcp.types as types

POLICY_URI = "policy://disputes/reason-codes"

POLICY_TEXT = """================================================================================
STERLING VANCE BANK — DISPUTE & CHARGEBACK REASON CODE POLICY
Internal reference. Applies to all card-not-present and card-present disputes.
================================================================================

1. duplicate_charge
   Definition: The same purchase was posted to the account more than once.
   Resolution: Request refund from merchant; if unsuccessful, process chargeback.

2. unauthorized_transaction
   Definition: The cardholder claims they did not authorize or participate in the transaction.
   Resolution: Investigate for fraud. Gather IP, delivery address, and 3D Secure status.

3. item_not_received
   Definition: The cardholder was billed for merchandise they never received.
   Resolution: Request proof of delivery from merchant.

4. defective_merchandise
   Definition: The item arrived but was defective or not as described.
   Resolution: Request evidence of return or attempted return to the merchant.

5. fraud
   Definition: Confirmed fraudulent transaction, typically card-not-present.
   Resolution: Immediately escalate; block card if pattern detected.
"""


def register_resources(app):
    async def handle_list_resources(ctx, params) -> types.ListResourcesResult:
        return types.ListResourcesResult(
            resources=[
                types.Resource(
                    uri=POLICY_URI,
                    name="Dispute Reason Code Policy",
                    mimeType="text/plain",
                    description=(
                        "Internal bank policy defining standard dispute reason "
                        "codes and their required resolution paths."
                    ),
                )
            ]
        )

    async def handle_read_resource(ctx, params) -> types.ReadResourceResult:
        uri = str(params.uri)
        if uri == POLICY_URI:
            return types.ReadResourceResult(
                contents=[
                    types.TextResourceContents(
                        uri=params.uri,
                        mimeType="text/plain",
                        text=POLICY_TEXT,
                    )
                ]
            )
        raise ValueError(f"Unknown resource URI: {uri}")

    app.add_request_handler(
        "resources/list",
        types.ListResourcesRequest,
        handle_list_resources,
    )
    app.add_request_handler(
        "resources/read",
        types.ReadResourceRequestParams,
        handle_read_resource,
    )
