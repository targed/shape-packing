# Pure Rust Standalone Worker Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pure Rust standalone volunteer worker binary (`shape-packing-worker`) that runs multithreaded shape packing computations without Python dependencies, and establish an automated multi-platform GitHub Releases CI/CD pipeline.

**Architecture:** A lightweight (~4MB) native binary built inside the existing `packer_rs` crate linking `packer_rs::solver::solve` directly in memory. It uses `ureq` for synchronous HTTP communication with the coordinator, `ctrlc` for graceful signal handling, an interactive CLI wizard for first-run configuration persisted in `~/.shape_packing_worker.json`, and an autostart subsystem supporting Windows Registry, Linux XDG desktop entries, and macOS LaunchAgents. GitHub Actions compiles, packages, and signs release tarballs/zips across Windows, Linux, and macOS.

**Tech Stack:** Rust 2021, `packer_rs::solver`, Rayon, `clap` v4 (derive), `ureq` v2 (json), `serde` / `serde_json`, `ctrlc` v3.4, GitHub Actions CI/CD.

## Global Constraints

- Standalone executable must have zero Python or PyO3 runtime dependencies when built with `--no-default-features`.
- Client configuration file must be stored in `~/.shape_packing_worker.json` and share the JSON schema with existing desktop client.
- Rayon concurrency must match the user's allocated `--cores` parameter.
- Coordinator communication must match existing `/api/v1/*` endpoints (`/api/v1/workers/register`, `/api/v1/work`, `/api/v1/work/heartbeat`, `/api/v1/solutions`, `/api/v1/workers/deregister`).
- Autostart operations must not require root or administrator elevation.
- Multi-platform release matrix must produce `shape-packing-worker-windows-x86_64.zip`, `shape-packing-worker-linux-x86_64.tar.gz`, and `shape-packing-worker-macos-universal.tar.gz` with `checksums.sha256`.

---

### Task 1: Update Cargo Configuration for Standalone Worker Target

**Files:**
- Modify: `packer_rs/Cargo.toml`

**Interfaces:**
- Consumes: Existing `packer_rs` crate dependencies.
- Produces: `shape-packing-worker` binary target and dependencies (`ureq`, `ctrlc`).

- [ ] **Step 1: Update `packer_rs/Cargo.toml` with binary definition and dependencies**

Add `ureq` and `ctrlc` under `[dependencies]` and define `[[bin]] name = "shape-packing-worker" path = "src/bin/worker.rs"`:

```toml
[dependencies]
clap = { version = "4", features = ["derive"] }
rand = "0.8"
rand_chacha = "0.3"
rayon = "1.10"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
pyo3 = { version = "0.22", features = ["extension-module", "abi3-py310"], optional = true }
ureq = { version = "2.10", features = ["json"] }
ctrlc = "3.4"

[[bin]]
name = "shape-packing-worker"
path = "src/bin/worker.rs"
```

- [ ] **Step 2: Create a minimal stub for `packer_rs/src/bin/worker.rs`**

```rust
fn main() {
    println!("shape-packing-worker stub");
}
```

- [ ] **Step 3: Run `cargo check` to verify dependencies resolve**

Run: `cargo check --bin shape-packing-worker --no-default-features --manifest-path packer_rs/Cargo.toml`  
Expected: `Finished dev profile [unoptimized + debuginfo] target(s)`

- [ ] **Step 4: Commit**

```bash
git add packer_rs/Cargo.toml packer_rs/src/bin/worker.rs
git commit -m "build: add shape-packing-worker binary target and ureq/ctrlc dependencies"
```

---

### Task 2: Implement Worker Configuration & Interactive Setup

**Files:**
- Create: `packer_rs/src/worker/mod.rs`
- Create: `packer_rs/src/worker/config.rs`
- Modify: `packer_rs/src/lib.rs` (expose `worker` module when building binary)

**Interfaces:**
- Consumes: `serde`, `serde_json`, user home directory.
- Produces: `WorkerConfig` struct with `load()`, `save()`, `resolve_interactive()`, and `default_config_path()`.

- [ ] **Step 1: Write unit tests for configuration serialization and deserialization**

In `packer_rs/src/worker/config.rs`:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_config_serialization_roundtrip() {
        let config = WorkerConfig {
            server_url: "http://example.com:8000".to_string(),
            username: "tester".to_string(),
            worker_id: Some("123e4567-e89b-12d3-a456-426614174000".to_string()),
            cores: 4,
        };
        let serialized = serde_json::to_string(&config).unwrap();
        let deserialized: WorkerConfig = serde_json::from_str(&serialized).unwrap();
        assert_eq!(deserialized.server_url, "http://example.com:8000");
        assert_eq!(deserialized.username, "tester");
        assert_eq!(deserialized.worker_id, Some("123e4567-e89b-12d3-a456-426614174000".to_string()));
        assert_eq!(deserialized.cores, 4);
    }

    #[test]
    fn test_config_preserves_extra_fields() {
        let json_str = r#"{"server_url":"http://test","username":"bob","extra_gui_field":true}"#;
        let config: WorkerConfig = serde_json::from_str(json_str).unwrap();
        assert_eq!(config.server_url, "http://test");
        assert_eq!(config.username, "bob");
        assert_eq!(config.cores, 1);
    }
}
```

- [ ] **Step 2: Run tests to verify they fail before implementation**

Run: `cargo test --bin shape-packing-worker --no-default-features --manifest-path packer_rs/Cargo.toml config::tests`  
Expected: FAIL (module not defined)

- [ ] **Step 3: Implement `WorkerConfig` and persistence logic**

In `packer_rs/src/worker/config.rs`:
- Define `WorkerConfig` with `server_url`, `username`, `worker_id: Option<String>`, `cores: usize` (with default serde values).
- Implement `home_dir() -> PathBuf` checking `USERPROFILE` on Windows and `HOME` on Unix.
- Implement `default_config_path() -> PathBuf` returning `~/.shape_packing_worker.json`.
- Implement `load(path: Option<&Path>) -> Result<WorkerConfig, String>`.
- Implement `save(path: Option<&Path>, config: &WorkerConfig) -> Result<(), String>`. When saving, read existing JSON as `serde_json::Value` (if present) so desktop GUI keys are preserved.
- Implement `resolve_interactive(cli_server, cli_username, cli_cores, no_interactive) -> Result<WorkerConfig, String>`.
  - If config exists on disk: load and merge any CLI overrides.
  - If config does not exist and interactive: prompt user on `std::io::stdin()` with sensible defaults (system username, `http://localhost:8000`, `num_cpus`). Save to disk.
  - If config does not exist and non-interactive: check environment variables or use defaults.

- [ ] **Step 4: Expose `worker` in `packer_rs/src/lib.rs` and run tests**

Run: `cargo test --no-default-features --manifest-path packer_rs/Cargo.toml worker::config::tests`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packer_rs/src/worker/mod.rs packer_rs/src/worker/config.rs packer_rs/src/lib.rs
git commit -m "feat(worker): implement WorkerConfig persistence and interactive onboarding"
```

---

### Task 3: Implement Coordinator HTTP Client

**Files:**
- Create: `packer_rs/src/worker/client.rs`
- Modify: `packer_rs/src/worker/mod.rs`

**Interfaces:**
- Consumes: `ureq`, `WorkerConfig`.
- Produces: `CoordinatorClient` with methods:
  - `register(username, worker_id, cores) -> Result<String, String>`
  - `lease_work(worker_id, cores) -> Result<Option<WorkAssignment>, String>`
  - `send_heartbeat(worker_id, work_id, attempts_completed, best_s) -> Result<(), String>`
  - `submit_solution(worker_id, work_id, problem, s, coordinates) -> Result<SolutionResponse, String>`
  - `deregister(worker_id) -> Result<(), String>`

- [ ] **Step 1: Define API payload structs and write client unit tests**

In `packer_rs/src/worker/client.rs`:
- Define `WorkAssignment`:
  ```rust
  #[derive(Debug, Clone, serde::Deserialize)]
  pub struct WorkAssignment {
      pub work_id: String,
      pub problem: String,
      pub shape: String,
      pub n: usize,
      #[serde(default = "default_container")]
      pub container: String,
      #[serde(default = "default_attempts")]
      pub attempts: usize,
      pub target_s: Option<f64>,
      #[serde(default = "default_lease_seconds")]
      pub lease_seconds: u64,
      pub initial_positions: Option<Vec<f64>>,
  }
  ```
- Define `SolutionResponse`:
  ```rust
  #[derive(Debug, Clone, serde::Deserialize)]
  pub struct SolutionResponse {
      pub status: String,
      #[serde(default)]
      pub verified: bool,
      #[serde(default)]
      pub record_broken: bool,
      pub message: Option<String>,
  }
  ```
- Write unit tests verifying JSON deserialization of sample coordinator responses.

- [ ] **Step 2: Run test to verify it passes for response parsing**

Run: `cargo test --no-default-features --manifest-path packer_rs/Cargo.toml worker::client::tests`  
Expected: PASS

- [ ] **Step 3: Implement `CoordinatorClient`**

In `packer_rs/src/worker/client.rs`:
- Create `CoordinatorClient::new(server_url: String) -> Self`.
- Normalize `server_url` (strip trailing slashes).
- Implement `register()`: calls `POST /api/v1/workers/register`.
- Implement `lease_work()`: calls `GET /api/v1/work?worker_id={}&cores={}&lease_seconds=300`. Returns `Ok(None)` if status is 204.
- Implement `send_heartbeat()`: calls `POST /api/v1/work/heartbeat`.
- Implement `submit_solution()`: calls `POST /api/v1/solutions`.
- Implement `deregister()`: calls `POST /api/v1/workers/deregister`.

- [ ] **Step 4: Commit**

```bash
git add packer_rs/src/worker/client.rs packer_rs/src/worker/mod.rs
git commit -m "feat(worker): implement CoordinatorClient HTTP protocol with ureq"
```

---

### Task 4: Implement Native Autostart Subsystem

**Files:**
- Create: `packer_rs/src/worker/autostart.rs`
- Modify: `packer_rs/src/worker/mod.rs`

**Interfaces:**
- Consumes: OS standard libraries, `std::env::current_exe()`.
- Produces: `enable_autostart()`, `disable_autostart()`, `autostart_status()`.

- [ ] **Step 1: Write platform-agnostic autostart interface & tests**

In `packer_rs/src/worker/autostart.rs`:
- Define `AutostartStatus { enabled: bool, target_path: Option<String> }`.
- Write unit test checking that `autostart_status()` executes without panic.

- [ ] **Step 2: Implement Windows, Linux, and macOS autostart logic**

In `packer_rs/src/worker/autostart.rs`:
- **Windows implementation:**
  - Uses `std::process::Command` calling `reg.exe` for HKCU without pulling in heavyweight `winreg` or `windows-sys` crates:
    - Enable: `reg add HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v ShapePackingWorker /t REG_SZ /d "<exe_path>" /f`
    - Disable: `reg delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v ShapePackingWorker /f`
    - Status: `reg query HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v ShapePackingWorker`
- **Linux implementation:**
  - Writes/removes `~/.config/autostart/shape-packing-worker.desktop` with `Exec=<exe_path>`.
- **macOS implementation:**
  - Writes/removes `~/Library/LaunchAgents/com.shapepacking.worker.plist`.

- [ ] **Step 3: Run test to verify autostart status check succeeds**

Run: `cargo test --no-default-features --manifest-path packer_rs/Cargo.toml worker::autostart::tests`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add packer_rs/src/worker/autostart.rs packer_rs/src/worker/mod.rs
git commit -m "feat(worker): implement cross-platform autostart management"
```

---

### Task 5: Implement Main Worker Execution Loop & CLI

**Files:**
- Modify: `packer_rs/src/bin/worker.rs`

**Interfaces:**
- Consumes: `clap`, `ctrlc`, `packer_rs::solver`, `worker::{config, client, autostart}`.
- Produces: Fully functional `shape-packing-worker` executable.

- [ ] **Step 1: Implement CLI argument parsing with `clap`**

In `packer_rs/src/bin/worker.rs`:
- Define `Cli` struct with subcommands:
  - Optional `autostart` subcommand with `action: AutostartAction` (`enable`, `disable`, `status`).
  - Flags: `-s, --server`, `-u, --username`, `-c, --cores`, `--config`, `--no-interactive`.

- [ ] **Step 2: Implement background heartbeat thread & signal handling**

- Register `ctrlc::set_handler` setting `RUNNING.store(false, Ordering::SeqCst)`.
- Configure Rayon global thread pool to use allocated cores:
  ```rust
  let _ = rayon::ThreadPoolBuilder::new().num_threads(config.cores).build_global();
  ```
- Before entering the compute loop, spawn or manage a periodic heartbeat thread:
  - Runs every 30 seconds while work is in flight.
  - Sends attempts completed and current best $s$.

- [ ] **Step 3: Implement main solve & submit loop**

- Register with coordinator, obtain/persist `worker_id`.
- Loop while `RUNNING.load(Ordering::SeqCst)`:
  1. Call `client.lease_work(worker_id, cores)`.
  2. If `Some(assignment)`:
     - Print problem banner: `[WORK] Leased {problem} (N={n}, shape={shape}, attempts={attempts})`.
     - Construct `SolveConfig` mapping assignment fields to `packer_rs::solver::SolveConfig`.
     - Call `packer_rs::solver::solve(&solve_config)`.
     - Check results: if `result.best_s < current_best`, print `[RECORD] Found improved metric s={best_s}!`.
     - Submit solution: `client.submit_solution(...)`.
  3. If `None` (no work available):
     - Print `[IDLE] No work available. Retrying in 10s...`.
     - Sleep in 1-second chunks checking `RUNNING`.
  4. On network error:
     - Print warning and backoff exponentially (2s, 4s, 8s, up to 60s).
- On shutdown signal:
  - Print `[SHUTDOWN] Signal received. Deregistering worker...`.
  - Call `client.deregister(worker_id)`.
  - Exit 0.

- [ ] **Step 4: Build release binary and verify `--help` and `--version`**

Run: `cargo run --bin shape-packing-worker --no-default-features --manifest-path packer_rs/Cargo.toml -- --help`  
Expected: Outputs formatted help documentation showing usage and options.

- [ ] **Step 5: Commit**

```bash
git add packer_rs/src/bin/worker.rs
git commit -m "feat(worker): implement standalone crunch loop, heartbeat, and signal handling"
```

---

### Task 6: Implement GitHub Actions Cross-Platform Release CI/CD

**Files:**
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: GitHub Actions runners, git tags matching `v*`.
- Produces: Packaged release assets (`.zip`, `.tar.gz`) and `checksums.sha256` uploaded to GitHub Release.

- [ ] **Step 1: Define multi-platform build matrix in `.github/workflows/release.yml`**

Create `.github/workflows/release.yml`:
- Triggers on:
  ```yaml
  push:
    tags:
      - 'v*'
  workflow_dispatch:
  ```
- Build matrix:
  1. **Windows**: runner `windows-latest`, target `x86_64-pc-windows-msvc`, builds `target/release/shape-packing-worker.exe`, packages into `shape-packing-worker-windows-x86_64.zip`.
  2. **Linux**: runner `ubuntu-latest`, target `x86_64-unknown-linux-gnu`, builds `target/release/shape-packing-worker`, packages into `shape-packing-worker-linux-x86_64.tar.gz`.
  3. **macOS**: runner `macos-latest`, builds `x86_64-apple-darwin` and `aarch64-apple-darwin`, runs `lipo -create -output shape-packing-worker`, packages into `shape-packing-worker-macos-universal.tar.gz`.
- Build command uses `--bin shape-packing-worker --release --no-default-features --manifest-path packer_rs/Cargo.toml`.
- Includes stripped symbols (`strip` command or Cargo release profile).

- [ ] **Step 2: Generate checksums and publish release**

- Compute `sha256sum` on all packaged archives into `checksums.sha256`.
- Use `softprops/action-gh-release@v2` with `files: | ... checksums.sha256`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: add multi-platform release workflow for shape-packing-worker"
```

---

### Task 7: End-to-End Verification & Python Regression Testing

**Files:**
- Verify: Full test suite

**Interfaces:**
- Consumes: Python coordinator and Rust binary.
- Produces: Proof of zero regressions and working native worker.

- [ ] **Step 1: Run complete Rust test suite**

Run: `cargo test --no-default-features --manifest-path packer_rs/Cargo.toml`  
Expected: All unit tests pass.

- [ ] **Step 2: Verify binary compilation and autostart CLI commands**

Run:
```powershell
cargo build --release --bin shape-packing-worker --no-default-features --manifest-path packer_rs/Cargo.toml
target/release/shape-packing-worker.exe --help
target/release/shape-packing-worker.exe autostart status
```
Expected: Help displays correctly; autostart status executes and reports enabled or disabled cleanly.

- [ ] **Step 3: Run complete Python regression test suite**

Run: `py -3.14 -m pytest tests/ -q`  
Expected: 189 passed in ~25 seconds.

- [ ] **Step 4: Commit any final refinements**

```bash
git commit -m "chore: verify pure Rust worker standalone build and full test suite"
```
