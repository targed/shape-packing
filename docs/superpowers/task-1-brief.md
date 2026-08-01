### Task 1: Add `--initial-positions` to Rust Solver

**Files:**
- Modify: `packer_rs/Cargo.toml`
- Modify: `packer_rs/src/main.rs`

**Interfaces:**
- Consumes: JSON file containing `[x1, y1, a1, x2, y2, a2, ...]` array.
- Produces: Optimization result starting from those coordinates.

- [ ] **Step 1: Add serde and serde_json to Cargo.toml**

```toml
# Append to dependencies in packer_rs/Cargo.toml
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
```

- [ ] **Step 2: Update Args struct in `main.rs`**

```rust
// Add to Args struct
    #[arg(long)]
    initial_positions: Option<String>,
```

- [ ] **Step 3: Modify `run_attempt` signature and usage in `main.rs`**

Update `run_attempt` to accept `initial_positions: Option<&Vec<f64>>`. Pass it down from `main`.

```rust
// In main.rs, before the par_iter loop, read the initial positions if provided:
    let initial_positions = if let Some(path) = &args.initial_positions {
        let contents = fs::read_to_string(path).expect("Failed to read initial positions file");
        let positions: Vec<f64> = serde_json::from_str(&contents).expect("Invalid JSON in initial positions");
        Some(positions)
    } else {
        None
    };
```

Pass `initial_positions.as_ref()` into `run_attempt`.

- [ ] **Step 4: Use `initial_positions` in `run_attempt`**

In `run_attempt` inside `main.rs`, replace the `x0` initialization:

```rust
    let mut x0: Vec<f64> = if let Some(init_pos) = initial_positions {
        // If provided, use it and add a tiny perturbation so parallel attempts aren't identical
        init_pos.iter().map(|&v| v + (rng.gen::<f64>() - 0.5) * 1e-5).collect()
    } else if rng.gen_bool(0.5) {
        // ... existing random init ...
```

- [ ] **Step 5: Compile and verify**

```bash
cd packer_rs
cargo build --release
```
Expected: successful compilation.

- [ ] **Step 6: Commit**

```bash
git add packer_rs/Cargo.toml packer_rs/src/main.rs
git commit -m "feat: allow packer_rs to accept initial-positions"
```

---
