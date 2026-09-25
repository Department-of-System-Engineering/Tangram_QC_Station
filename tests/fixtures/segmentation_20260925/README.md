User-supplied diagnostic capture from archive
`6db6cb60-13dc-4e43-915f-978894beb86b.zip` (2026-09-25).

The original Lab-only segmentation produced 11 raw candidates and 9 retained
candidates locally: blue triangles split under illumination differences and
a blue background component was also detected. The sampled HSV ranges retain
the actual closed triangle boundaries. Connected-component extraction must
preserve foreground pieces enclosed by a separate background ring.

Expected: seven parts, variant A, three blue pieces pass geometry checks.
The yellow ear remains imperfectly segmented and must not be forced to PASS.
The profile contains color/geometry settings only, no connection credentials.
