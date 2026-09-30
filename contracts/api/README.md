# contracts/api/

Request/response surfaces: OpenAPI fragments, JSON Schema, `.proto` service definitions.

**Consumers** (from `ownership.yaml` → `contract_consumers["contracts/api/**"]`):

- `bot-02-web-edge`
- `bot-03-android`
- `bot-04-ios`

A breaking change here needs an acknowledgement from all three before G-4 passes. That is the
control that stops a field rename which takes thirty seconds in the API repo from breaking the
iOS client silently, to be discovered weeks later by a user.

Empty until the first service exists. The directory is tracked so the surface, the consumer
list and the gate that reads them are in place before the first change arrives rather than
after it.

One file per surface, named for the surface rather than the service that happens to serve it
today — `notifications.yaml`, not `api-v2.yaml`.
