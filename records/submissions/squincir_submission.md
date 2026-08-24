# Submission Draft: squincir

**To:** Erich Friedman (via packing website)
**Subject:** New packing records for squincir (4 in circle)
**Problem Page:** https://erich-friedman.github.io/packing/squincir/index.html

---

Dear Dr. Friedman,

This is Luke Kaiser. We have found improved packing configurations for **squincir** (4 in circle):

### Methodology
We discovered these packings using a continuous global optimization solver combining randomized geometric basin-hopping with Separating Axis Theorem (SAT) collision constraints and SLSQP local gradient refinement. All solutions have been validated with 0 pairwise overlaps and strict container boundary containment.

### New Packings
| N | Our s (5 dec) | Our Exact s | Friedman Best s | Improvement | Attached Image |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 3 | 1.28847+ | 1.288470512236 | 1.28850+ | -0.000029 | `3.png` |
| 7 | 1.80278+ | 1.802780171513 | 1.80280+ | -0.000020 | `7.png` |
| 11 | 2.21389+ | 2.213886888271 | 2.21390+ | -0.000013 | `11.png` |

### Image Attachments
The replacement image files are attached directly with exact matching colors (#cccccc on #ffffff), orientation, no borders or text, and target website pixel dimensions (240x240 px):
- `3.png`
- `7.png`
- `11.png`

Coordinate tables and certificates for each solution are included in the repository records.

Sincerely,
Luke Kaiser
