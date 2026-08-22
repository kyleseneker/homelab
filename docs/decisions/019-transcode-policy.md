# ADR-019: Transcode Policy

## Status

Accepted

## Context

The library is acquired through Sonarr and Radarr, whose quality profiles come from the
TRaSH guides via Recyclarr. Those profiles score `x265 (HD)` at -10000, which rejects 1080p
HEVC releases. Tdarr is deployed against the same library and is capable of re-encoding
every file to HEVC.

Run together without a stated policy, the two contradict each other: Tdarr manufactures
precisely the files the quality profiles reject. Radarr's `HD Bluray + WEB` profile has
`upgradeAllowed: true`, so a re-encoded file can be scored below its replacement and pulled
again, re-encoded again, indefinitely.

The contradiction is not hypothetical. Six of seven films in the library are HEVC while the
profile that governs them rejects that codec.

## Decision

Acquire the best available source and keep it. Tdarr does not re-encode video.

`processTranscodes` is false on both libraries. Health checks stay enabled, so Tdarr still
reports corrupt or unplayable files.

## Alternatives Considered

- **Native HEVC**: drop `x265 (HD)` from the unwanted formats, accept HEVC on acquisition and
  keep Tdarr re-encoding. Internally consistent, and the storage saving is real -- four films
  gave back 38 GB. Rejected because it discards the reason the score exists: a 1080p HEVC
  release is usually a re-encode of an x264 source, and re-encoding locally reproduces that
  loss rather than avoiding it.
- **Re-encode only what the profiles ignore** (4K, or sources above a bitrate ceiling): keeps
  most of the saving without fighting the profiles. Viable later; it needs a bitrate-aware
  flow rather than a codec check, and the library is too small today to justify one.

## Rationale

- **The profiles already encode a policy.** Running TRaSH profiles is a decision to prefer
  source quality over size. Re-encoding contradicts that decision rather than complementing it.
- **The loss is permanent, the saving is not scarce.** An x264 Blu-ray re-encoded to HEVC on
  QSV at CQ 20 cannot be undone, and storage is not the binding constraint here.
- **It removes a feedback loop.** With `upgradeAllowed: true` and a -10000 score, re-encoded
  files invite their own replacement.
- **Playback does not need it.** Jellyfin transcodes on the same Intel GPU on demand, so
  client compatibility is not a reason to re-encode at rest.

## Consequences

- Files already re-encoded stay HEVC and continue to score -10000. They are candidates for
  replacement on the next upgrade search, which restores the acquired quality.
- Tdarr's role narrows to health checking. Audio cleanup and container normalisation remain
  available and do not conflict with this decision, but no flow performs them today.
- Reversing this means removing `x265 (HD)` from the unwanted formats in
  `recyclarr/configmap.yml` first, then re-enabling `processTranscodes`. Doing it in the other
  order recreates the loop.
