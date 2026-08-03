# Test Coverage Requirements

Scope:
pytest suite (tests/), coverage policy, and expectations around what must be testable.

1. General Policy

- The system SHALL have an automated test suite that can be run via pytest.
- WHEN coverage is considered THEN:
  - meaningful correctness checks are prioritized over forcing 100% coverage.
- Tests SHOULD:
  - validate geometry correctness,
  - validate problem parsing,
  - validate solution verification logic,
  - validate scheduler/autoresearch selection logic,
  - avoid long-running solver calls via mocking where appropriate.

2. Core Modules

- WHEN geometry.py is changed THEN:
  - tests SHALL confirm:
    - regular polygon vertices and normals are correct,
    - special shapes (TAN, DOMINO) produce expected vertices,
    - overlap checks match expected SAT behavior for known configurations.

- WHEN solution_tools.py or verify_solution.py is changed THEN:
  - tests SHALL include:
    - a valid packing that passes,
    - a packing with overlap that fails,
    - a packing out-of-bounds that fails,
    - metric-mismatch cases.

- WHEN agent_loop.py or ranker.py is changed THEN:
  - tests SHALL confirm:
    - problem selection avoids trivial/proved_optimal families,
    - fairness/penalty logic reduces overfitting to single problems,
    - compact names are normalized before use.

- WHEN optimization.py is changed THEN:
  - tests SHOULD confirm:
    - initialization is reasonable,
    - objective computation is consistent,
    - external solvers (e.g., scipy) are wrapped safely (mocked where necessary).

3. Problem-Specific Expectations

- WHEN a new problem family is added THEN:
  - at least one test SHOULD validate:
    - that its geometry is built,
    - that a simple valid/invalid packing is classified correctly.

4. Prohibitions

- Tests SHALL NOT:
  - rely on external network calls,
  - permanently modify PACKING_REFERENCE or shared files.
