# CSS consolidation visual check (#190)

The ten PNGs show the same five screens before and after the stylesheet move:
Daily, Arena hub, Shop Discover, Profile and Leaderboard. They were captured from
`python scripts/preview_webapp.py` at a 390 × 844 browser viewport using the
same `?design-review` fixture. Each PNG is a full-page screenshot.

Daily, Arena, Profile and Leaderboard are pixel identical. Shop uses animated
decorative effects, so its two captures show different animation frames; visual
inspection found no layout or styling change. The source sheets were concatenated
in their original import order. The only declarations removed were 20 exact
same-selector, same-context, same-value duplicates superseded later in the cascade.
