use clap::{Parser, Subcommand};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use packer_rs::solver::{self, SolveConfig};
use packer_rs::worker::{autostart, config, CoordinatorClient, WorkAssignment};

static RUNNING: AtomicBool = AtomicBool::new(true);

#[derive(Parser, Debug, Clone, PartialEq, Eq)]
#[command(
    name = "shape-packing-worker",
    version,
    about = "Volunteer crunch worker for distributed shape packing optimization",
    long_about = "A standalone, high-performance volunteer crunch node that leases packing problems from the central coordinator, searches for tighter packings, and submits verified solutions."
)]
pub struct Cli {
    /// Coordinator server URL (e.g. http://localhost:8000)
    #[arg(short = 's', long = "server")]
    pub server: Option<String>,

    /// Contributor username
    #[arg(short = 'u', long = "username")]
    pub username: Option<String>,

    /// Number of worker threads/cores to utilize
    #[arg(short = 'c', long = "cores")]
    pub cores: Option<usize>,

    /// Path to custom worker configuration file
    #[arg(long = "config")]
    pub config: Option<PathBuf>,

    /// Run non-interactively without prompting (use defaults or environment)
    #[arg(long = "no-interactive")]
    pub no_interactive: bool,

    #[command(subcommand)]
    pub command: Option<Commands>,
}

#[derive(Subcommand, Debug, Clone, PartialEq, Eq)]
pub enum Commands {
    /// Manage operating system autostart configuration
    Autostart {
        #[command(subcommand)]
        action: AutostartAction,
    },
}

#[derive(Subcommand, Debug, Clone, PartialEq, Eq)]
pub enum AutostartAction {
    /// Enable worker autostart on system boot
    Enable,
    /// Disable worker autostart on system boot
    Disable,
    /// Show current worker autostart status
    Status,
}

/// Executes the requested autostart action and prints status messages.
pub fn handle_autostart_action(action: &AutostartAction) -> Result<(), String> {
    match action {
        AutostartAction::Enable => {
            autostart::enable_autostart()?;
            println!("[AUTOSTART] Successfully enabled worker autostart.");
            Ok(())
        }
        AutostartAction::Disable => {
            autostart::disable_autostart()?;
            println!("[AUTOSTART] Successfully disabled worker autostart.");
            Ok(())
        }
        AutostartAction::Status => {
            let status = autostart::autostart_status()?;
            println!(
                "[AUTOSTART] Status: {}",
                if status.enabled {
                    "ENABLED"
                } else {
                    "DISABLED"
                }
            );
            if let Some(target) = status.target_path {
                println!("[AUTOSTART] Target path: {}", target);
            }
            Ok(())
        }
    }
}

/// Computes the next exponential backoff interval, capped at 60 seconds.
pub fn next_backoff(current: Duration) -> Duration {
    (current * 2).min(Duration::from_secs(60))
}

/// Maps a coordinator `WorkAssignment` into a solver `SolveConfig`.
pub fn assignment_to_solve_config(assignment: &WorkAssignment) -> SolveConfig {
    SolveConfig {
        inner_polygons: assignment.n,
        inner_shape: assignment.shape.clone(),
        container_shape: assignment.container.clone(),
        attempts: assignment.attempts,
        tolerance: 1e-30,
        finalstep: 0.0001,
        time_limit: Some(assignment.lease_seconds.saturating_sub(15).max(10) as f64),
        initial_positions: assignment.initial_positions.clone(),
        target_s: assignment.target_s,
    }
}

/// Spawns a background thread that periodically sends heartbeats to the coordinator
/// until `stop_flag` is signaled.
pub fn spawn_heartbeat_thread(
    client: CoordinatorClient,
    worker_id: String,
    work_id: String,
    stop_flag: Arc<AtomicBool>,
    interval: Duration,
) -> std::thread::JoinHandle<()> {
    std::thread::spawn(move || {
        let mut last_beat = Instant::now();
        while !stop_flag.load(Ordering::SeqCst) {
            std::thread::sleep(Duration::from_millis(100).min(interval));
            if stop_flag.load(Ordering::SeqCst) {
                break;
            }
            if last_beat.elapsed() >= interval {
                if let Err(e) = client.send_heartbeat(&worker_id, &work_id, 0, None) {
                    eprintln!("[HEARTBEAT WARNING] Failed to ping coordinator: {}", e);
                }
                last_beat = Instant::now();
            }
        }
    })
}

/// Executes one cycle of the worker execution loop:
/// - Attempts to lease a work unit.
/// - If work received, solves it, heartbeats, and submits the verified solution.
/// - If no work available, sleeps for `idle_duration`.
/// - If network error occurs, logs warning, sleeps for `*backoff`, and updates `*backoff`.
pub fn run_worker_cycle_with_durations(
    client: &CoordinatorClient,
    worker_id: &str,
    cores: usize,
    running: &AtomicBool,
    backoff: &mut Duration,
    idle_duration: Duration,
    heartbeat_interval: Duration,
) -> Result<bool, String> {
    if !running.load(Ordering::SeqCst) {
        return Ok(false);
    }

    match client.lease_work(worker_id, cores, 300) {
        Ok(Some(assignment)) => {
            *backoff = Duration::from_secs(2);
            println!(
                "[WORK] Leased {} (N={}, shape={}, attempts={})",
                assignment.problem, assignment.n, assignment.shape, assignment.attempts
            );

            let hb_stop = Arc::new(AtomicBool::new(false));
            let hb_handle = spawn_heartbeat_thread(
                client.clone(),
                worker_id.to_string(),
                assignment.work_id.clone(),
                Arc::clone(&hb_stop),
                heartbeat_interval,
            );

            let solve_config = assignment_to_solve_config(&assignment);
            let result = solver::solve(&solve_config);

            hb_stop.store(true, Ordering::SeqCst);
            let _ = hb_handle.join();

            // Send completion heartbeat so worker compute attempts are credited in coordinator database
            let best_s_opt = if result.success && result.best_s.is_finite() && result.best_s > 0.0 {
                Some(result.best_s)
            } else {
                None
            };
            if let Err(e) = client.send_heartbeat(
                worker_id,
                &assignment.work_id,
                assignment.attempts,
                best_s_opt,
            ) {
                eprintln!(
                    "[HEARTBEAT WARNING] Failed to report completed attempts to coordinator: {}",
                    e
                );
            }

            let is_improvement = match assignment.target_s {
                Some(target) => result.best_s < target,
                None => true,
            };

            if result.success && is_improvement {
                println!("[RECORD] Found improved metric s={:.8}!", result.best_s);
                match client.submit_solution(
                    worker_id,
                    Some(&assignment.work_id),
                    &assignment.problem,
                    result.best_s,
                    &result.values,
                ) {
                    Ok(resp) => {
                        if resp.record_broken {
                            println!(
                                "[RECORD ACCEPTED] Coordinator confirmed new record for {}! (status: {})",
                                assignment.problem, resp.status
                            );
                        } else if resp.verified {
                            println!(
                                "[SOLUTION ACCEPTED] Coordinator verified solution for {}. (status: {})",
                                assignment.problem, resp.status
                            );
                        } else {
                            println!(
                                "[SOLUTION REJECTED] Coordinator response: status={}, message={}",
                                resp.status,
                                resp.message.as_deref().unwrap_or("no details")
                            );
                        }
                    }
                    Err(e) => {
                        eprintln!(
                            "[SUBMIT ERROR] Failed to submit solution for {}: {}",
                            assignment.problem, e
                        );
                    }
                }
            } else if result.success {
                println!(
                    "[WORK] Found packing with s={:.8}, but did not improve current target (target_s={:?}). Skipping submission.",
                    result.best_s, assignment.target_s
                );
            } else {
                println!(
                    "[WORK] No valid packing found for {} in {} attempts.",
                    assignment.problem, assignment.attempts
                );
            }

            Ok(true)
        }
        Ok(None) => {
            *backoff = Duration::from_secs(2);
            println!(
                "[IDLE] No work available. Retrying in {}s...",
                idle_duration.as_secs()
            );
            let sleep_end = Instant::now() + idle_duration;
            while Instant::now() < sleep_end && running.load(Ordering::SeqCst) {
                std::thread::sleep(Duration::from_millis(100).min(idle_duration));
            }
            Ok(false)
        }
        Err(e) => {
            eprintln!(
                "[NETWORK WARNING] Error contacting coordinator: {}. Backing off for {}s...",
                e,
                backoff.as_secs()
            );
            let sleep_end = Instant::now() + *backoff;
            while Instant::now() < sleep_end && running.load(Ordering::SeqCst) {
                std::thread::sleep(Duration::from_millis(100).min(*backoff));
            }
            *backoff = next_backoff(*backoff);
            Err(e)
        }
    }
}

/// Convenience runner with standard idle (10s) and heartbeat (30s) intervals.
pub fn run_worker_cycle(
    client: &CoordinatorClient,
    worker_id: &str,
    cores: usize,
    running: &AtomicBool,
    backoff: &mut Duration,
) -> Result<bool, String> {
    run_worker_cycle_with_durations(
        client,
        worker_id,
        cores,
        running,
        backoff,
        Duration::from_secs(10),
        Duration::from_secs(30),
    )
}

fn main() {
    let cli = Cli::parse();

    // 1. Handle autostart subcommand if present
    if let Some(Commands::Autostart { action }) = cli.command {
        if let Err(e) = handle_autostart_action(&action) {
            eprintln!("[AUTOSTART ERROR] {}", e);
            std::process::exit(1);
        }
        return;
    }

    // 2. Register Ctrl-C signal handler
    if let Err(e) = ctrlc::set_handler(|| {
        RUNNING.store(false, Ordering::SeqCst);
    }) {
        eprintln!("[WARNING] Failed to set Ctrl-C handler: {}", e);
    }

    // 3. Resolve configuration
    let mut config = match config::resolve_interactive_custom(
        cli.server,
        cli.username,
        cli.cores,
        cli.no_interactive,
        cli.config.as_deref(),
    ) {
        Ok(cfg) => cfg,
        Err(e) => {
            eprintln!("[CONFIG ERROR] Failed to resolve worker configuration: {}", e);
            std::process::exit(1);
        }
    };

    // 4. Configure Rayon global thread pool
    if let Err(e) = rayon::ThreadPoolBuilder::new()
        .num_threads(config.cores)
        .build_global()
    {
        eprintln!("[RAYON] Thread pool initialization note: {}", e);
    }

    // 5. Connect and register with coordinator
    let client = CoordinatorClient::new(config.server_url.clone());
    println!(
        "[STARTUP] Registering worker with coordinator at {} (username: {}, cores: {})...",
        config.server_url, config.username, config.cores
    );

    let mut register_backoff = Duration::from_secs(2);
    let worker_id = loop {
        if !RUNNING.load(Ordering::SeqCst) {
            return;
        }
        match client.register(&config.username, config.worker_id.as_deref(), config.cores) {
            Ok(id) => {
                println!("[STARTUP] Registered successfully with worker_id: {}", id);
                break id;
            }
            Err(e) => {
                eprintln!(
                    "[STARTUP WARNING] Failed to register with coordinator: {}. Retrying in {}s...",
                    e,
                    register_backoff.as_secs()
                );
                let sleep_until = Instant::now() + register_backoff;
                while Instant::now() < sleep_until && RUNNING.load(Ordering::SeqCst) {
                    std::thread::sleep(Duration::from_millis(200));
                }
                register_backoff = next_backoff(register_backoff);
            }
        }
    };

    // Persist worker_id if changed or newly assigned
    if config.worker_id.as_deref() != Some(&worker_id) {
        config.worker_id = Some(worker_id.clone());
        if let Err(e) = config::save(cli.config.as_deref(), &config) {
            eprintln!(
                "[CONFIG WARNING] Failed to persist assigned worker_id to config: {}",
                e
            );
        } else {
            println!("[CONFIG] Persisted worker_id to configuration file.");
        }
    }

    // 6. Enter execution loop
    println!(
        "[READY] Worker {} ready. Entering lease-solve crunch loop...",
        worker_id
    );

    let mut backoff = Duration::from_secs(2);
    while RUNNING.load(Ordering::SeqCst) {
        let _ = run_worker_cycle(&client, &worker_id, config.cores, &RUNNING, &mut backoff);
    }

    // 7. Graceful shutdown
    println!("[SHUTDOWN] Signal received. Deregistering worker...");
    if let Err(e) = client.deregister(&worker_id) {
        eprintln!("[SHUTDOWN WARNING] Failed to deregister worker: {}", e);
    } else {
        println!("[SHUTDOWN] Worker successfully deregistered.");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn mock_client<F>(handler: F) -> CoordinatorClient
    where
        F: Fn(&str, &str) -> (u16, &'static str, String) + Send + Sync + 'static,
    {
        let agent = ureq::AgentBuilder::new()
            .middleware(move |req: ureq::Request, _next: ureq::MiddlewareNext| {
                let (status, status_text, body) = handler(req.method(), req.url());
                ureq::Response::new(status, status_text, &body)
            })
            .build();
        CoordinatorClient::with_agent("http://coordinator.test".to_string(), agent)
    }

    #[test]
    fn test_cli_parse_flags_and_options() {
        let cli = Cli::parse_from([
            "shape-packing-worker",
            "-s",
            "http://192.168.1.50:8000",
            "-u",
            "test_user",
            "-c",
            "8",
            "--config",
            "custom_worker.json",
            "--no-interactive",
        ]);

        assert_eq!(cli.server.as_deref(), Some("http://192.168.1.50:8000"));
        assert_eq!(cli.username.as_deref(), Some("test_user"));
        assert_eq!(cli.cores, Some(8));
        assert_eq!(cli.config, Some(PathBuf::from("custom_worker.json")));
        assert!(cli.no_interactive);
        assert!(cli.command.is_none());
    }

    #[test]
    fn test_cli_parse_subcommand_autostart_enable() {
        let cli = Cli::parse_from(["shape-packing-worker", "autostart", "enable"]);
        assert_eq!(
            cli.command,
            Some(Commands::Autostart {
                action: AutostartAction::Enable
            })
        );
    }

    #[test]
    fn test_cli_parse_subcommand_autostart_disable() {
        let cli = Cli::parse_from(["shape-packing-worker", "autostart", "disable"]);
        assert_eq!(
            cli.command,
            Some(Commands::Autostart {
                action: AutostartAction::Disable
            })
        );
    }

    #[test]
    fn test_cli_parse_subcommand_autostart_status() {
        let cli = Cli::parse_from(["shape-packing-worker", "autostart", "status"]);
        assert_eq!(
            cli.command,
            Some(Commands::Autostart {
                action: AutostartAction::Status
            })
        );
    }

    #[test]
    fn test_assignment_to_solve_config_mapping() {
        let assignment = WorkAssignment {
            work_id: "work-123".to_string(),
            problem: "squincir_5_3_in_CIRCLE".to_string(),
            shape: "3".to_string(),
            n: 5,
            container: "CIRCLE".to_string(),
            attempts: 500,
            target_s: Some(0.85),
            lease_seconds: 300,
            initial_positions: Some(vec![0.1, 0.2, 0.3]),
        };

        let solve_cfg = assignment_to_solve_config(&assignment);
        assert_eq!(solve_cfg.inner_polygons, 5);
        assert_eq!(solve_cfg.inner_shape, "3");
        assert_eq!(solve_cfg.container_shape, "CIRCLE");
        assert_eq!(solve_cfg.attempts, 500);
        assert_eq!(solve_cfg.target_s, Some(0.85));
        assert_eq!(solve_cfg.initial_positions, Some(vec![0.1, 0.2, 0.3]));
        assert_eq!(solve_cfg.tolerance, 1e-30);
        assert_eq!(solve_cfg.finalstep, 0.0001);
        assert_eq!(solve_cfg.time_limit, Some(285.0));
    }

    #[test]
    fn test_next_backoff_exponential() {
        let b1 = Duration::from_secs(2);
        let b2 = next_backoff(b1);
        assert_eq!(b2, Duration::from_secs(4));

        let b3 = next_backoff(b2);
        assert_eq!(b3, Duration::from_secs(8));

        let b4 = next_backoff(Duration::from_secs(32));
        assert_eq!(b4, Duration::from_secs(60));

        let b5 = next_backoff(Duration::from_secs(60));
        assert_eq!(b5, Duration::from_secs(60));
    }

    #[test]
    fn test_spawn_heartbeat_thread_lifecycle() {
        let heartbeats_received = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let hb_counter = Arc::clone(&heartbeats_received);

        let client = mock_client(move |method, url| {
            assert_eq!(method, "POST");
            assert!(url.contains("/heartbeat"));
            hb_counter.fetch_add(1, Ordering::SeqCst);
            (200, "OK", r#"{"status":"heartbeat_ack"}"#.to_string())
        });

        let stop_flag = Arc::new(AtomicBool::new(false));
        let handle = spawn_heartbeat_thread(
            client,
            "worker-hb-test".to_string(),
            "work-hb-test".to_string(),
            Arc::clone(&stop_flag),
            Duration::from_millis(50),
        );

        // Sleep to let at least one heartbeat tick fire
        std::thread::sleep(Duration::from_millis(150));
        stop_flag.store(true, Ordering::SeqCst);
        let _ = handle.join();

        assert!(
            heartbeats_received.load(Ordering::SeqCst) >= 1,
            "Heartbeat thread should have executed at least one ping"
        );
    }

    #[test]
    fn test_run_worker_cycle_idle_204() {
        let client = mock_client(|method, url| {
            assert_eq!(method, "GET");
            assert!(url.starts_with("http://coordinator.test/api/v1/work"));
            (204, "No Content", String::new())
        });

        let running = AtomicBool::new(true);
        let mut backoff = Duration::from_secs(16);

        let result = run_worker_cycle_with_durations(
            &client,
            "wid-1",
            2,
            &running,
            &mut backoff,
            Duration::from_millis(20),
            Duration::from_secs(30),
        );

        assert_eq!(result, Ok(false));
        // Backoff resets on successful 204
        assert_eq!(backoff, Duration::from_secs(2));
    }

    #[test]
    fn test_run_worker_cycle_network_error_backoff() {
        let client = mock_client(|_, _| {
            (500, "Internal Server Error", r#"{"error":"DB offline"}"#.to_string())
        });

        let running = AtomicBool::new(true);
        let mut backoff = Duration::from_secs(4);

        let result = run_worker_cycle_with_durations(
            &client,
            "wid-err",
            2,
            &running,
            &mut backoff,
            Duration::from_millis(20),
            Duration::from_secs(30),
        );

        assert!(result.is_err());
        // Backoff doubles on network error
        assert_eq!(backoff, Duration::from_secs(8));
    }

    #[test]
    fn test_run_worker_cycle_lease_solve_and_submit() {
        let submit_called = Arc::new(AtomicBool::new(false));
        let submit_called_clone = Arc::clone(&submit_called);
        let completion_heartbeat_called = Arc::new(AtomicBool::new(false));
        let completion_heartbeat_clone = Arc::clone(&completion_heartbeat_called);

        let client = mock_client(move |method, url| {
            if method == "GET" && url.contains("/api/v1/work") {
                (
                    200,
                    "OK",
                    r#"{
                        "work_id": "test-work-99",
                        "problem": "squincir_1_4_in_CIRCLE",
                        "inner_token": "4",
                        "container_token": "CIRCLE",
                        "n": 1,
                        "target_s": 5.0,
                        "recommended_attempts": 2,
                        "timeout_seconds": 300
                    }"#
                    .to_string(),
                )
            } else if method == "POST" && url.contains("/api/v1/solutions") {
                submit_called_clone.store(true, Ordering::SeqCst);
                (
                    200,
                    "OK",
                    r#"{
                        "status": "accepted",
                        "verified": true,
                        "is_new_record": true,
                        "message": "New record registered"
                    }"#
                    .to_string(),
                )
            } else if method == "POST" && url.contains("/heartbeat") {
                completion_heartbeat_clone.store(true, Ordering::SeqCst);
                (200, "OK", r#"{"status":"ack"}"#.to_string())
            } else {
                (404, "Not Found", String::new())
            }
        });

        let running = AtomicBool::new(true);
        let mut backoff = Duration::from_secs(8);

        let result = run_worker_cycle_with_durations(
            &client,
            "wid-solve-test",
            1,
            &running,
            &mut backoff,
            Duration::from_millis(10),
            Duration::from_secs(30),
        );

        assert_eq!(result, Ok(true));
        assert_eq!(backoff, Duration::from_secs(2));
        assert!(
            completion_heartbeat_called.load(Ordering::SeqCst),
            "Expected completion heartbeat to credit compute attempts"
        );
        assert!(
            submit_called.load(Ordering::SeqCst),
            "Expected solution submission to coordinator for improving result"
        );
    }

    #[test]
    fn test_run_worker_cycle_non_improving_solution_not_submitted() {
        let submit_called = Arc::new(AtomicBool::new(false));
        let submit_called_clone = Arc::clone(&submit_called);
        let completion_heartbeat_called = Arc::new(AtomicBool::new(false));
        let completion_heartbeat_clone = Arc::clone(&completion_heartbeat_called);

        let client = mock_client(move |method, url| {
            if method == "GET" && url.contains("/api/v1/work") {
                (
                    200,
                    "OK",
                    r#"{
                        "work_id": "test-work-100",
                        "problem": "squincir_1_4_in_CIRCLE",
                        "inner_token": "4",
                        "container_token": "CIRCLE",
                        "n": 1,
                        "target_s": 0.00001,
                        "recommended_attempts": 2,
                        "timeout_seconds": 300
                    }"#
                    .to_string(),
                )
            } else if method == "POST" && url.contains("/api/v1/solutions") {
                submit_called_clone.store(true, Ordering::SeqCst);
                (200, "OK", r#"{"status":"accepted"}"#.to_string())
            } else if method == "POST" && url.contains("/heartbeat") {
                completion_heartbeat_clone.store(true, Ordering::SeqCst);
                (200, "OK", r#"{"status":"ack"}"#.to_string())
            } else {
                (404, "Not Found", String::new())
            }
        });

        let running = AtomicBool::new(true);
        let mut backoff = Duration::from_secs(2);

        let result = run_worker_cycle_with_durations(
            &client,
            "wid-solve-non-improving",
            1,
            &running,
            &mut backoff,
            Duration::from_millis(10),
            Duration::from_secs(30),
        );

        assert_eq!(result, Ok(true));
        assert!(
            completion_heartbeat_called.load(Ordering::SeqCst),
            "Expected completion heartbeat to credit attempts even when not improving"
        );
        assert!(
            !submit_called.load(Ordering::SeqCst),
            "Non-improving solution must NOT be submitted for SAT verification"
        );
    }

    #[test]
    fn test_worker_graceful_shutdown_on_stop_flag() {
        let client = mock_client(|_, _| (200, "OK", String::new()));

        let running = AtomicBool::new(false);
        let mut backoff = Duration::from_secs(2);

        let result = run_worker_cycle_with_durations(
            &client,
            "wid-stopped",
            1,
            &running,
            &mut backoff,
            Duration::from_millis(10),
            Duration::from_secs(30),
        );

        assert_eq!(result, Ok(false));
    }
}
