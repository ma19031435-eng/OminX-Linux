# OminXOS website

The public-facing OminXOS site: a single, dependency-free static page that presents
the platform vision, Windows application compatibility, gaming, the desktop,
software installation, updates, education and creator use, security, and the 1.0
release model.

## View locally

Open `index.html` directly, or serve the folder over HTTP:

```sh
python3 -m http.server 8080 --directory website
```

Then visit `http://localhost:8080`.

## Structure

```text
website/
  index.html                       Single page, semantic section per topic
  og-image.png                     Social preview card (1200 x 630)
  assets/css/styles.css            Aurora design system and responsive layout
  assets/js/main.js                Progressive enhancement only
  assets/brand/ominx-icon.svg      Original OminX mark and favicon
  assets/brand/ominx-aurora-wallpaper.svg
  assets/fonts/                    Inter and JetBrains Mono (variable, SIL OFL)
```

## Notes

- No build step, no frameworks, and no third-party network requests. Fonts are
  bundled locally; icons are inline SVG.
- The page works without JavaScript. Scripts add scroll-state navigation,
  reveal-on-scroll, a single count-up for the compatibility figure, and a subtle
  pointer tilt on the desktop illustration; all motion respects
  `prefers-reduced-motion`.
- The desktop, store, login, update, and compatibility panels are stylized
  illustrations of the OminXOS interface, built from the original Aurora palette
  and artwork in this repository. They are not screenshots.
- Compatibility figures (89%) are testing targets, not guarantees. Content mirrors
  the project brief and the repository documentation.
- Fonts: Inter and JetBrains Mono, licensed under the SIL Open Font License; see
  `assets/fonts/LICENSE-Inter.txt` and `assets/fonts/LICENSE-JetBrainsMono.txt`.
