# Image generation prompts

Created with the built-in image-generation tool. The banner uses the generated icon as its reference. Original PNGs are preserved without postprocessing.

## Icon

```text
Use case: logo-brand.
Create a finished original square app icon for "notedrop", a tiny terminal tool for agents to exchange notes in a shared folder.
Asset type: a production-quality 1024x1024 app icon, one icon only, no presentation board.
Visual direction: refined old terminal / phosphor display aesthetic. Near-black deep forest background (#07130f), bright mint-phosphor green (#57f2a0), a little pale mint (#d7ffe8). Very strong contrast. Flat pixel-geometric construction with deliberate stepped corners and thick consistent strokes, not 3D or glossy.
Subject: one distinctive centered symbol: a compact folded-corner paper note hovering immediately above a sturdy open inbox tray. On the note is a small simple terminal ">_" symbol. The note and tray together should feel like a coherent bold logo for dropping a message. The paper's folded upper-right corner is clear. Keep the mark simple, roughly 60% of canvas width, balanced and readable at small size. Use a single small square between the note and the tray to suggest a falling packet only if composition remains clean.
Background: a very dark green square canvas with an inset gently rounded square tile; subtle tonal separation. A restrained phosphor glow immediately around bright edges, but crisp geometry and no busy texture.
Constraints: create original identity, no existing company logos, no robot or mascot, no brain, no network node diagrams, no letters other than the tiny >_ symbol, no wordmark, no captions, no watermark, no mockup, no perspective. Beautiful, minimal, confident, exceptionally clean silhouette.
```

## Banner

```text
Use case: logo-brand.
Asset type: finished wide landscape GitHub README banner for notedrop, aspect ratio 3:1, ideally 1800x600.
Reference image: the attached image is the notedrop icon to reuse as the identity, not another company's logo. Preserve its distinctive folded paper with >_ prompt, one falling square, and pixel-stepped inbox tray. Recompose this identity into a banner. Remove the icon's surrounding rounded app-tile border; use just the coherent note-and-inbox mark as the large emblem at the left.
Layout: beautiful restrained typography-led terminal identity on a near-black deep forest background. Generous negative space. Left third: the bright mint note/inbox emblem. Right two thirds: enormous perfectly legible lowercase monospace wordmark "notedrop", pale warm mint, with one small mint rectangular terminal cursor immediately after it. Below the wordmark in smaller readable monospaced type: "A shared-folder mailbox for agents." Below that, a quiet mint command line: "$ notedrop send bob 'hello'"
Use exactly these three text strings and no additional words. Spell notedrop exactly n-o-t-e-d-r-o-p.
Style: polished late-1980s phosphor terminal visual identity; crisp pixel geometry, restrained close phosphor glow, extremely faint scanlines, a single thin dark-green rectangular keyline well inset from the image edges. The wordmark is strong squared monospace lettering, clean rather than distressed. No excessive bloom, no drop shadows, no 3D perspective, no mockup scene, no robot, no branded third-party symbols, no icons unrelated to notes. Maintain ample padding. Everything visually balanced and immediately legible when scaled to a GitHub README width of 900px.
```
# Social card

Built-in image generation, with `notedrop-banner.png` as reference. Saved
unchanged as `notedrop-social.png` (1774 × 887 pixels; 958,935 bytes).

```text
Use case: logo-brand. Create a GitHub repository social preview card for notedrop using the attached banner as the visual identity reference. Output a PNG, landscape 2:1 aspect ratio, preferably 1280x640, optimized under 1 MB. Preserve its distinctive green pixel-art folded terminal note with >_ dropping a square into an inbox tray, and lowercase monospace notedrop wordmark with green block cursor. Recompose with generous margins for a 2:1 social card: icon on left, wordmark and subtitle on right. Exact text: "notedrop" and "A shared-folder mailbox" then "for agents." No other text. Palette dark forest #07130F, phosphor #57F2A0 and pale mint #D7FFE8. Crisp controlled pixel geometry, beautiful restrained retro terminal identity. Solid flat background and mostly solid colors, minimal glow, no grain, no noise, no tiny decorative elements, no gradients to keep file compact. Preserve the recognizable icon design; make text legible at thumbnail size.
```

