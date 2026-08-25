# Submission Draft: triindom

**To:** Erich Friedman (via packing website)
**Subject:** New packing records for triindom (3 in DOMINO)
**Problem Page:** https://erich-friedman.github.io/packing/triindom/index.html

---

Dear Dr. Friedman,

This is Luke Kaiser. We have found improved packing configurations for **triindom** (3 in DOMINO):

### Methodology
We discovered these packings using a continuous global optimization solver combining randomized geometric basin-hopping with Separating Axis Theorem (SAT) collision constraints and SLSQP local gradient refinement. All solutions have been validated with 0 pairwise overlaps and strict container boundary containment.

### New Packings
| N | Our s (5 dec) | Our Exact s | Friedman Best s | Improvement | Attached Image |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 22 | 2.41951+ | 2.419505003282 | 2.42212+ | -0.002615 | `22.png` |

### Image Attachments
The replacement image files are attached directly with exact matching colors (#dee1f1 on #ffffff), orientation, no borders or text, and target website pixel dimensions (250x125 px):
- `22.png`

Coordinate tables and certificates for each solution are included in the repository records.

Sincerely,
Luke Kaiser
