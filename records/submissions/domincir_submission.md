# Submission Draft: domincir

**To:** Erich Friedman (via packing website)
**Subject:** New packing records for domincir (DOMINO in CIRCLE)
**Problem Page:** https://erich-friedman.github.io/packing/domincir/index.html

---

Dear Dr. Friedman,

This is Luke Kaiser. We have found improved packing configurations for **domincir** (DOMINO in CIRCLE):

### Methodology
We discovered these packings using a continuous global optimization solver combining randomized geometric basin-hopping with Separating Axis Theorem (SAT) collision constraints and SLSQP local gradient refinement. All solutions have been validated with 0 pairwise overlaps and strict container boundary containment.

### New Packings
| N | Our s (5 dec) | Our Exact s | Friedman Best s | Improvement | Attached Image |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 18 | 3.77916+ | 3.779156069737 | 3.78120+ | -0.002044 | `18.png` |
| 19 | 3.87882+ | 3.878816717652 | 3.89340+ | -0.014583 | `19.png` |

### Image Attachments
The replacement image files are attached directly with exact matching colors (#fed4d1 on #ffffff), orientation, no borders or text, and target website pixel dimensions (250x250 px):
- `18.png`
- `19.png`

Coordinate tables and certificates for each solution are included in the repository records.

Sincerely,
Luke Kaiser
