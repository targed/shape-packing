# Submission Draft: hexinhex

**To:** Erich Friedman (via packing website)
**Subject:** New packing records for hexinhex (6 in 6)
**Problem Page:** https://erich-friedman.github.io/packing/hexinhex/index.html

---

Dear Dr. Friedman,

This is Luke Kaiser. We have found improved packing configurations for **hexinhex** (6 in 6):

### Methodology
We discovered these packings using a continuous global optimization solver combining randomized geometric basin-hopping with Separating Axis Theorem (SAT) collision constraints and SLSQP local gradient refinement. All solutions have been validated with 0 pairwise overlaps and strict container boundary containment.

### New Packings
| N | Our s (5 dec) | Our Exact s | Friedman Best s | Improvement | Attached Image |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 5 | 2.66668+ | 2.666678387864 | 2.66700+ | -0.000322 | `5.png` |
| 12 | 3.94165+ | 3.941648986550 | 3.94200+ | -0.000351 | `12.png` |

### Image Attachments
The replacement image files are attached directly with exact matching colors (#fdadac on #ffffff), orientation, no borders or text, and target website pixel dimensions (260x226 px):
- `5.png`
- `12.png`

Coordinate tables and certificates for each solution are included in the repository records.

Sincerely,
Luke Kaiser
