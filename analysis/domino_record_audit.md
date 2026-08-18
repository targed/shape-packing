# Domino Record Audit

This note audits four proposed domino records against the repository’s benchmark data, the repo’s geometric domino definition, and the available verification logs.

## Sources
- Official benchmark data: [packingVerification/domincir.json](packingVerification/domincir.json), [packingVerification/dominhex.json](packingVerification/dominhex.json), [packingVerification/dominpen.json](packingVerification/dominpen.json)
- Candidate solutions: [records/domincir/18_DOMINO_in_CIRCLE/solution.json](records/domincir/18_DOMINO_in_CIRCLE/solution.json), [records/domincir/19_DOMINO_in_CIRCLE/solution.json](records/domincir/19_DOMINO_in_CIRCLE/solution.json), [records/dominhex/21_DOMINO_in_6/solution.json](records/dominhex/21_DOMINO_in_6/solution.json), [records/dominpen/21_DOMINO_in_5/solution.json](records/dominpen/21_DOMINO_in_5/solution.json)
- Verification logs: [records/domincir/18_DOMINO_in_CIRCLE/verification.txt](records/domincir/18_DOMINO_in_CIRCLE/verification.txt), [records/domincir/19_DOMINO_in_CIRCLE/verification.txt](records/domincir/19_DOMINO_in_CIRCLE/verification.txt), [records/dominhex/21_DOMINO_in_6/verification.txt](records/dominhex/21_DOMINO_in_6/verification.txt), [records/dominpen/21_DOMINO_in_5/verification.txt](records/dominpen/21_DOMINO_in_5/verification.txt)
- Domino shape definition: [src/shape_packing/geometry.py](src/shape_packing/geometry.py), [src/shape_packing/solution_tools.py](src/shape_packing/solution_tools.py)

## Domino definition check
The repository’s domino is defined as a `2 x 1` rectangle in [src/shape_packing/geometry.py](src/shape_packing/geometry.py). That matches the standard domino interpretation used by the website and the benchmark files. The verification code reconstructs that same shape and checks overlap / containment directly, so the domino geometry itself is not the concern here.

## Findings

| Problem | Candidate s | Official benchmark | Margin | Verdict |
| :--- | ---: | ---: | ---: | :--- |
| 18_DOMINO_in_CIRCLE | 3.7791560697370707 | 3.78121+ | 0.002053930263 | Valid, better than benchmark |
| 19_DOMINO_in_CIRCLE | 3.8788167176520854 | 3.89344+ | 0.014623282348 | Valid, better than benchmark |
| 21_DOMINO_in_6 | 4.4394957939916555 | 4.59807+ | 0.158574206008 | Valid, better than benchmark |
| 21_DOMINO_in_5 | 5.4121555761458735 | 5.55308+ | 0.140924423854 | Valid, better than benchmark |

## Interpretation
- The four candidates all beat the published Friedman values at the five-decimal level.
- The verification logs for all four report `VALID` with zero pairwise overlaps.
- For the circle-container cases, the repository’s search/optimization pipeline may use a polygon approximation internally, but the verification step checks the true circle boundary directly. That means the approximation concern does not invalidate these two results the way it did for the earlier `22_CIRCLE_in_6` review.
- No evidence turned up of a domino-definition mismatch, area mismatch, or a representation inconsistency with the website’s domino packing pages.

## Conclusion
All four proposed domino records are currently supported by the repository evidence and should be treated as genuine records under the repo’s verification rules.