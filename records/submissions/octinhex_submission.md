# Submission Draft: octinhex

**To:** Erich Friedman (via packing website)
**Subject:** New packing records for octinhex (8 in 6)
**Problem Page:** https://erich-friedman.github.io/packing/octinhex/index.html

---

Dear Dr. Friedman,

This is Luke Kaiser. We have found improved packing configurations for **octinhex** (8 in 6):

### Methodology
We discovered these packings using a continuous global optimization solver combining randomized geometric basin-hopping with Separating Axis Theorem (SAT) collision constraints and SLSQP local gradient refinement. All solutions have been validated with 0 pairwise overlaps and strict container boundary containment.

### New Packings
| N | Our s (5 dec) | Our Exact s | Friedman Best s | Improvement | Attached Image |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 3 | 2.88963+ | 2.889629996220 | 2.89000+ | -0.000370 | `3.png` |
| 8 | 4.56656+ | 4.566557709973 | 4.56700+ | -0.000442 | `8.png` |

### Image Attachments
The replacement image files are attached directly with exact matching colors (#fafbe5 on #ffffff), orientation, no borders or text, and target website pixel dimensions (250x216 px):
- `3.png`
- `8.png`

Coordinate tables and certificates for each solution are included in the repository records.

Sincerely,
Luke Kaiser
