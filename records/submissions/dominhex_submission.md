# Submission Draft: dominhex

**To:** Erich Friedman (via packing website)
**Subject:** New packing records for dominhex (DOMINO in 6)
**Problem Page:** https://erich-friedman.github.io/packing/dominhex/index.html

---

Dear Dr. Friedman,

This is Luke Kaiser. We have found improved packing configurations for **dominhex** (DOMINO in 6):

### Methodology
We discovered these packings using a continuous global optimization solver combining randomized geometric basin-hopping with Separating Axis Theorem (SAT) collision constraints and SLSQP local gradient refinement. All solutions have been validated with 0 pairwise overlaps and strict container boundary containment.

### New Packings
| N | Our s (5 dec) | Our Exact s | Friedman Best s | Improvement | Attached Image |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 2 | 1.51967+ | 1.519671772343 | 1.51970+ | -0.000028 | `2.png` |
| 11 | 3.33392+ | 3.333917266858 | 3.34790+ | -0.013983 | `11.png` |
| 12 | 3.44304+ | 3.443042419757 | 3.46080+ | -0.017758 | `12.png` |
| 14 | 3.65081+ | 3.650805162046 | 3.67230+ | -0.021495 | `14.png` |
| 16 | 3.87031+ | 3.870307629844 | 3.90290+ | -0.032592 | `16.png` |
| 17 | 4.00242+ | 4.002423086173 | 4.01160+ | -0.009177 | `17.png` |
| 20 | 4.35105+ | 4.351046532676 | 4.36720+ | -0.016153 | `20.png` |
| 21 | 4.43950+ | 4.439495793992 | 4.59810+ | -0.158604 | `21.png` |
| 22 | 4.54230+ | 4.542298637202 | 4.59810+ | -0.055801 | `22.png` |
| 28 | 5.07599+ | 5.075988007438 | 5.14000+ | -0.064012 | `28.png` |

### Image Attachments
The replacement image files are attached directly with exact matching colors (#fed4d1 on #ffffff), orientation, no borders or text, and target website pixel dimensions (260x225 px):
- `2.png`
- `11.png`
- `12.png`
- `14.png`
- `16.png`
- `17.png`
- `20.png`
- `21.png`
- `22.png`
- `28.png`

Coordinate tables and certificates for each solution are included in the repository records.

Sincerely,
Luke Kaiser
