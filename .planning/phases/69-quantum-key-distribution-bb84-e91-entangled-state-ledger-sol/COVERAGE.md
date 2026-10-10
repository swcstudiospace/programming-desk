# API Coverage — Solana Devnet standard Memo publication

Original scope: REQ-QTELEPORT-009 and the live anchoring stage of010; user selected the existing SPL Memo publisher, not a wallet/account/token/validator platform. Existing cryptography/httpx are the transport/signature libraries. Full capability inventory is the official [HTTP RPC index](https://solana.com/docs/rpc/http), inspected2026-10-09; every unused indexed method is explicitly decided below. Opt-outs do not remove any original criterion. The application constructs only standard Memo plus fixed SetComputeUnitLimit400000, no priority fee, transfers, funding mutation or program deployment. Node workers are owned internal protocols, not an external provider SDK.

| capability | decision | reason |
|---|---|---|
| getBalance | INTEGRATE | Verify dedicated fee-payer prerequisite without wallet discovery. |
| getFeeForMessage | INTEGRATE | Check actual fee for the exact prepared legacy message. |
| getLatestBlockhash | INTEGRATE | Actual recent blockhash and lastValidBlockHeight. |
| getSignatureStatuses | INTEGRATE | Observe the same submitted signature at confirmed/finalized. |
| getTransaction | INTEGRATE | Verify successful exact Memo/program/payer/signature/proof readback and observed slot. |
| sendTransaction | INTEGRATE | One authorized signed Memo transaction with preflight and maxRetries0. |
| getBlockHeight | INTEGRATE | Observe blockhash expiry during bounded same-signature confirmation. |
| getGenesisHash | INTEGRATE | Fail closed unless the immutable expected Devnet genesis matches. |
| getAccountInfo | OPT-OUT | Account-management state is unnecessary for Memo-only proof publication. |
| getLargestAccounts | OPT-OUT | Unrelated account discovery. |
| getMinimumBalanceForRentExemption | OPT-OUT | Memo publication creates no rent-bearing account. |
| getMultipleAccounts | OPT-OUT | No bulk account management. |
| getProgramAccounts | OPT-OUT | No custom program/account enumeration. |
| getTokenAccountBalance | OPT-OUT | No token operations authorized. |
| getTokenAccountsByDelegate | OPT-OUT | No token/delegation operations. |
| getTokenAccountsByOwner | OPT-OUT | No wallet/token discovery. |
| getTokenLargestAccounts | OPT-OUT | No token account discovery. |
| getTokenSupply | OPT-OUT | Unrelated token economics. |
| getRecentPrioritizationFees | OPT-OUT | Fixed no-priority-fee transaction shape. |
| getSignaturesForAddress | OPT-OUT | Observe the persisted exact publication signature, not scan wallet history. |
| getTransactionCount | OPT-OUT | Cluster-wide transaction count does not prove this publication. |
| isBlockhashValid | OPT-OUT | lastValidBlockHeight/getBlockHeight provide bounded expiry observation without a second policy. |
| requestAirdrop | OPT-OUT | Funding is external operator action, not a publisher mutation; observed earlier airdrop failure is not retried. |
| simulateTransaction | OPT-OUT | sendTransaction's required real preflight covers the exact packet; no separate simulation success substitute. |
| getBlock | OPT-OUT | Exact getTransaction readback is sufficient; no block-history browser. |
| getBlockCommitment | OPT-OUT | Confirmed/finalized status plus actual transaction readback are the selected evidence. |
| getBlockProduction | OPT-OUT | Unrelated validator telemetry. |
| getBlocks | OPT-OUT | No historical block enumeration. |
| getBlocksWithLimit | OPT-OUT | No historical block enumeration. |
| getBlockTime | OPT-OUT | Use observed transaction slot/blockTime when provided, never manufacture time. |
| getFirstAvailableBlock | OPT-OUT | No ledger-history administration. |
| getRecentPerformanceSamples | OPT-OUT | Unrelated performance telemetry. |
| minimumLedgerSlot | OPT-OUT | No RPC ledger administration. |
| getClusterNodes | OPT-OUT | Configured Devnet endpoint, no infrastructure discovery. |
| getEpochInfo | OPT-OUT | Publication does not require epoch economics. |
| getEpochSchedule | OPT-OUT | No epoch scheduling. |
| getHealth | OPT-OUT | Actual scoped RPC results/readback determine availability; no extra health telemetry. |
| getHighestSnapshotSlot | OPT-OUT | No validator snapshot administration. |
| getIdentity | OPT-OUT | Immutable genesis pins cluster; RPC node identity is not publication evidence. |
| getLeaderSchedule | OPT-OUT | No validator/leader targeting. |
| getMaxRetransmitSlot | OPT-OUT | No network diagnostics. |
| getMaxShredInsertSlot | OPT-OUT | No network diagnostics. |
| getSlot | OPT-OUT | Use observed execution slot, not a context/current slot as fabricated publication slot. |
| getSlotLeader | OPT-OUT | No leader targeting. |
| getSlotLeaders | OPT-OUT | No leader enumeration. |
| getVersion | OPT-OUT | Runtime/platform version telemetry is outside publication acceptance. |
| getVoteAccounts | OPT-OUT | No staking/validator management. |
| getInflationGovernor | OPT-OUT | Unrelated economics. |
| getInflationRate | OPT-OUT | Unrelated economics. |
| getInflationReward | OPT-OUT | No staking rewards. |
| getStakeMinimumDelegation | OPT-OUT | No stake operations. |
| getSupply | OPT-OUT | Unrelated economics. |

WebSocket subscriptions are a separately indexed API surface and not the selected bounded HTTP same-signature observation; no subscription/watch capability is implied. Eight INTEGRATE methods must be exercised or explicitly reported unverified. This matrix is a planning decision, not a claim that any code or live transaction passed.
