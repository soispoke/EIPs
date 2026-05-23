---
eip: TBD
title: Recent Root References for Frame Transactions
description: Frame transactions can declare verified recent roots
author: Thomas Thiery (@soispoke), Vitalik Buterin (@vbuterin), Toni Wahrstätter (@nerolation)
discussions-to: TBD
status: Draft
type: Standards Track
category: Core
created: 2026-05-15
requires: 7843, 8141
---

## Abstract

EIP-8141 frame transactions can reference recent application-published roots without reading mutable storage during validation. Applications publish roots to a system contract keyed by `(source_id, slot)`, where `source_id` derives from the writer address and a salt. Each reference is verified by the protocol before any dependent frame executes.

## Motivation

EIP-8141 validation must not read arbitrary storage controlled by another account or application in the public mempool. Some validation rules still need to depend on recent application state: privacy tree roots, wallet authorization roots, account validation roots.

An application publishes a root for the current slot to a system contract. Transactions name a `(source_id, slot, root)` tuple that the protocol verifies before any frame that depends on it. Validation logic can then rely on the named root without reading mutable storage.

Privacy applications, for example, keep a tree of commitments and prove spends against a recent tree root. With this EIP, the application writes a root each slot, and spend transactions reference that root directly instead of reading the application's changing tree state during validation.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

This specification is a delta against EIP-8141. Terms not defined here, including `FrameTx`, `FRAME_TX_TYPE`, `VERIFY`, `EXPIRY_VERIFIER`, frame modes, `compute_sig_hash`, `FRAMEDATALOAD`, `FRAMEDATACOPY`, and `FRAMEPARAM`, have the meanings defined in EIP-8141.

### Constants

| Name                                |                              Value |
| ----------------------------------- | ---------------------------------: |
| `FORK_TIMESTAMP`                    |                              `TBD` |
| `RECENT_ROOT_ADDRESS`               |                              `TBD` |
| `RECENT_ROOT_CODE`                  |                              `TBD` |
| `RECENT_ROOT_REFERENCE_VERIFIER`    |                              `TBD` |
| `RECENT_ROOT_REFERENCE_CODE`        |                              `TBD` |
| `RECENT_ROOT_REFERENCE_DATA_LENGTH` |                               `72` |
| `RECENT_ROOT_LENGTH`                |                             `8192` |
| `RECENT_ROOT_USABLE_WINDOW`         |                             `8191` |
| `RECENT_ROOT_ENTRY_DOMAIN`          |    `keccak256("RECENT_ROOT_ENTRY")` |
| `RECENT_ROOT_STORAGE_DOMAIN`        |  `keccak256("RECENT_ROOT_STORAGE")` |

All concatenations below use fixed-length encodings. Domains are 32 bytes. Addresses are 20 bytes. Slots and indices are unsigned 64-bit big-endian integers. Roots, salts, source identifiers, entry hashes, and storage keys are 32 bytes.

### Current slot

For block validation, `current_slot` is the consensus slot of the beacon block that contains the execution payload being validated.

Execution clients MUST obtain `current_slot` from the EIP-7843 `slotNumber` field. Clients MUST NOT derive `current_slot` from `block.timestamp` using a fixed slot duration.

For transaction pool handling, `current_slot` is the node's current slot at receipt, recheck, or eviction time. It is local policy, not block validity.

References MUST target slots strictly before `current_slot`. A root written during slot `S` becomes referenceable beginning in slot `S + 1`.

### Root sources

A root source is identified by:

```text
source_id = keccak256(source_address || salt)
```

where `source_address` is an address and `salt` is a `bytes32` value.

The source address MAY be an externally owned account or a contract, and MAY use multiple root sources by using different salts. Applications using a root source are responsible for controlling who can write to it and how salts are allocated.

### Entry and storage keys

The committed entry for `(source_id, slot, root)` is:

```text
entry_hash = keccak256(
    RECENT_ROOT_ENTRY_DOMAIN ||
    source_id ||
    uint64_be(slot) ||
    root
)
```

The storage key for index `i` is:

```text
storage_key = keccak256(
    RECENT_ROOT_STORAGE_DOMAIN ||
    source_id ||
    uint64_be(i)
)
```

Each root source has a conceptual array:

```text
entries: bytes32[RECENT_ROOT_LENGTH]
```

`entries[i]` is stored at `RECENT_ROOT_ADDRESS[storage_key]`. All entries are initially zero.

Each root source uses at most `RECENT_ROOT_LENGTH` storage keys. The global storage footprint is `RECENT_ROOT_LENGTH` keys per written `source_id`.

### Recent root contract

At activation, clients MUST create or update the account at `RECENT_ROOT_ADDRESS` as specified in [Activation](#activation).

The contract accepts one write operation with 64 bytes of calldata:

```text
salt: bytes32
root: bytes32
```

Bytes `0..31` are `salt`. Bytes `32..63` are `root`.

Calls MUST revert unless calldata is exactly 64 bytes and call value is zero.

In static context, the write MUST fail and storage MUST remain unchanged.

The source address for a successful write is `msg.sender` of the call to `RECENT_ROOT_ADDRESS`.

Only a direct call to `RECENT_ROOT_ADDRESS` can write recent-root storage. `DELEGATECALL` and `CALLCODE` MUST NOT write recent-root storage.

When a successful call is made during slot `S`, the contract computes:

```text
source_address = msg.sender
source_id = keccak256(source_address || salt)
i = S mod RECENT_ROOT_LENGTH
entry_hash = keccak256(
    RECENT_ROOT_ENTRY_DOMAIN ||
    source_id ||
    uint64_be(S) ||
    root
)
storage_key = keccak256(
    RECENT_ROOT_STORAGE_DOMAIN ||
    source_id ||
    uint64_be(i)
)
```

and sets:

```text
storage[storage_key] = entry_hash
```

The call follows normal EVM execution and gas accounting. A successful call returns zero bytes. The contract exposes no read operation.

Each `(source_id, S)` has at most one referenceable root on the canonical chain. Multiple writes by the same source address and salt during slot `S` target the same storage key. If multiple writes are included, the final write in canonical block execution order overwrites earlier writes. Only that final root is referenceable beginning in slot `S + 1`.

### Recent root reference frame

A **recent root reference frame** is a frame whose `target` equals `RECENT_ROOT_REFERENCE_VERIFIER`. It declares one reference `(source_id, slot, root)` carried in `frame.data`.

A recent root reference frame is invalid unless:

- `frame.mode == VERIFY`,
- `frame.flags == 0`,
- `frame.value == 0`, and
- `len(frame.data) == RECENT_ROOT_REFERENCE_DATA_LENGTH`.

`frame.data` is laid out as:

```text
source_id : bytes[0:32]
slot      : bytes[32:40]   # uint64 big-endian
root      : bytes[40:72]
```

EIP-8141's transaction payload, frame layout, frame execution rules, and gas accounting are otherwise unchanged. The verifier's work is paid from `frame.gas_limit`.

EIP-8141's VERIFY-mode data-elision rule is extended to a set of **public-data verifiers**:

```text
PUBLIC_DATA_VERIFIERS = {EXPIRY_VERIFIER, RECENT_ROOT_REFERENCE_VERIFIER}
```

For VERIFY frames whose `target` is in `PUBLIC_DATA_VERIFIERS`, `frame.data` is not elided by `compute_sig_hash(tx)`, and `FRAMEDATALOAD`, `FRAMEDATACOPY`, and `FRAMEPARAM(0x04)` return the frame's actual data and length. This binds the reference to the signature and makes it readable from other frames.

### Recent root reference verifier

When a recent root reference frame executes, the verifier performs the following check against the state at frame entry:

```text
source_id   = frame.data[0:32]
slot        = uint64_be(frame.data[32:40])
root        = frame.data[40:72]

assert 1 <= current_slot - slot <= RECENT_ROOT_USABLE_WINDOW

i           = slot mod RECENT_ROOT_LENGTH
storage_key = keccak256(RECENT_ROOT_STORAGE_DOMAIN || source_id || uint64_be(i))
entry_hash  = keccak256(RECENT_ROOT_ENTRY_DOMAIN   || source_id || uint64_be(slot) || root)

assert state.storage[RECENT_ROOT_ADDRESS][storage_key] == entry_hash
```

If any assertion fails, the frame reverts. Per EIP-8141, a revert in a VERIFY frame renders the transaction invalid.

A successful check returns zero bytes and adds `RECENT_ROOT_ADDRESS` and the computed `storage_key` to the transaction's accessed address and storage-key sets. This affects warm/cold gas accounting only.

Duplicate recent root reference frames are valid. Each is checked and charged independently.

Like the expiry verifier in EIP-8141, clients MAY skip explicit EVM execution at `RECENT_ROOT_REFERENCE_VERIFIER` and perform the check natively, provided the result is indistinguishable from executing `RECENT_ROOT_REFERENCE_CODE`.

### Public mempool handling

A recent root reference frame MAY appear at any position in the frame list. For matching the recognized validation-prefix shapes in EIP-8141, recent root reference frames are skipped, in the same manner as expiry verifier frames.

Recent root reference frames are exempt from the generic validation-trace and banned-opcode rules. Their effect on mutable state outside `tx.sender` is bounded to one storage read on `RECENT_ROOT_ADDRESS` at a key fully determined by `frame.data`. Their `gas_limit` counts toward `MAX_VERIFY_GAS` when they appear in the validation prefix.

Nodes SHOULD admit a transaction to the public mempool only if every recent root reference frame is valid against the node's current head.

Nodes SHOULD NOT admit a transaction while any recent root reference frame has `slot >= current_slot`. Nodes MAY evict a transaction with any recent root reference frame where `current_slot - slot >= RECENT_ROOT_LENGTH`.

Nodes SHOULD recheck pending transactions with recent root reference frames when the head changes, when the node's current slot advances, or after any reorg that may affect referenced entries.

### Activation

This EIP MUST activate at or after EIP-8141. If `timestamp < FORK_TIMESTAMP`, clients MUST NOT apply this EIP.

For every block `B` with `B.timestamp >= FORK_TIMESTAMP` whose parent has `parent.timestamp < FORK_TIMESTAMP`, clients MUST initialize both system contracts against `B`'s parent state before executing any transaction in `B`. For each `(address, code)` pair in `{(RECENT_ROOT_ADDRESS, RECENT_ROOT_CODE), (RECENT_ROOT_REFERENCE_VERIFIER, RECENT_ROOT_REFERENCE_CODE)}`:

- If the account does not exist, clients MUST create it with balance 0, nonce 1, the given `code`, and empty storage.
- If the account already exists with empty code and empty storage, clients MUST set its code to the given `code`, set its nonce to `max(existing_nonce, 1)`, preserve its balance, and leave storage empty.

The fork configuration MUST choose both addresses with empty code and empty storage in the parent state of the first post-fork payload. If this condition is false at activation, the payload is invalid.

For all other blocks, clients MUST NOT run this initialization. Clients MUST handle reorgs across the fork boundary by applying or undoing this transition according to the canonical chain.

## Rationale

EIP-8141 validation needs inputs that are known before validation starts. General reads from storage controlled by another account or application are unsafe for the public mempool because one mutable cell can invalidate many pending transactions. Recent root references provide a narrow channel: each reference names one recent `bytes32` root and one system-contract storage key.

### Frame-based delivery

References are carried by VERIFY frames so that signature-hash binding, gas accounting, mempool prefix shapes, and introspection follow EIP-8141 unchanged. The pattern mirrors the expiry verifier; the one-off expiry exception generalizes into a `PUBLIC_DATA_VERIFIERS` set covering both. One reference per frame keeps `FRAMEDATALOAD` offsets fixed and gives each reference its own receipt entry. `MAX_FRAMES` already bounds the count.

### Entry binding

Each stored entry commits to the root source, slot, and root. This prevents an old root at the same array index, or a root from another root source, from satisfying a reference.

### Window choice

References are limited to slots strictly before `current_slot`. During slot `S`, writes update index `S mod RECENT_ROOT_LENGTH`, but references to `S` are invalid and references old enough to share that index are expired. Current-slot writes therefore cannot invalidate currently valid references. `RECENT_ROOT_LENGTH = 8192` gives `RECENT_ROOT_USABLE_WINDOW = 8191`, because the current slot is not referenceable.

### Implicit source creation

No creation transaction is required. A root source is created implicitly when a source address first writes with a new `(source_address, salt)` pair. Each root source has a bounded rolling window. Aggregate storage grows linearly with the number of written root sources. State growth is paid incrementally by the writes that create storage entries.

## Backwards Compatibility

This EIP does not modify EIP-7702 or other transaction types. An EIP-7702-delegated EOA may be a source address; `source_id` is derived from `msg.sender` of the write call.

The transaction payload schema of EIP-8141 is unchanged. Pre-fork frame transactions remain valid under EIP-8141's pre-fork rules.

References to slots before this EIP's activation are not satisfiable because recent root storage is empty at activation.

## Security Considerations

Consensus treats `root` as an opaque `bytes32`. Applications define what it commits to and MUST bind the expected `source_id`, slot window, and root in their validation logic. A privacy proof using root `R` should include `(source_id, slot, R)` or an application-specific commitment to those fields as a public input, and validation logic MUST read the same tuple from the recent root reference frame via `FRAMEDATALOAD` and check that it matches.

Each `(source_id, slot)` has one referenceable root on the canonical chain. The referenceable root is last-write-wins according to canonical execution order and is finalized with the containing block. An application that needs multiple roots from the same slot SHOULD write an aggregate commitment.

This EIP does not guarantee inclusion of root writes. Applications that rely on timely root publication need their own publication path, redundant root sources, or an inclusion policy for write transactions.

The same `(source_address, salt)` pair produces the same `source_id` on different chains, but each chain maintains independent recent root state. Proofs, bridge messages, and offchain attestations that carry recent root references MUST bind the intended chain domain outside the tuple.

Recent roots create ordinary persistent storage under `RECENT_ROOT_ADDRESS`. Existing root sources overwrite at most `RECENT_ROOT_LENGTH` cells, while new root sources create additional cells. The pricing point for aggregate state growth is source creation, not recurring writes. Future versions MAY add a one-time source registration cost or first-write surcharge for each new `source_id`.

## Copyright

Copyright and related rights waived via [CC0](/LICENSE).
