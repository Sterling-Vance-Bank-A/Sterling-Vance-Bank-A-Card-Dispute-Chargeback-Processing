import mcp.types as types

POLICY_TEXT = """================================================================================
STERLING VANCE BANK — DISPUTE & CHARGEBACK REASON CODE POLICY
Internal reference. Applies to all card-not-present and card-present disputes.
================================================================================

1. duplicate_charge
   Definition: The same purchase was posted to the account more than once.
   Resolution: Request refund from merchant, if unsuccessful process chargeback.

2. unauthorized_transaction
   Definition: The cardholder claims they did not authorize or participate in the transaction.
   Resolution: Investigate for fraud. Gather IP, delivery address, and 3D Secure status.

3. item_not_received
   Definition: The cardholder was billed for merchandise they never received.
   Resolution: Request proof of delivery from merchant.

4. defective_merchandise
   Definition: The item arrived but was defective or not as described.
   Resolution: Request evidence of return or attempted return to the merchant.
"""

def register_resources(app):
    @app.list_resources()
    async def list_resources() -> list[types.Resource]:
        return [
            types.Resource(
                uri="policy://disputes/reason-codes",
                name="Dispute Reason Code Policy",
                mimeType="text/plain",
                description="Internal bank policy defining standard dispute reason codes and resolution paths."
            )
        ]

    @app.read_resource()
    async def read_resource(uri: str) -> str:
        if uri == "policy://disputes/reason-codes":
            return POLICY_TEXT
        raise ValueError(f"Unknown resource URI: {uri}")
