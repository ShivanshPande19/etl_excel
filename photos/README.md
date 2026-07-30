# Staff photos

Raw photos as received, one per staff member, named by their **slug**.

| Person | File |
|---|---|
| Deepak | `deepak.jpeg` |
| Delip | `delip.jpeg` |
| Anshu | `anshu.jpeg` |
| Sunil | `sunil.jpeg` |
| Vansh Singh Fartyal | `vansh.jpeg` |

Supported extensions: `.jpg`, `.jpeg`, `.png`, `.webp`. A roughly portrait (3:4)
photo looks best. Until a photo is added, that card shows a "PHOTO" placeholder.

## These are not the ones on the cards

The cards use the cleaned-up versions in [`groomed/`](groomed/README.md) —
even studio background, levelled, standard ID framing and colour corrected.
The files here are kept as the untouched originals.

To add or replace someone's photo: drop the new file here, then re-run

```bash
python3 tools/groom_photos.py --contact-sheet   # -> photos/groomed/
python3 tools/render_cards.py                   # -> id-cards/, PDF, preview
```

The card loader prefers `photos/groomed/<slug>.*` and falls back to
`photos/<slug>.*`, so a brand-new raw photo will still appear on its card
before it has been groomed.
