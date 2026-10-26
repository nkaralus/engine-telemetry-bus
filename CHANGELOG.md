# Changelog

## 0.1.0
- Registry: /24 subnets in 10.0.0.0/8, lowest-free or explicit host allocation, duplicate IP and
  duplicate (case-insensitive) name prevention, strict JSON load, atomic save, revision + fingerprint.
- Gates: GI_1 boundary, GI_2 isolation + lexical path traversal, GI_3 AABB overlap + filesystem guard.
- PathGuard: refuses symlinks, mountpoints, cross-device paths, hardlinked writes, root escapes,
  and project roots that are filesystem roots, home, or system directories.
- CLI: `python -m subnetbus`.
