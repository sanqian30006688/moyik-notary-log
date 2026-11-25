# Moyik notary format (`moyik-notary-v1`)

This document describes the format of Moyik's notary records precisely enough for anyone to write an independent checker. It covers the format and how to check it, and nothing else.

## What it does and does not guarantee

| Situation | Result |
|---|---|
| An entry is changed, removed or inserted afterwards | The chain no longer adds up; a check names the entry |
| Someone with full control of the database rewrites history | Possible, but it no longer matches the checkpoints already signed, anchored and copied elsewhere |
| Different people are shown different histories | There is one sequence of checkpoints for the whole platform, public and mirrored |
| A time is forged | Upper bound: the Bitcoin block of the anchor. Lower bound: the newest Bitcoin block named inside the checkpoint |
| The content was false at the moment it was recorded | **Not prevented.** A record proves what was recorded and when, not that it was true |
| Records made after the latest anchor | Protected by Moyik's signature only, until the next anchor reaches a block |

## Format (version `moyik-notary-v1`)

All hashes are SHA-256. Hex is lower case. `LF` is the single byte `0x0a`. Text is UTF-8.

### Entry

An entry has an envelope and two parts, `who` and `what`. Each part is a JSON object stored as text, exactly as hashed, together with a 16-byte random salt.

```
part_hash  = SHA-256( salt || utf8(text) )

entry_hash = SHA-256( utf8(
  "moyik-notary-v1" LF "entry" LF
  chain_id LF            -- UUID, lower case, with dashes
  seq LF                 -- decimal, first entry of a chain is 1
  hex(prev_hash) LF      -- entry_hash of seq-1; 64 zeros for seq 1
  type LF                -- [a-z0-9_.]{1,80}
  at_micros LF           -- decimal microseconds since the Unix epoch
  actor_kind LF          -- human | ai | system | admin | agent
  attest LF              -- witnessed | device_signed | co_signed
  hex(who_hash) LF
  hex(what_hash) LF ))
```

A part may have been erased (account closed, space deleted): then its text and salt are absent and only its hash remains. The envelope never changes, so the chain still verifies.

The first entry of every chain has type `chain.opened` and a `what` of `{"scope_kind": ..., "scope_id": ...}`, which binds the chain id to the space, person or platform it belongs to.

### Checkpoint

A checkpoint seals every entry not yet sealed, across all chains, in ascending order of the database's entry id. The position of an entry inside its checkpoint is `leaf_index` (from 0).

The Merkle tree is the one in RFC 6962 section 2.1:

```
leaf = SHA-256( 0x00 || entry_hash )
node = SHA-256( 0x01 || left || right )
```

```
checkpoint_hash = SHA-256( utf8(
  "moyik-notary-v1" LF "checkpoint" LF
  number LF              -- decimal, from 1, no gaps
  hex(prev_hash) LF      -- checkpoint_hash of number-1; 64 zeros for number 1
  entry_count LF         -- leaves in this checkpoint
  total_count LF         -- entries sealed up to and including this checkpoint
  hex(root) LF
  at_micros LF
  beacon LF ))           -- empty, or "bitcoin:<height>:<block hash>" of the newest block seen
```

The text inside `utf8( ... )` is the checkpoint's *preimage*. Saved as a file, it is the file whose SHA-256 is anchored.

### Signature

Moyik signs each checkpoint with Ed25519 over:

```
utf8( "moyik-notary-v1" LF "signed-checkpoint" LF hex(checkpoint_hash) LF )
```

Public keys (raw 32 bytes, hex) are listed with their `key_id` at `/.well-known/moyik-notary.json`. A retired key stays listed. Adding and retiring a key are themselves entries on the platform chain (`notary.key_added`, `notary.key_retired`).

### Anchor

The newest checkpoint's `checkpoint_hash` is submitted to public OpenTimestamps calendars. Because checkpoints are chained, one anchored checkpoint covers every checkpoint before it. The stored proof is the calendar's serialized timestamp for that digest; `/.well-known/moyik-notary/checkpoint/<n>?file=ots` serves it as a standard detached `.ots` file and `/.well-known/moyik-notary/checkpoint/<n>` serves the preimage.

### Content digest

Long content stays in its own table; the entry holds a digest of it:

```
digest = hex( SHA-256( for each piece: utf8(decimal byte length) || ":" || piece ) )
```

For `decision.recorded` the pieces are the decision's title, decision and rationale (empty string when there is none).

**Exact bytes, never normalised.** A digest is taken over the bytes exactly as the database stores them and is compared against the same stored bytes later. Nothing is trimmed, no line endings are converted, no Unicode form is changed, on either side: a checker that "tidies" text first will report a change that never happened. Whoever exports content for an outside check must hand over the stored text untouched (in JSON, as a string; never re-typed or re-wrapped).

**Structured content.** A digest that an outside checker is meant to recompute is never taken over a JSON object, because two serialisers disagree on key order, spacing and numbers. It is taken over text pieces with the formula above, in an order written down here for that type. Fields of an entry not described in this document are not part of what a receipt proves.

**What a receipt proves without any of this.** The checks in the next sections cover the entry, its place in a checkpoint, the signature and the anchor. They need no content digest at all. Comparing long content with its fingerprint is a separate, optional step.

### Receipt (`moyik-notary-receipt-v1`)

A JSON object: `entry` (envelope plus the parts that still exist), `checkpoint`, `inclusion` (`leaf_index`, `path` of sibling hashes, leaf to root), `later` (the checkpoints after it up to an anchored one), `anchors` (provider, endpoint, checkpoint number, proof in hex) and `keys`.

## Checking a receipt without Moyik

1. Recompute `part_hash` for each part present and `entry_hash`; compare.
2. Walk `inclusion.path` from `leaf` to a root (RFC 9162 section 2.1.3.2) with tree size `entry_count`; compare with `checkpoint.root`.
3. Recompute `checkpoint_hash`. Check the signature against a public key obtained somewhere other than the receipt.
4. For each checkpoint in `later`: its `prev_hash` must be the hash of the one before, and its own hash must recompute.
5. The anchored checkpoint's hash is the digest of the OpenTimestamps proof. Follow the proof to its Bitcoin attestation and compare the resulting Merkle root with the block header at that height, from any block explorer or your own node. Or fetch the two checkpoint files and run `ots verify moyik-checkpoint-<n>.txt.ots`.

`mirror.py --check-only` in this repository does steps 3 and 4 for the whole public log.
