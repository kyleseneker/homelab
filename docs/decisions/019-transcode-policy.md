# ADR-019: Transcode Policy

## Status

Accepted

## Context

The library is acquired through Sonarr and Radarr, whose quality profiles come from the
TRaSH guides via Recyclarr. Those profiles score `x265 (HD)` at -10000, which rejects 1080p
HEVC releases. Tdarr is deployed against the same library and is capable of re-encoding
every file to HEVC.

Run together without a stated policy, the two contradict each other: Tdarr manufactures
precisely the files the quality profiles reject.

The contradiction is latent rather than active today. Every film is assigned to the `Any`
profile, which carries no custom format scores and has `upgradeAllowed: false`, so Radarr
reports nothing cutoff-unmet and will not re-grab a re-encoded file. The -10000 score sits on
`HD Bluray + WEB`, which no film uses. Moving the library onto the TRaSH profile would make
the contradiction active, and re-encoded files would then invite their own replacement.

## Decision

Acquire the best available source and keep it. Tdarr does not re-encode video.

Both libraries run transcode jobs with `disable_video: 'true'`, so the flow copies the video
stream through untouched and its work is limited to audio cleanup and container
normalisation. Health checks stay enabled, so Tdarr still reports corrupt or unplayable
files.

The transcode cache lives on the NFS share, not on node-local storage. Cache holds a full
copy of the file being worked on, and the largest files in the library are several times the
size of a node's root disk.

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
- **It forecloses a feedback loop.** The TRaSH profile scores these files at -10000 with
  upgrades allowed. Adopting that profile while re-encoding would have files replaced and
  re-encoded in turn.
- **Playback does not need it.** Jellyfin transcodes on the same Intel GPU on demand, so
  client compatibility is not a reason to re-encode at rest.

## Consequences

- Files already re-encoded stay HEVC. On the `Any` profile nothing re-grabs them, so the loss
  is taken and settled. They would become replacement candidates if the library moved onto
  `HD Bluray + WEB`.
- The TRaSH profiles Recyclarr maintains are not in use: every film is on `Any`. Custom format
  scoring therefore influences nothing today, which is worth resolving separately.
- Tdarr's role narrows to health checking, audio cleanup and container normalisation.
- Cache traffic crosses the network twice per file, read and written over NFS. That is slower
  than local cache and is accepted: no node has the capacity to hold a UHD remux.
- Reversing this means removing `x265 (HD)` from the unwanted formats in
  `recyclarr/configmap.yml` first, then setting `disable_video` to `'false'`. Doing it in the
  other order recreates the loop.
