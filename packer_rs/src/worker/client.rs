//! HTTP client for communicating with the distributed shape-packing coordinator.

use std::time::Duration;

fn default_container() -> String {
    "CIRCLE".to_string()
}

fn default_attempts() -> usize {
    1000
}

fn default_lease_seconds() -> u64 {
    300
}

/// Work assignment received from the coordinator scheduler.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
#[serde(from = "RawWorkAssignment")]
pub struct WorkAssignment {
    pub work_id: String,
    pub problem: String,
    pub shape: String,
    pub n: usize,
    pub container: String,
    pub attempts: usize,
    pub target_s: Option<f64>,
    pub lease_seconds: u64,
    pub initial_positions: Option<Vec<f64>>,
}

#[derive(serde::Deserialize)]
struct RawWorkAssignment {
    work_id: String,
    problem: String,
    #[serde(default)]
    shape: Option<String>,
    #[serde(default)]
    inner_token: Option<String>,
    n: usize,
    #[serde(default)]
    container: Option<String>,
    #[serde(default)]
    container_token: Option<String>,
    #[serde(default)]
    attempts: Option<usize>,
    #[serde(default)]
    recommended_attempts: Option<usize>,
    #[serde(default)]
    target_s: Option<f64>,
    #[serde(default)]
    lease_seconds: Option<u64>,
    #[serde(default)]
    timeout_seconds: Option<u64>,
    #[serde(default)]
    initial_positions: Option<Vec<f64>>,
}

impl From<RawWorkAssignment> for WorkAssignment {
    fn from(raw: RawWorkAssignment) -> Self {
        WorkAssignment {
            work_id: raw.work_id,
            problem: raw.problem,
            shape: raw
                .shape
                .or(raw.inner_token)
                .unwrap_or_else(|| "3".to_string()),
            n: raw.n,
            container: raw
                .container
                .or(raw.container_token)
                .unwrap_or_else(default_container),
            attempts: raw
                .attempts
                .or(raw.recommended_attempts)
                .unwrap_or_else(default_attempts),
            target_s: raw.target_s,
            lease_seconds: raw
                .lease_seconds
                .or(raw.timeout_seconds)
                .unwrap_or_else(default_lease_seconds),
            initial_positions: raw.initial_positions,
        }
    }
}

/// Verification and record status response from the coordinator.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct SolutionResponse {
    pub status: String,
    #[serde(default)]
    pub verified: bool,
    #[serde(default, alias = "is_new_record")]
    pub record_broken: bool,
    pub message: Option<String>,
}

#[derive(serde::Serialize)]
struct RegisterRequest<'a> {
    username: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    worker_id: Option<&'a str>,
    client_type: &'a str,
    cores: usize,
}

#[derive(serde::Deserialize)]
struct RegisterResponse {
    worker_id: String,
}

#[derive(serde::Serialize)]
struct HeartbeatRequest<'a> {
    worker_id: &'a str,
    work_id: &'a str,
    attempts_completed: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    best_local_s: Option<f64>,
}

#[derive(serde::Serialize)]
struct SolutionSubmitRequest<'a> {
    #[serde(skip_serializing_if = "Option::is_none")]
    work_id: Option<&'a str>,
    worker_id: &'a str,
    problem: &'a str,
    s: f64,
    coordinates: &'a [f64],
}

#[derive(serde::Serialize)]
struct DeregisterRequest<'a> {
    worker_id: &'a str,
}

/// RFC 3986 percent-encoding for query string parameter values.
fn url_encode(input: &str) -> String {
    let mut encoded = String::with_capacity(input.len());
    for b in input.bytes() {
        match b {
            b'a'..=b'z' | b'A'..=b'Z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                encoded.push(b as char);
            }
            _ => {
                encoded.push_str(&format!("%{:02X}", b));
            }
        }
    }
    encoded
}

/// Synchronous HTTP client for the coordinator REST API.
#[derive(Clone, Debug)]
pub struct CoordinatorClient {
    server_url: String,
    agent: ureq::Agent,
}

impl CoordinatorClient {
    /// Create a new coordinator HTTP client with normalized server URL.
    pub fn new(server_url: String) -> Self {
        let server_url = server_url.trim_end_matches('/').to_string();
        let agent = ureq::AgentBuilder::new()
            .timeout_connect(Duration::from_secs(5))
            .timeout_read(Duration::from_secs(15))
            .timeout_write(Duration::from_secs(10))
            .build();
        Self { server_url, agent }
    }

    /// Create a client with a custom `ureq::Agent` (useful for testing or custom timeouts).
    pub fn with_agent(server_url: String, agent: ureq::Agent) -> Self {
        let server_url = server_url.trim_end_matches('/').to_string();
        Self { server_url, agent }
    }

    /// Base URL of the coordinator server without trailing slashes.
    pub fn server_url(&self) -> &str {
        &self.server_url
    }

    /// Register worker node with coordinator and return the assigned `worker_id`.
    ///
    /// Calls `POST /api/v1/workers/register`.
    pub fn register(
        &self,
        username: &str,
        worker_id: Option<&str>,
        cores: usize,
    ) -> Result<String, String> {
        let url = format!("{}/api/v1/workers/register", self.server_url);
        let payload = RegisterRequest {
            username,
            worker_id,
            client_type: "native",
            cores,
        };

        match self.agent.post(&url).send_json(&payload) {
            Ok(resp) => {
                let parsed: RegisterResponse = resp
                    .into_json()
                    .map_err(|e| format!("Failed to parse register response JSON: {}", e))?;
                Ok(parsed.worker_id)
            }
            Err(ureq::Error::Status(code, resp)) => {
                let body = resp.into_string().unwrap_or_default();
                Err(format!(
                    "Coordinator registration failed (HTTP {}): {}",
                    code, body
                ))
            }
            Err(ureq::Error::Transport(e)) => {
                Err(format!("Network error during registration: {}", e))
            }
        }
    }

    /// Lease a work unit from the coordinator scheduler.
    ///
    /// Calls `GET /api/v1/work?worker_id={}&cores={}&lease_seconds={}`.
    /// Returns `Ok(None)` when the coordinator returns HTTP 204 No Content.
    pub fn lease_work(
        &self,
        worker_id: &str,
        cores: usize,
        lease_seconds: u64,
    ) -> Result<Option<WorkAssignment>, String> {
        let url = format!(
            "{}/api/v1/work?worker_id={}&cores={}&lease_seconds={}",
            self.server_url,
            url_encode(worker_id),
            cores,
            lease_seconds
        );

        match self.agent.get(&url).call() {
            Ok(resp) => {
                if resp.status() == 204 {
                    Ok(None)
                } else {
                    let assignment: WorkAssignment = resp
                        .into_json()
                        .map_err(|e| format!("Failed to parse work assignment JSON: {}", e))?;
                    Ok(Some(assignment))
                }
            }
            Err(ureq::Error::Status(204, _)) => Ok(None),
            Err(ureq::Error::Status(code, resp)) => {
                let body = resp.into_string().unwrap_or_default();
                Err(format!(
                    "Coordinator lease_work failed (HTTP {}): {}",
                    code, body
                ))
            }
            Err(ureq::Error::Transport(e)) => Err(format!("Network error leasing work: {}", e)),
        }
    }

    /// Convenience wrapper for leasing work with default lease duration of 300 seconds.
    pub fn lease_work_simple(
        &self,
        worker_id: &str,
        cores: usize,
    ) -> Result<Option<WorkAssignment>, String> {
        self.lease_work(worker_id, cores, 300)
    }

    /// Send progress heartbeat for an active lease.
    ///
    /// Calls `POST /api/v1/work/heartbeat`, falling back to `POST /api/v1/heartbeat`
    /// if the former returns HTTP 404 Not Found.
    pub fn send_heartbeat(
        &self,
        worker_id: &str,
        work_id: &str,
        attempts_completed: usize,
        best_local_s: Option<f64>,
    ) -> Result<(), String> {
        let payload = HeartbeatRequest {
            worker_id,
            work_id,
            attempts_completed,
            best_local_s,
        };

        let url_primary = format!("{}/api/v1/work/heartbeat", self.server_url);
        let res = self.agent.post(&url_primary).send_json(&payload);

        match res {
            Ok(_) => Ok(()),
            Err(ureq::Error::Status(404, _)) => {
                let url_fallback = format!("{}/api/v1/heartbeat", self.server_url);
                match self.agent.post(&url_fallback).send_json(&payload) {
                    Ok(_) => Ok(()),
                    Err(ureq::Error::Status(code, resp)) => {
                        let body = resp.into_string().unwrap_or_default();
                        Err(format!(
                            "Coordinator heartbeat failed (HTTP {}): {}",
                            code, body
                        ))
                    }
                    Err(ureq::Error::Transport(e)) => {
                        Err(format!("Network error sending heartbeat: {}", e))
                    }
                }
            }
            Err(ureq::Error::Status(code, resp)) => {
                let body = resp.into_string().unwrap_or_default();
                Err(format!(
                    "Coordinator heartbeat failed (HTTP {}): {}",
                    code, body
                ))
            }
            Err(ureq::Error::Transport(e)) => {
                Err(format!("Network error sending heartbeat: {}", e))
            }
        }
    }

    /// Submit a computed geometric solution to the coordinator for SAT verification and recording.
    ///
    /// Calls `POST /api/v1/solutions`. Returns `Ok(SolutionResponse)` on HTTP 200 or HTTP 400
    /// (with rejection details parsed from the body).
    pub fn submit_solution(
        &self,
        worker_id: &str,
        work_id: Option<&str>,
        problem: &str,
        s: f64,
        coordinates: &[f64],
    ) -> Result<SolutionResponse, String> {
        let url = format!("{}/api/v1/solutions", self.server_url);
        let payload = SolutionSubmitRequest {
            work_id,
            worker_id,
            problem,
            s,
            coordinates,
        };

        match self.agent.post(&url).send_json(&payload) {
            Ok(resp) => {
                let sol_resp: SolutionResponse = resp
                    .into_json()
                    .map_err(|e| format!("Failed to parse solution response JSON: {}", e))?;
                Ok(sol_resp)
            }
            Err(ureq::Error::Status(code, resp)) => {
                if let Ok(sol_resp) = resp.into_json::<SolutionResponse>() {
                    Ok(sol_resp)
                } else {
                    Err(format!(
                        "Coordinator rejected solution (HTTP {}): unexpected response body",
                        code
                    ))
                }
            }
            Err(ureq::Error::Transport(e)) => {
                Err(format!("Network error submitting solution: {}", e))
            }
        }
    }

    /// Notify coordinator on graceful exit to release active leases and mark worker offline.
    ///
    /// Calls `POST /api/v1/workers/deregister`.
    pub fn deregister(&self, worker_id: &str) -> Result<(), String> {
        let url = format!("{}/api/v1/workers/deregister", self.server_url);
        let payload = DeregisterRequest { worker_id };

        match self.agent.post(&url).send_json(&payload) {
            Ok(_) => Ok(()),
            Err(ureq::Error::Status(code, resp)) => {
                let body = resp.into_string().unwrap_or_default();
                Err(format!(
                    "Coordinator deregistration failed (HTTP {}): {}",
                    code, body
                ))
            }
            Err(ureq::Error::Transport(e)) => {
                Err(format!("Network error during deregistration: {}", e))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;

    #[test]
    fn test_work_assignment_deserialization_standard() {
        let json_data = r#"{
            "work_id": "work-abc-123",
            "problem": "squinoct_38_4_in_8",
            "shape": "4",
            "n": 38,
            "container": "8",
            "attempts": 5000,
            "target_s": 0.825,
            "lease_seconds": 600,
            "initial_positions": [0.1, 0.2, 0.3]
        }"#;

        let assignment: WorkAssignment = serde_json::from_str(json_data).unwrap();
        assert_eq!(assignment.work_id, "work-abc-123");
        assert_eq!(assignment.problem, "squinoct_38_4_in_8");
        assert_eq!(assignment.shape, "4");
        assert_eq!(assignment.n, 38);
        assert_eq!(assignment.container, "8");
        assert_eq!(assignment.attempts, 5000);
        assert_eq!(assignment.target_s, Some(0.825));
        assert_eq!(assignment.lease_seconds, 600);
        assert_eq!(assignment.initial_positions, Some(vec![0.1, 0.2, 0.3]));
    }

    #[test]
    fn test_work_assignment_deserialization_coordinator_aliases() {
        // Coordinator returns inner_token, container_token, recommended_attempts, timeout_seconds
        let json_data = r#"{
            "work_id": "lease-uuid-999",
            "problem": "triindom_22_3_in_DOMINO",
            "inner_token": "3",
            "container_token": "DOMINO",
            "n": 22,
            "target_s": 1.234,
            "recommended_attempts": 2000,
            "timeout_seconds": 300
        }"#;

        let assignment: WorkAssignment = serde_json::from_str(json_data).unwrap();
        assert_eq!(assignment.work_id, "lease-uuid-999");
        assert_eq!(assignment.problem, "triindom_22_3_in_DOMINO");
        assert_eq!(assignment.shape, "3");
        assert_eq!(assignment.n, 22);
        assert_eq!(assignment.container, "DOMINO");
        assert_eq!(assignment.attempts, 2000);
        assert_eq!(assignment.target_s, Some(1.234));
        assert_eq!(assignment.lease_seconds, 300);
        assert_eq!(assignment.initial_positions, None);
    }

    #[test]
    fn test_work_assignment_deserialization_both_lease_and_timeout_seconds() {
        // Live coordinator app.py returns both lease_seconds AND timeout_seconds
        let json_data = r#"{
            "work_id": "lease-both-123",
            "problem": "3_3_in_circle",
            "inner_token": "3",
            "container_token": "CIRCLE",
            "n": 3,
            "target_s": 3.5,
            "recommended_attempts": 2000,
            "lease_seconds": 300,
            "timeout_seconds": 300
        }"#;

        let assignment: WorkAssignment = serde_json::from_str(json_data).unwrap();
        assert_eq!(assignment.work_id, "lease-both-123");
        assert_eq!(assignment.problem, "3_3_in_circle");
        assert_eq!(assignment.shape, "3");
        assert_eq!(assignment.n, 3);
        assert_eq!(assignment.container, "CIRCLE");
        assert_eq!(assignment.attempts, 2000);
        assert_eq!(assignment.target_s, Some(3.5));
        assert_eq!(assignment.lease_seconds, 300);
    }

    #[test]
    fn test_work_assignment_defaults() {
        let json_data = r#"{
            "work_id": "minimal-001",
            "problem": "prob-1",
            "shape": "5",
            "n": 10
        }"#;

        let assignment: WorkAssignment = serde_json::from_str(json_data).unwrap();
        assert_eq!(assignment.work_id, "minimal-001");
        assert_eq!(assignment.problem, "prob-1");
        assert_eq!(assignment.shape, "5");
        assert_eq!(assignment.n, 10);
        assert_eq!(assignment.container, "CIRCLE");
        assert_eq!(assignment.attempts, 1000);
        assert_eq!(assignment.lease_seconds, 300);
        assert_eq!(assignment.target_s, None);
        assert_eq!(assignment.initial_positions, None);
    }

    #[test]
    fn test_solution_response_accepted_record() {
        let json_data = r#"{
            "status": "accepted",
            "verified": true,
            "is_new_record": true,
            "message": "New world record registered! Rank updated."
        }"#;

        let resp: SolutionResponse = serde_json::from_str(json_data).unwrap();
        assert_eq!(resp.status, "accepted");
        assert!(resp.verified);
        assert!(resp.record_broken);
        assert_eq!(
            resp.message.as_deref(),
            Some("New world record registered! Rank updated.")
        );
    }

    #[test]
    fn test_solution_response_duplicate() {
        let json_data = r#"{
            "status": "duplicate",
            "verified": true,
            "record_broken": false,
            "message": "Valid packing, but not lower than current best"
        }"#;

        let resp: SolutionResponse = serde_json::from_str(json_data).unwrap();
        assert_eq!(resp.status, "duplicate");
        assert!(resp.verified);
        assert!(!resp.record_broken);
        assert_eq!(
            resp.message.as_deref(),
            Some("Valid packing, but not lower than current best")
        );
    }

    #[test]
    fn test_solution_response_rejected() {
        let json_data = r#"{
            "status": "rejected",
            "verified": false,
            "message": "Geometric verification failed: Polygon overlap detected"
        }"#;

        let resp: SolutionResponse = serde_json::from_str(json_data).unwrap();
        assert_eq!(resp.status, "rejected");
        assert!(!resp.verified);
        assert!(!resp.record_broken);
        assert_eq!(
            resp.message.as_deref(),
            Some("Geometric verification failed: Polygon overlap detected")
        );
    }

    #[test]
    fn test_server_url_normalization() {
        let c1 = CoordinatorClient::new("http://localhost:8000/".to_string());
        assert_eq!(c1.server_url(), "http://localhost:8000");

        let c2 = CoordinatorClient::new("http://localhost:8000///".to_string());
        assert_eq!(c2.server_url(), "http://localhost:8000");

        let c3 = CoordinatorClient::new("http://localhost:8000".to_string());
        assert_eq!(c3.server_url(), "http://localhost:8000");
    }

    #[test]
    fn test_url_encode() {
        assert_eq!(url_encode("hello_world-123.~"), "hello_world-123.~");
        assert_eq!(url_encode("uuid:123/456"), "uuid%3A123%2F456");
        assert_eq!(url_encode("a b+c"), "a%20b%2Bc");
    }

    /// Creates a `CoordinatorClient` backed by an in-memory mock middleware.
    /// This enables fast, deterministic HTTP client testing without network sockets.
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
    fn test_client_register_success() {
        let client = mock_client(|method, url| {
            assert_eq!(method, "POST");
            assert_eq!(url, "http://coordinator.test/api/v1/workers/register");
            (
                200,
                "OK",
                r#"{"worker_id":"assigned-worker-123","status":"registered"}"#.to_string(),
            )
        });

        let wid = client.register("alice", None, 4).unwrap();
        assert_eq!(wid, "assigned-worker-123");
    }

    #[test]
    fn test_client_register_error() {
        let client = mock_client(|_method, _url| {
            (
                400,
                "Bad Request",
                r#"{"detail":"Username cannot be empty"}"#.to_string(),
            )
        });

        let err = client.register("", None, 4).unwrap_err();
        assert!(err.contains("HTTP 400"));
        assert!(err.contains("Username cannot be empty"));
    }

    #[test]
    fn test_client_lease_work_available() {
        let client = mock_client(|method, url| {
            assert_eq!(method, "GET");
            assert!(url.starts_with("http://coordinator.test/api/v1/work?"));
            assert!(url.contains("worker_id=wid-42"));
            assert!(url.contains("cores=2"));
            assert!(url.contains("lease_seconds=300"));
            (
                200,
                "OK",
                r#"{
                    "work_id": "wid-lease-1",
                    "problem": "squinoct_10_4_in_8",
                    "inner_token": "4",
                    "container_token": "8",
                    "n": 10,
                    "target_s": 0.95,
                    "recommended_attempts": 1500,
                    "timeout_seconds": 300
                }"#
                .to_string(),
            )
        });

        let opt_work = client.lease_work("wid-42", 2, 300).unwrap();
        assert!(opt_work.is_some());
        let work = opt_work.unwrap();
        assert_eq!(work.work_id, "wid-lease-1");
        assert_eq!(work.problem, "squinoct_10_4_in_8");
        assert_eq!(work.shape, "4");
        assert_eq!(work.container, "8");
        assert_eq!(work.attempts, 1500);
    }

    #[test]
    fn test_client_lease_work_204_no_content() {
        let client = mock_client(|method, url| {
            assert_eq!(method, "GET");
            assert!(url.starts_with("http://coordinator.test/api/v1/work?"));
            (204, "No Content", "".to_string())
        });

        let opt_work = client.lease_work_simple("wid-empty", 1).unwrap();
        assert!(opt_work.is_none());
    }

    #[test]
    fn test_client_send_heartbeat_primary_success() {
        let client = mock_client(|method, url| {
            assert_eq!(method, "POST");
            assert_eq!(url, "http://coordinator.test/api/v1/work/heartbeat");
            (200, "OK", r#"{"status":"recorded"}"#.to_string())
        });

        let res = client.send_heartbeat("wid-1", "work-1", 500, Some(0.812));
        assert!(res.is_ok());
    }

    #[test]
    fn test_client_send_heartbeat_fallback_on_404() {
        let attempts = Arc::new(AtomicUsize::new(0));
        let attempts_clone = attempts.clone();

        let client = mock_client(move |method, url| {
            assert_eq!(method, "POST");
            let req_num = attempts_clone.fetch_add(1, Ordering::SeqCst);
            if req_num == 0 {
                assert_eq!(url, "http://coordinator.test/api/v1/work/heartbeat");
                (404, "Not Found", "Not Found".to_string())
            } else {
                assert_eq!(url, "http://coordinator.test/api/v1/heartbeat");
                (200, "OK", r#"{"status":"recorded"}"#.to_string())
            }
        });

        let res = client.send_heartbeat("wid-2", "work-2", 1000, None);
        assert!(res.is_ok());
        assert_eq!(attempts.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn test_client_submit_solution_accepted() {
        let client = mock_client(|method, url| {
            assert_eq!(method, "POST");
            assert_eq!(url, "http://coordinator.test/api/v1/solutions");
            (
                200,
                "OK",
                r#"{
                    "status": "accepted",
                    "verified": true,
                    "is_new_record": true,
                    "message": "New record!"
                }"#
                .to_string(),
            )
        });

        let resp = client
            .submit_solution("wid-submit", Some("work-9"), "prob-9", 0.75, &[0.1, 0.2, 0.3])
            .unwrap();
        assert_eq!(resp.status, "accepted");
        assert!(resp.verified);
        assert!(resp.record_broken);
        assert_eq!(resp.message.as_deref(), Some("New record!"));
    }

    #[test]
    fn test_client_submit_solution_rejected_400() {
        let client = mock_client(|method, url| {
            assert_eq!(method, "POST");
            assert_eq!(url, "http://coordinator.test/api/v1/solutions");
            (
                400,
                "Bad Request",
                r#"{
                    "status": "rejected",
                    "verified": false,
                    "message": "Geometric verification failed: Overlap detected"
                }"#
                .to_string(),
            )
        });

        let resp = client
            .submit_solution("wid-submit", None, "prob-9", 0.75, &[0.1, 0.2, 0.3])
            .unwrap();
        assert_eq!(resp.status, "rejected");
        assert!(!resp.verified);
        assert!(!resp.record_broken);
        assert!(resp
            .message
            .as_deref()
            .unwrap()
            .contains("Overlap detected"));
    }

    #[test]
    fn test_client_deregister_success() {
        let client = mock_client(|method, url| {
            assert_eq!(method, "POST");
            assert_eq!(url, "http://coordinator.test/api/v1/workers/deregister");
            (200, "OK", r#"{"status":"deregistered"}"#.to_string())
        });

        let res = client.deregister("wid-leaving");
        assert!(res.is_ok());
    }

    #[test]
    fn test_client_network_error() {
        let agent = ureq::AgentBuilder::new()
            .timeout_connect(Duration::from_millis(100))
            .build();
        // Point to an address where nothing is listening
        let client =
            CoordinatorClient::with_agent("http://127.0.0.1:54321".to_string(), agent);
        let res = client.register("test", None, 1);
        assert!(res.is_err());
        let err = res.unwrap_err();
        assert!(err.contains("Network error"));
    }
}
