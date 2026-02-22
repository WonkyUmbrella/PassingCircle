# FluffyChat: ~60-Second Delay at Key Backup Screen (Incognito / Fresh Session)

## Symptom

When an **existing user** logs into FluffyChat via SSO in an **incognito / private browsing window**, the app shows "Waiting for server..." at `/#/backup` for approximately 60 seconds before displaying the key recovery prompt.

**New accounts do not experience this delay.** The delay only affects users who have previously logged in and completed the E2EE bootstrap (cross-signing + key backup setup).

## Root Cause

This is a known bug in FluffyChat v2.4.1 in `lib/pages/bootstrap/bootstrap_dialog.dart`:

```dart
void _createBootstrap(bool wipe) async {
  await client.roomsLoading;
  await client.accountDataLoading;
  await client.userDeviceKeysLoading;
  while (client.prevBatch == null) {      // <-- blocks here
    await client.onSyncStatus.stream.first;
  }
  ...
}
```

In incognito mode, IndexedDB is blank — `prevBatch` is always `null`. FluffyChat sits in this `while` loop waiting for sync events that will never arrive, burning through two full 30-second long-poll timeouts before it can show the backup UI.

**Why new accounts are faster:** New accounts have no existing SSSS/cross-signing keys. FluffyChat takes the setup path (generating new keys) instead of the recovery path. The `prevBatch` guard only causes a visible delay in the recovery path where FluffyChat is trying to verify existing SSSS state.

**Why existing accounts are slow in incognito:** After a user's first session, Synapse stores their cross-signing public keys and SSSS `account_data` (`m.cross_signing.master`, `m.cross_signing.self_signing`, `m.cross_signing.user_signing`, `m.megolm_backup.v1`). On subsequent incognito logins, FluffyChat detects these entries in the initial sync response and enters the recovery path, hitting the `prevBatch` loop.

## Evidence from Network Logs

Two sequential sync requests, each timing out at exactly 30 seconds:

```
GET /_matrix/client/v3/sync?filter=1&since=s40_646_...&timeout=30000
→ 30.05s → { "next_batch": "s40_649_..." }   (empty — no new events)

GET /_matrix/client/v3/sync?filter=1&since=s40_649_...&timeout=30000
→ 30.05s → { "next_batch": "s40_652_..." }   (empty — no new events)
```

The server is not slow. These are long-poll timeouts — Synapse holds the connection open waiting for new events that will never arrive (they were already delivered in a previous session). The `next_batch`-only response confirms this.

## Status

- **FluffyChat v2.4.1** (current stable, January 2026): affected
- **FluffyChat `main` branch**: partially fixed by commits in Nov–Dec 2025:
  - `31a204f` — "Always open Chat Backup as page right after login"
  - `02b0fcb` — "Wait for secrets after bootstrap verification"
  - `040c18d` — "Better wait for secrets after verification bootstrap" (most relevant — avoids blocking if keys already cached)
- **No v2.5.0 release scheduled** as of February 2026
- Tracked in matrix-dart-sdk as [Issue #2028](https://github.com/famedly/matrix-dart-sdk/issues/2028): "Do not use Client.oneShotSync in SSSS and bootstrap" (closed without fix)

## Workarounds

### Option 1: Lower Synapse sync long-poll timeout (recommended quick fix)

Add to `services/synapse/templates/homeserver.yaml.j2` and `services/synapse/homeserver.yaml`:

```yaml
# Reduce long-poll timeout to shorten the FluffyChat incognito bootstrap delay.
# Default is 30000ms; lowering to 5000ms reduces the delay from ~60s to ~10s.
sync_long_poll_timeout_ms: 5000
```

Trade-off: all Matrix clients (Element, FluffyChat) poll more frequently — slightly higher CPU/bandwidth.

### Option 2: Avoid incognito / use PWA

If the user installs FluffyChat as a PWA or uses a regular (non-incognito) browser session, IndexedDB persists between visits. `prevBatch` is cached and the bootstrap loop exits immediately. Subsequent logins are instant.

### Option 3: Build FluffyChat from `main`

The `main` branch contains the Dec 2025 bootstrap fixes. A custom Docker build from `main` would likely reduce or eliminate the delay. Requires maintaining a custom image.

### Option 4: Accept the delay

~60 seconds, once per incognito session. After the user enters their recovery key, subsequent navigation within the session is instant.

## Related Files

- `services/synapse/templates/homeserver.yaml.j2` — add `sync_long_poll_timeout_ms` here
- `services/fluffychat/templates/config.json.j2` — no relevant config options exist in FluffyChat's `config.json` for this behavior
