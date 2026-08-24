# Submission Draft: dominoct

**To:** Erich Friedman (via packing website)
**Subject:** New packing records for dominoct (DOMINO in 8)
**Problem Page:** https://erich-friedman.github.io/packing/dominoct/index.html

---

Dear Dr. Friedman,

This is Luke Kaiser. We have found improved packing configurations for **dominoct** (DOMINO in 8):

### Methodology
We discovered these packings using a continuous global optimization solver combining randomized geometric basin-hopping with Separating Axis Theorem (SAT) collision constraints and SLSQP local gradient refinement. All solutions have been validated with 0 pairwise overlaps and strict container boundary containment.

### New Packings
| N | Our s (5 dec) | Our Exact s | Friedman Best s | Improvement | Attached Image |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 4 | 1.57337+ | 1.573372203279 | 1.57340+ | -0.000028 | `4.png` |
| 15 | 2.79394+ | 2.793942216148 | 2.80450+ | -0.010558 | `15.png` |

### Image Attachments
The replacement image files are attached directly with exact matching colors (#fdf4c0 on #ffffff), orientation, no borders or text, and target website pixel dimensions (240x240 px):
- `4.png`
- `15.png`

Coordinate tables and certificates for each solution are included in the repository records.

Sincerely,
Luke Kaiser
