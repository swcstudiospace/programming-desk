# contracts/events/

Asynchronous surfaces: event envelopes, queue and topic payloads, webhook bodies.

**Consumers** (from `ownership.yaml` → `contract_consumers["contracts/events/**"]`):

- `bot-01-systems-backend`
- `bot-02-web-edge`
- `bot-05-infrastructure`

Events deserve their own directory because their failure mode differs from an API's. A
request/response break shows up as an error the caller sees; an event break shows up as a
consumer that quietly stops matching, keeps returning 200, and drops the payload. Nothing is red
until someone asks why a downstream table is empty.

So: version the envelope, never reuse an event name with different semantics, and treat an
unrecognised field as ignorable rather than fatal on the consumer side.

The envelope schema shared across seats is documented in `docs/handoff-contracts.md`. Empty
until the first published event exists.
