# No app-level authentication

The web UI has no login, session, or token-based auth of its own. Network
reachability is the entire access boundary: the server is only reachable
over Tailscale (plus tsdproxy), and anyone who can reach it on the network
is treated as trusted.

This is a deliberate trade-off for a single-user, self-hosted stack, not an
oversight — adding app-level auth would be real, ongoing engineering
surface (credential storage, session handling, CSRF, etc.) for a threat
model (an untrusted party on Evan's own Tailscale network) that doesn't
currently exist.

## Consequences

- The plugin must never be exposed on an interface reachable outside
  Tailscale (e.g. bound to `0.0.0.0` behind a NAT'd port-forward) without
  first revisiting this decision.
- Adding auth later is possible but not free: none of the current API
  design (`/api/*` routes) assumes or carries any identity/session concept,
  so retrofitting it would touch every route.
- This is consistent with the solo-user assumption already recorded
  elsewhere (no concurrency/conflict handling for simultaneous edits).
