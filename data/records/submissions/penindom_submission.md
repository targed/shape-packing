# Submission Draft: penindom

**To:** Erich Friedman (via packing website)
**Subject:** New packing records for penindom (5 in DOMINO)
**Problem Page:** https://erich-friedman.github.io/packing/penindom/index.html

---

Dear Dr. Friedman,

This is Luke Kaiser. We have found improved packing configurations for **penindom** (5 in DOMINO):

### Methodology
We discovered these packings using a continuous global optimization solver combining randomized geometric basin-hopping with Separating Axis Theorem (SAT) collision constraints and SLSQP local gradient refinement. All solutions have been validated with 0 pairwise overlaps and strict container boundary containment.

### New Packings
| N | Our s (5 dec) | Our Exact s | Friedman Best s | Improvement | Attached Image |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 6 | 2.69228+ | 2.692284327857 | 2.69230+ | -0.000016 | `6.png` |
| 7 | 2.91977+ | 2.919773978456 | 2.91980+ | -0.000026 | `7.png` |

### Image Attachments
The replacement image files are attached directly with exact matching colors (#cae6f8 on #ffffff), orientation, no borders or text, and target website pixel dimensions (250x125 px):
- `6.png`
- `7.png`

Coordinate tables and certificates for each solution are included in the repository records.

Sincerely,
Luke Kaiser
