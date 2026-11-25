use serde::{Deserialize, Serialize};
use std::io::{BufRead, Write};
use std::path::{Path, PathBuf};

fn default_server_url() -> String {
    "https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net".to_string()
}

fn default_username() -> String {
    "anonymous".to_string()
}

fn default_cores() -> usize {
    1
}

/// Configuration parameters for distributed worker daemon.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WorkerConfig {
    #[serde(default = "default_server_url")]
    pub server_url: String,

    #[serde(default = "default_username")]
    pub username: String,

    #[serde(default)]
    pub worker_id: Option<String>,

    #[serde(default = "default_cores")]
    pub cores: usize,
}

impl Default for WorkerConfig {
    fn default() -> Self {
        Self {
            server_url: default_server_url(),
            username: default_username(),
            worker_id: None,
            cores: default_cores(),
        }
    }
}

/// Resolves user home directory using USERPROFILE on Windows and HOME on Unix.
pub fn home_dir() -> PathBuf {
    #[cfg(windows)]
    {
        if let Some(userprofile) = std::env::var_os("USERPROFILE") {
            return PathBuf::from(userprofile);
        }
        if let Some(home) = std::env::var_os("HOME") {
            return PathBuf::from(home);
        }
    }
    #[cfg(not(windows))]
    {
        if let Some(home) = std::env::var_os("HOME") {
            return PathBuf::from(home);
        }
        if let Some(userprofile) = std::env::var_os("USERPROFILE") {
            return PathBuf::from(userprofile);
        }
    }
    PathBuf::from(".")
}

/// Returns default configuration file path `~/.shape_packing_worker.json`.
pub fn default_config_path() -> PathBuf {
    home_dir().join(".shape_packing_worker.json")
}

/// Detects default system username or fallback.
pub fn default_system_username() -> String {
    std::env::var("USER")
        .or_else(|_| std::env::var("USERNAME"))
        .unwrap_or_else(|_| default_username())
}

/// Detects available system CPU cores (minimum 1).
pub fn detected_cores() -> usize {
    std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(1)
        .max(1)
}

/// Loads `WorkerConfig` from disk at specified path or default path.
pub fn load(path: Option<&Path>) -> Result<WorkerConfig, String> {
    let p = path.map(|p| p.to_path_buf()).unwrap_or_else(default_config_path);
    if !p.exists() {
        return Err(format!("Configuration file does not exist: {}", p.display()));
    }
    let content = std::fs::read_to_string(&p)
        .map_err(|e| format!("Failed to read configuration file {}: {}", p.display(), e))?;
    let mut config: WorkerConfig = serde_json::from_str(&content)
        .map_err(|e| format!("Failed to parse configuration file {}: {}", p.display(), e))?;
    if config.cores == 0 {
        config.cores = 1;
    }
    Ok(config)
}

/// Saves `WorkerConfig` to disk. If the file exists, preserves extra fields from desktop GUI.
pub fn save(path: Option<&Path>, config: &WorkerConfig) -> Result<(), String> {
    let p = path.map(|p| p.to_path_buf()).unwrap_or_else(default_config_path);
    if let Some(parent) = p.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("Failed to create directory {}: {}", parent.display(), e))?;
        }
    }

    let mut root_val = if p.exists() {
        let content = std::fs::read_to_string(&p).unwrap_or_default();
        serde_json::from_str::<serde_json::Value>(&content).unwrap_or_else(|_| serde_json::json!({}))
    } else {
        serde_json::json!({})
    };

    if !root_val.is_object() {
        root_val = serde_json::json!({});
    }

    if let serde_json::Value::Object(ref mut map) = root_val {
        map.insert(
            "server_url".to_string(),
            serde_json::Value::String(config.server_url.clone()),
        );
        map.insert(
            "username".to_string(),
            serde_json::Value::String(config.username.clone()),
        );
        map.insert(
            "cores".to_string(),
            serde_json::Value::Number(serde_json::Number::from(config.cores)),
        );
        if let Some(ref wid) = config.worker_id {
            map.insert(
                "worker_id".to_string(),
                serde_json::Value::String(wid.clone()),
            );
        } else if !map.contains_key("worker_id") {
            map.insert("worker_id".to_string(), serde_json::Value::Null);
        }
    }

    let formatted = serde_json::to_string_pretty(&root_val)
        .map_err(|e| format!("Failed to serialize configuration: {}", e))?;
    std::fs::write(&p, formatted)
        .map_err(|e| format!("Failed to write configuration file {}: {}", p.display(), e))?;
    Ok(())
}

/// Resolves configuration through interactive prompt or defaults / environment variables.
pub fn resolve_interactive(
    cli_server: Option<String>,
    cli_username: Option<String>,
    cli_cores: Option<usize>,
    no_interactive: bool,
) -> Result<WorkerConfig, String> {
    resolve_interactive_custom(
        cli_server,
        cli_username,
        cli_cores,
        no_interactive,
        None,
    )
}

/// Resolves configuration with custom path support.
pub fn resolve_interactive_custom(
    cli_server: Option<String>,
    cli_username: Option<String>,
    cli_cores: Option<usize>,
    no_interactive: bool,
    config_path: Option<&Path>,
) -> Result<WorkerConfig, String> {
    let stdin = std::io::stdin();
    let stdout = std::io::stdout();
    resolve_interactive_internal(
        cli_server,
        cli_username,
        cli_cores,
        no_interactive,
        config_path,
        &mut stdin.lock(),
        &mut stdout.lock(),
    )
}

/// Internal resolver supporting mock reader and writer for unit tests.
pub fn resolve_interactive_internal<R: BufRead, W: Write>(
    cli_server: Option<String>,
    cli_username: Option<String>,
    cli_cores: Option<usize>,
    no_interactive: bool,
    config_path: Option<&Path>,
    reader: &mut R,
    writer: &mut W,
) -> Result<WorkerConfig, String> {
    let target_path = config_path
        .map(|p| p.to_path_buf())
        .unwrap_or_else(default_config_path);

    if target_path.exists() {
        let mut cfg = load(Some(&target_path))?;
        if let Some(s) = cli_server {
            cfg.server_url = s;
        }
        if let Some(u) = cli_username {
            cfg.username = u;
        }
        if let Some(c) = cli_cores {
            cfg.cores = c.max(1);
        }
        return Ok(cfg);
    }

    if no_interactive {
        let server_url = cli_server
            .or_else(|| std::env::var("SHAPE_PACKING_SERVER").ok().filter(|s| !s.trim().is_empty()))
            .unwrap_or_else(default_server_url);

        let username = cli_username
            .or_else(|| std::env::var("SHAPE_PACKING_USERNAME").ok().filter(|s| !s.trim().is_empty()))
            .unwrap_or_else(default_system_username);

        let cores = cli_cores
            .or_else(|| {
                std::env::var("SHAPE_PACKING_CORES")
                    .ok()
                    .and_then(|s| s.parse::<usize>().ok())
            })
            .unwrap_or_else(detected_cores)
            .max(1);

        let worker_id = std::env::var("SHAPE_PACKING_WORKER_ID")
            .ok()
            .filter(|s| !s.trim().is_empty());

        let config = WorkerConfig {
            server_url,
            username,
            worker_id,
            cores,
        };
        return Ok(config);
    }

    // Interactive first-run setup wizard
    let max_cores = detected_cores();
    let default_server = cli_server
        .or_else(|| std::env::var("SHAPE_PACKING_SERVER").ok().filter(|s| !s.trim().is_empty()))
        .unwrap_or_else(default_server_url);

    let default_user = cli_username
        .or_else(|| std::env::var("SHAPE_PACKING_USERNAME").ok().filter(|s| !s.trim().is_empty()))
        .unwrap_or_else(default_system_username);

    let default_cores_val = cli_cores
        .or_else(|| {
            std::env::var("SHAPE_PACKING_CORES")
                .ok()
                .and_then(|s| s.parse::<usize>().ok())
        })
        .unwrap_or(max_cores)
        .max(1);

    writeln!(writer, "=============================================").map_err(|e| e.to_string())?;
    writeln!(writer, "    Distributed Shape Packing Worker Setup").map_err(|e| e.to_string())?;
    writeln!(writer, "=============================================").map_err(|e| e.to_string())?;

    write!(writer, "[?] Coordinator Server URL [{}]: ", default_server).map_err(|e| e.to_string())?;
    writer.flush().map_err(|e| e.to_string())?;
    let mut server_input = String::new();
    reader.read_line(&mut server_input).map_err(|e| e.to_string())?;
    let server_url = {
        let trimmed = server_input.trim();
        if trimmed.is_empty() {
            default_server
        } else {
            trimmed.to_string()
        }
    };

    write!(writer, "[?] Volunteer Username [{}]: ", default_user).map_err(|e| e.to_string())?;
    writer.flush().map_err(|e| e.to_string())?;
    let mut user_input = String::new();
    reader.read_line(&mut user_input).map_err(|e| e.to_string())?;
    let username = {
        let trimmed = user_input.trim();
        if trimmed.is_empty() {
            default_user
        } else {
            trimmed.to_string()
        }
    };

    write!(writer, "[?] Allocated CPU Cores (1-{}) [{}]: ", max_cores, default_cores_val).map_err(|e| e.to_string())?;
    writer.flush().map_err(|e| e.to_string())?;
    let mut cores_input = String::new();
    reader.read_line(&mut cores_input).map_err(|e| e.to_string())?;
    let cores = {
        let trimmed = cores_input.trim();
        if trimmed.is_empty() {
            default_cores_val
        } else {
            match trimmed.parse::<usize>() {
                Ok(c) => c.max(1),
                Err(_) => default_cores_val,
            }
        }
    };

    let config = WorkerConfig {
        server_url,
        username,
        worker_id: None,
        cores,
    };

    save(Some(&target_path), &config)?;
    writeln!(writer, "Settings saved to {}", target_path.display()).map_err(|e| e.to_string())?;

    Ok(config)
}

impl WorkerConfig {
    pub fn home_dir() -> PathBuf {
        home_dir()
    }

    pub fn default_config_path() -> PathBuf {
        default_config_path()
    }

    pub fn load(path: Option<&Path>) -> Result<Self, String> {
        load(path)
    }

    pub fn save(&self, path: Option<&Path>) -> Result<(), String> {
        save(path, self)
    }

    pub fn resolve_interactive(
        cli_server: Option<String>,
        cli_username: Option<String>,
        cli_cores: Option<usize>,
        no_interactive: bool,
    ) -> Result<Self, String> {
        resolve_interactive(cli_server, cli_username, cli_cores, no_interactive)
    }

    pub fn resolve_interactive_custom(
        cli_server: Option<String>,
        cli_username: Option<String>,
        cli_cores: Option<usize>,
        no_interactive: bool,
        config_path: Option<&Path>,
    ) -> Result<Self, String> {
        resolve_interactive_custom(cli_server, cli_username, cli_cores, no_interactive, config_path)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static TEST_COUNTER: AtomicUsize = AtomicUsize::new(0);

    fn temp_test_path(prefix: &str) -> PathBuf {
        let id = TEST_COUNTER.fetch_add(1, Ordering::SeqCst);
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_millis();
        std::env::temp_dir().join(format!("packer_rs_{}_{}_{}.json", prefix, timestamp, id))
    }

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
        assert_eq!(
            deserialized.worker_id,
            Some("123e4567-e89b-12d3-a456-426614174000".to_string())
        );
        assert_eq!(deserialized.cores, 4);
    }

    #[test]
    fn test_config_preserves_extra_fields() {
        let json_str = r#"{"server_url":"http://test","username":"bob","extra_gui_field":true}"#;
        let config: WorkerConfig = serde_json::from_str(json_str).unwrap();
        assert_eq!(config.server_url, "http://test");
        assert_eq!(config.username, "bob");
        assert_eq!(config.cores, 1);
        assert_eq!(config.worker_id, None);
    }

    #[test]
    fn test_home_dir_and_default_path() {
        let home = home_dir();
        assert!(!home.as_os_str().is_empty());
        let default_path = default_config_path();
        assert!(default_path.ends_with(".shape_packing_worker.json"));
        assert_eq!(default_path, home.join(".shape_packing_worker.json"));
    }

    #[test]
    fn test_save_and_load_roundtrip() {
        let path = temp_test_path("roundtrip");
        let config = WorkerConfig {
            server_url: "http://coord.example.com:9000".to_string(),
            username: "charlie".to_string(),
            worker_id: Some("test-uuid-99".to_string()),
            cores: 8,
        };

        config.save(Some(&path)).unwrap();
        assert!(path.exists());

        let loaded = WorkerConfig::load(Some(&path)).unwrap();
        assert_eq!(loaded, config);

        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_save_preserves_desktop_gui_fields() {
        let path = temp_test_path("gui_fields");
        let initial_json = r#"{
  "server_url": "https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net",
  "username": "desktop_user",
  "cores": 2,
  "autostart": true,
  "start_minimized": true,
  "schedule_enabled": true,
  "schedule_start": "22:00",
  "schedule_end": "07:00"
}"#;
        std::fs::write(&path, initial_json).unwrap();

        let mut config = WorkerConfig::load(Some(&path)).unwrap();
        assert_eq!(config.username, "desktop_user");
        assert_eq!(config.cores, 2);

        // Update fields and save
        config.username = "upgraded_user".to_string();
        config.cores = 16;
        config.worker_id = Some("newly-assigned-uuid".to_string());
        config.save(Some(&path)).unwrap();

        let raw_content = std::fs::read_to_string(&path).unwrap();
        let val: serde_json::Value = serde_json::from_str(&raw_content).unwrap();

        // Verify updated worker config fields
        assert_eq!(val["username"], "upgraded_user");
        assert_eq!(val["cores"], 16);
        assert_eq!(val["worker_id"], "newly-assigned-uuid");

        // Verify preserved desktop GUI keys
        assert_eq!(val["autostart"], true);
        assert_eq!(val["start_minimized"], true);
        assert_eq!(val["schedule_enabled"], true);
        assert_eq!(val["schedule_start"], "22:00");
        assert_eq!(val["schedule_end"], "07:00");

        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_resolve_interactive_when_config_exists_applies_cli_overrides() {
        let path = temp_test_path("existing_overrides");
        let existing = WorkerConfig {
            server_url: "http://existing:8000".to_string(),
            username: "existing_user".to_string(),
            worker_id: Some("id-123".to_string()),
            cores: 2,
        };
        existing.save(Some(&path)).unwrap();

        let mut input = Cursor::new(b"");
        let mut output = Vec::new();

        let resolved = resolve_interactive_internal(
            Some("http://override:9999".to_string()),
            None,
            Some(12),
            false,
            Some(&path),
            &mut input,
            &mut output,
        )
        .unwrap();

        assert_eq!(resolved.server_url, "http://override:9999");
        assert_eq!(resolved.username, "existing_user");
        assert_eq!(resolved.worker_id, Some("id-123".to_string()));
        assert_eq!(resolved.cores, 12);

        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_resolve_interactive_wizard_custom_input() {
        let path = temp_test_path("wizard_custom");
        assert!(!path.exists());

        let simulated_input = b"http://interactive.site:8000\nwizard_user\n6\n";
        let mut input = Cursor::new(simulated_input);
        let mut output = Vec::new();

        let resolved = resolve_interactive_internal(
            None,
            None,
            None,
            false,
            Some(&path),
            &mut input,
            &mut output,
        )
        .unwrap();

        assert_eq!(resolved.server_url, "http://interactive.site:8000");
        assert_eq!(resolved.username, "wizard_user");
        assert_eq!(resolved.worker_id, None);
        assert_eq!(resolved.cores, 6);

        // Verify saved to file
        assert!(path.exists());
        let on_disk = WorkerConfig::load(Some(&path)).unwrap();
        assert_eq!(on_disk, resolved);

        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_resolve_interactive_wizard_default_input() {
        let path = temp_test_path("wizard_defaults");
        assert!(!path.exists());

        // Pressing Enter to all 3 prompts
        let simulated_input = b"\n\n\n";
        let mut input = Cursor::new(simulated_input);
        let mut output = Vec::new();

        let resolved = resolve_interactive_internal(
            None,
            None,
            None,
            false,
            Some(&path),
            &mut input,
            &mut output,
        )
        .unwrap();

        assert_eq!(resolved.server_url, "https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net");
        assert_eq!(resolved.username, default_system_username());
        assert_eq!(resolved.cores, detected_cores());
        assert_eq!(resolved.worker_id, None);

        assert!(path.exists());
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_resolve_interactive_non_interactive() {
        let path = temp_test_path("non_interactive");
        assert!(!path.exists());

        let mut input = Cursor::new(b"");
        let mut output = Vec::new();

        let resolved = resolve_interactive_internal(
            Some("http://cli-headless:8000".to_string()),
            Some("headless_user".to_string()),
            Some(4),
            true,
            Some(&path),
            &mut input,
            &mut output,
        )
        .unwrap();

        assert_eq!(resolved.server_url, "http://cli-headless:8000");
        assert_eq!(resolved.username, "headless_user");
        assert_eq!(resolved.cores, 4);
        // Non-interactive does not auto-save missing file
        assert!(!path.exists());
    }
}
