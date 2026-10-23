# dwork GitHub social preview

Mode: built-in imagegen.
References: GitHub repository social card template (proportions and safe area only),
docs/assets/readme-hero.png (existing dwork brand and illustration style).
Current export: github-social-card-v2.png, 1280 x 640, opaque PNG.
Revision 2 restores the OS logos and adds the packaged tray glyph in the footer.

## Initial generation prompt

```text
Use case: ads-marketing.
Asset: GitHub repository social preview card for the open source developer tool dwork.
Create a polished final social card, exactly 1280 x 640 pixels, landscape 2:1. Adapt the existing dwork hero in Image 2 into this new proportion. Image 1 is ONLY a reference for 2:1 dimensions and the protected inner safe area. Do not copy its content or appearance. Do not include any GitHub logo, template title, red guides, pale pink border, or template instructions.
Image 2 is the visual brand reference: preserve its premium matte charcoal 3D terminal/workspace style, deep navy-black background, restrained luminous emerald green accents, blue/green/purple service blocks and database cylinder, clean white wordmark. Recompose its elements for a 2:1 social card rather than squeezing or cropping the wide hero.
Composition: very large bold white lowercase wordmark 'dwork' at left, exact spelling d-w-o-r-k. Under it, elegant readable cool-gray sans serif tagline on two lines. On the right, a single isometric dark terminal window with glowing green trim reading '$ dwork', arranged behind three small blue, green, and violet service blocks and one dark database cylinder joined with subtle emerald connections. A faint inactive workspace may sit behind the active one, suggesting switching, but the overall card must stay uncluttered. Use the soft cinematic lighting and textured materials of Image 2, with crisp typography and generous negative space.
Render ONLY these exact texts:
'dwork'
'Switch your development'
'workspace with one command.'
'$ dwork'
'Linux · macOS · WSL2'
'github.com/hayyaun/dwork'
The first two tagline lines are together below the wordmark. The platform line and repository address are discreet readable footer text. No other words.
Keep every text element and every important illustration detail at least 80 pixels from all four canvas edges, following the template safe margins. Outer background can bleed. No text overlaps. A finished professional open-source developer product social graphic, not a screenshot or a framed webpage. Opaque background, no watermark.

```

## Refinement prompt

```text
Refine this dwork social preview card for safe cropping. Keep the exact same dark 3D artwork, two-workspace switching concept, wordmark, typography, text, colors, and 2:1 composition. Make only two finishing adjustments:
1. Remove the decorative Linux penguin, Apple, Windows, and GitHub logo icons in the footer. Retain the two footer text strings exactly: "Linux · macOS · WSL2" and "github.com/hayyaun/dwork". The footer should be simple text only.
2. Increase empty outer crop-safe margins: all typography, terminal window, service blocks, database cylinder, and platform should sit within the central area bounded by x=8% to 92% of canvas width and y=14% to 86% of canvas height. Reduce and reposition the existing illustration slightly as needed; do not alter its design. The edge background is uninterrupted dark charcoal/navy. Keep the large wordmark and tagline aligned at the left safe margin. The whole repository URL must end before the right safe margin. Do not add borders or crop marks.
Exact copy remains:
"dwork"
"Switch your development"
"workspace with one command."
"$ dwork"
"Linux · macOS · WSL2"
"github.com/hayyaun/dwork"
Preserve text accuracy and excellent readability at thumbnail sizes. Output a finished opaque 2:1 landscape GitHub social card, ideally 1280 x 640 pixels.
```

## Revision 2: OS logos and tray glyph

References: the first exported social card, the original generated OS-logo footer,
and the project's packaged `companion/src/dwork_tray/assets/tray.png`.
Generated with the built-in image tool; exported with Lanczos scaling and lossless
PNG compression using FFmpeg's mixed prediction filter.

```text
Edit the dwork social card in Image 1. Preserve its approved design and change ONLY the footer.
Input roles:
- Image 1 is the edit target: the current final social card. Keep its wordmark, tagline, 3D terminal artwork, colors, lighting, dark backdrop, 2:1 layout and generous safe margins unchanged.
- Image 2 is a reference ONLY for the Linux, Apple/macOS, and Windows OS logos shown in its lower-left footer. Do not copy its overall layout, tighter margins, or its GitHub Octocat icon.
- Image 3 is the actual dwork tray icon: a transparent white outline mark consisting of two opposed open perspective window frames. Use this exact recognizable geometry, with two open halves separated by a central gap; do not substitute a generic tray, app, cube, or window icon.

Footer changes:
1. Restore the small monochrome Linux penguin, Apple, and four-pane Windows logos from Image 2 in a tidy horizontal group immediately before the existing "Linux · macOS · WSL2" platform text in the lower-left footer. Each logo about 22–28 pixels high at 1280-pixel card width. Retain the platform text verbatim and keep the entire row within the safe margin.
2. Add the actual tray glyph from Image 3 as one understated white/cool-gray mark about 28–32 pixels high immediately before "github.com/hayyaun/dwork" in the lower-right footer, vertically centered with the URL. Keep its crisp open outline and transparent background. No surrounding badge, square, glow, additional label, or Octocat logo. Keep the full URL inside the right safe margin.

No other changes. Preserve ALL exact existing text:
"dwork"
"Switch your development"
"workspace with one command."
"$ dwork"
"Linux · macOS · WSL2"
"github.com/hayyaun/dwork"
Keep the rest of the card visually identical to Image 1, especially the large dwork wordmark and terminal/service illustration. Final output is an opaque 2:1 landscape GitHub social preview, ideally exactly 1280 x 640 pixels, with important content at least 80 pixels from the canvas edges.
```

