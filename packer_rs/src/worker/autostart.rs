use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

pub const APP_NAME: &str = "ShapePackingWorker";
pub const MACOS_PLIST_LABEL: &str = "com.shapepacking.worker";
pub const WINDOWS_RUN_KEY: &str = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run";

/// Cross-platform autostart status.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AutostartStatus {
    pub enabled: bool,
    pub target_path: Option<String>,
}

// ---------------------------------------------------------------------------
// Windows Implementation & Helpers
// ---------------------------------------------------------------------------

pub fn build_windows_reg_add_args(exe_path: &str) -> Vec<String> {
    let clean = exe_path.trim().trim_matches('"');
    let quoted = format!("\"{}\"", clean);
    vec![
        "add".to_string(),
        WINDOWS_RUN_KEY.to_string(),
        "/v".to_string(),
        APP_NAME.to_string(),
        "/t".to_string(),
        "REG_SZ".to_string(),
        "/d".to_string(),
        quoted,
        "/f".to_string(),
    ]
}

pub fn build_windows_reg_delete_args() -> Vec<String> {
    vec![
        "delete".to_string(),
        WINDOWS_RUN_KEY.to_string(),
        "/v".to_string(),
        APP_NAME.to_string(),
        "/f".to_string(),
    ]
}

pub fn build_windows_reg_query_args() -> Vec<String> {
    vec![
        "query".to_string(),
        WINDOWS_RUN_KEY.to_string(),
        "/v".to_string(),
        APP_NAME.to_string(),
    ]
}

pub fn parse_reg_query_output(output: &str) -> Option<String> {
    let needle = APP_NAME.to_lowercase();
    for line in output.lines() {
        let trimmed = line.trim();
        if let Some(idx) = trimmed.to_lowercase().find(&needle) {
            let after_name = &trimmed[idx + APP_NAME.len()..];
            let (type_len, pos) = if let Some(p) = after_name.find("REG_SZ") {
                ("REG_SZ".len(), p)
            } else if let Some(p) = after_name.find("REG_EXPAND_SZ") {
                ("REG_EXPAND_SZ".len(), p)
            } else {
                continue;
            };
            let val = after_name[pos + type_len..].trim();
            let clean = val.trim_matches('"');
            if !clean.is_empty() {
                return Some(clean.to_string());
            }
        }
    }
    None
}

pub fn windows_status_from_output(
    success: bool,
    stdout: &str,
    stderr: &str,
) -> Result<AutostartStatus, String> {
    if success {
        let path = parse_reg_query_output(stdout);
        Ok(AutostartStatus {
            enabled: true,
            target_path: path,
        })
    } else {
        let combined = format!("{}\n{}", stdout, stderr).to_lowercase();
        if combined.contains("unable to find") || combined.contains("not find") {
            Ok(AutostartStatus {
                enabled: false,
                target_path: None,
            })
        } else {
            Err(format!("reg query failed: {}", stderr.trim()))
        }
    }
}

#[cfg(target_os = "windows")]
fn windows_enable(exe_path: &Path) -> Result<(), String> {
    let path_str = exe_path
        .to_str()
        .ok_or_else(|| "Invalid UTF-8 in executable path".to_string())?;
    let args = build_windows_reg_add_args(path_str);
    let output = std::process::Command::new("reg")
        .args(&args)
        .output()
        .map_err(|e| format!("Failed to execute reg.exe: {e}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("reg add failed: {}", stderr.trim()));
    }
    Ok(())
}

#[cfg(target_os = "windows")]
fn windows_disable() -> Result<(), String> {
    let args = build_windows_reg_delete_args();
    let output = std::process::Command::new("reg")
        .args(&args)
        .output()
        .map_err(|e| format!("Failed to execute reg.exe: {e}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stdout = String::from_utf8_lossy(&output.stdout);
        let combined = format!("{}\n{}", stdout, stderr).to_lowercase();
        if !combined.contains("unable to find") && !combined.contains("not find") {
            return Err(format!("reg delete failed: {}", stderr.trim()));
        }
    }
    Ok(())
}

#[cfg(target_os = "windows")]
fn windows_status() -> Result<AutostartStatus, String> {
    let args = build_windows_reg_query_args();
    let output = std::process::Command::new("reg")
        .args(&args)
        .output()
        .map_err(|e| format!("Failed to execute reg.exe: {e}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    windows_status_from_output(output.status.success(), &stdout, &stderr)
}

// ---------------------------------------------------------------------------
// Linux Implementation & Helpers
// ---------------------------------------------------------------------------

pub fn generate_desktop_entry(exe_path: &str) -> String {
    let clean = exe_path.trim().trim_matches('"');
    let exec_val = if clean.contains(' ') {
        format!("\"{}\"", clean)
    } else {
        clean.to_string()
    };
    format!(
        "[Desktop Entry]\n\
         Type=Application\n\
         Version=1.0\n\
         Name=Shape Packing Worker\n\
         Comment=Distributed Shape Packing Volunteer Node\n\
         Exec={}\n\
         Terminal=false\n\
         Categories=Utility;Math;Science;\n",
        exec_val
    )
}

pub fn parse_desktop_entry(content: &str) -> (bool, Option<String>) {
    let mut hidden = false;
    let mut exec = None;
    for line in content.lines() {
        let trimmed = line.trim();
        if let Some(val) = trimmed.strip_prefix("Hidden=") {
            if val.trim().eq_ignore_ascii_case("true") {
                hidden = true;
            }
        } else if let Some(val) = trimmed.strip_prefix("Exec=") {
            let clean = val.trim().trim_matches('"');
            if !clean.is_empty() {
                exec = Some(clean.to_string());
            }
        }
    }
    if hidden {
        (false, exec)
    } else {
        (exec.is_some(), exec)
    }
}

pub fn linux_autostart_dir() -> PathBuf {
    if let Some(xdg) = std::env::var_os("XDG_CONFIG_HOME") {
        PathBuf::from(xdg).join("autostart")
    } else {
        super::config::home_dir().join(".config").join("autostart")
    }
}

pub fn linux_desktop_file_path() -> PathBuf {
    linux_autostart_dir().join("shape-packing-worker.desktop")
}

pub fn linux_enable_in(autostart_dir: &Path, exe_path: &Path) -> Result<(), String> {
    std::fs::create_dir_all(autostart_dir)
        .map_err(|e| format!("Failed to create autostart directory {}: {e}", autostart_dir.display()))?;
    let file_path = autostart_dir.join("shape-packing-worker.desktop");
    let path_str = exe_path
        .to_str()
        .ok_or_else(|| "Invalid UTF-8 in executable path".to_string())?;
    let content = generate_desktop_entry(path_str);
    std::fs::write(&file_path, content)
        .map_err(|e| format!("Failed to write {}: {e}", file_path.display()))?;
    Ok(())
}

pub fn linux_disable_in(autostart_dir: &Path) -> Result<(), String> {
    let file_path = autostart_dir.join("shape-packing-worker.desktop");
    if file_path.exists() {
        std::fs::remove_file(&file_path)
            .map_err(|e| format!("Failed to remove {}: {e}", file_path.display()))?;
    }
    Ok(())
}

pub fn linux_status_in(autostart_dir: &Path) -> Result<AutostartStatus, String> {
    let file_path = autostart_dir.join("shape-packing-worker.desktop");
    if !file_path.exists() {
        return Ok(AutostartStatus {
            enabled: false,
            target_path: None,
        });
    }
    let content = std::fs::read_to_string(&file_path)
        .map_err(|e| format!("Failed to read {}: {e}", file_path.display()))?;
    let (enabled, target_path) = parse_desktop_entry(&content);
    Ok(AutostartStatus {
        enabled,
        target_path,
    })
}

// ---------------------------------------------------------------------------
// macOS Implementation & Helpers
// ---------------------------------------------------------------------------

fn xml_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

fn xml_unescape(s: &str) -> String {
    s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&apos;", "'")
}

pub fn generate_launchd_plist(exe_path: &str) -> String {
    let clean = exe_path.trim().trim_matches('"');
    let escaped = xml_escape(clean);
    format!(
r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"#,
        MACOS_PLIST_LABEL, escaped
    )
}

pub fn parse_launchd_plist(content: &str) -> (bool, Option<String>) {
    let mut in_prog_args = false;
    let mut pending_disabled = false;
    let mut disabled = false;
    let mut target = None;

    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.contains("<key>Disabled</key>") {
            pending_disabled = true;
            if trimmed.contains("<true/>") {
                disabled = true;
            }
        } else if pending_disabled {
            if trimmed.contains("<true/>") {
                disabled = true;
            } else if trimmed.contains("<key>") {
                pending_disabled = false;
            }
        }

        if trimmed.contains("<key>ProgramArguments</key>") {
            in_prog_args = true;
            continue;
        }

        if in_prog_args {
            if trimmed.contains("</array>") || trimmed.contains("</dict>") {
                in_prog_args = false;
                continue;
            }
            if let Some(start) = trimmed.find("<string>") {
                if let Some(end) = trimmed.find("</string>") {
                    let s_start = start + "<string>".len();
                    if end > s_start {
                        let path = trimmed[s_start..end].trim().trim_matches('"');
                        if !path.is_empty() && target.is_none() {
                            target = Some(xml_unescape(path));
                        }
                    }
                }
            }
        }
    }

    if disabled {
        (false, target)
    } else {
        (target.is_some(), target)
    }
}

pub fn macos_launch_agents_dir() -> PathBuf {
    super::config::home_dir().join("Library").join("LaunchAgents")
}

pub fn macos_plist_file_path() -> PathBuf {
    macos_launch_agents_dir().join(format!("{MACOS_PLIST_LABEL}.plist"))
}

pub fn macos_enable_in(agents_dir: &Path, exe_path: &Path) -> Result<(), String> {
    std::fs::create_dir_all(agents_dir)
        .map_err(|e| format!("Failed to create LaunchAgents directory {}: {e}", agents_dir.display()))?;
    let file_path = agents_dir.join(format!("{MACOS_PLIST_LABEL}.plist"));
    let path_str = exe_path
        .to_str()
        .ok_or_else(|| "Invalid UTF-8 in executable path".to_string())?;
    let content = generate_launchd_plist(path_str);
    std::fs::write(&file_path, content)
        .map_err(|e| format!("Failed to write {}: {e}", file_path.display()))?;
    Ok(())
}

pub fn macos_disable_in(agents_dir: &Path) -> Result<(), String> {
    let file_path = agents_dir.join(format!("{MACOS_PLIST_LABEL}.plist"));
    if file_path.exists() {
        std::fs::remove_file(&file_path)
            .map_err(|e| format!("Failed to remove {}: {e}", file_path.display()))?;
    }
    Ok(())
}

pub fn macos_status_in(agents_dir: &Path) -> Result<AutostartStatus, String> {
    let file_path = agents_dir.join(format!("{MACOS_PLIST_LABEL}.plist"));
    if !file_path.exists() {
        return Ok(AutostartStatus {
            enabled: false,
            target_path: None,
        });
    }
    let content = std::fs::read_to_string(&file_path)
        .map_err(|e| format!("Failed to read {}: {e}", file_path.display()))?;
    let (enabled, target_path) = parse_launchd_plist(&content);
    Ok(AutostartStatus {
        enabled,
        target_path,
    })
}

// ---------------------------------------------------------------------------
// Cross-Platform Public API
// ---------------------------------------------------------------------------

/// Enables autostart using an explicit executable path.
#[cfg(target_os = "windows")]
pub fn enable_autostart_for_path(exe_path: &Path) -> Result<(), String> {
    windows_enable(exe_path)
}

#[cfg(target_os = "windows")]
pub fn disable_autostart() -> Result<(), String> {
    windows_disable()
}

#[cfg(target_os = "windows")]
pub fn autostart_status() -> Result<AutostartStatus, String> {
    windows_status()
}

#[cfg(target_os = "macos")]
pub fn enable_autostart_for_path(exe_path: &Path) -> Result<(), String> {
    macos_enable_in(&macos_launch_agents_dir(), exe_path)
}

#[cfg(target_os = "macos")]
pub fn disable_autostart() -> Result<(), String> {
    macos_disable_in(&macos_launch_agents_dir())
}

#[cfg(target_os = "macos")]
pub fn autostart_status() -> Result<AutostartStatus, String> {
    macos_status_in(&macos_launch_agents_dir())
}

#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub fn enable_autostart_for_path(exe_path: &Path) -> Result<(), String> {
    linux_enable_in(&linux_autostart_dir(), exe_path)
}

#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub fn disable_autostart() -> Result<(), String> {
    linux_disable_in(&linux_autostart_dir())
}

#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub fn autostart_status() -> Result<AutostartStatus, String> {
    linux_status_in(&linux_autostart_dir())
}

/// Enables autostart using the current running executable.
pub fn enable_autostart() -> Result<(), String> {
    let exe = std::env::current_exe()
        .map_err(|e| format!("Failed to get current executable path: {e}"))?;
    enable_autostart_for_path(&exe)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_autostart_status_no_panic() {
        let result = autostart_status();
        match result {
            Ok(status) => {
                if status.enabled {
                    assert!(status.target_path.is_some());
                }
            }
            Err(err) => {
                assert!(!err.is_empty());
            }
        }
    }

    #[test]
    fn test_windows_reg_args_builders() {
        let add_args = build_windows_reg_add_args(r"C:\Program Files\Shape\worker.exe");
        assert_eq!(add_args[0], "add");
        assert_eq!(add_args[1], WINDOWS_RUN_KEY);
        assert_eq!(add_args[2], "/v");
        assert_eq!(add_args[3], APP_NAME);
        assert_eq!(add_args[4], "/t");
        assert_eq!(add_args[5], "REG_SZ");
        assert_eq!(add_args[6], "/d");
        assert_eq!(add_args[7], "\"C:\\Program Files\\Shape\\worker.exe\"");
        assert_eq!(add_args[8], "/f");

        let del_args = build_windows_reg_delete_args();
        assert_eq!(
            del_args,
            vec!["delete", WINDOWS_RUN_KEY, "/v", APP_NAME, "/f"]
        );

        let query_args = build_windows_reg_query_args();
        assert_eq!(
            query_args,
            vec!["query", WINDOWS_RUN_KEY, "/v", APP_NAME]
        );
    }

    #[test]
    fn test_windows_parse_reg_query_output() {
        let sample_quoted = "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\r\n    ShapePackingWorker    REG_SZ    \"C:\\Program Files\\Shape\\worker.exe\"\r\n";
        assert_eq!(
            parse_reg_query_output(sample_quoted),
            Some("C:\\Program Files\\Shape\\worker.exe".to_string())
        );

        let sample_unquoted = "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\n    ShapePackingWorker    REG_SZ    C:\\Tools\\worker.exe\n";
        assert_eq!(
            parse_reg_query_output(sample_unquoted),
            Some("C:\\Tools\\worker.exe".to_string())
        );

        let sample_expand_sz = "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\n    ShapePackingWorker    REG_EXPAND_SZ    \"%LOCALAPPDATA%\\worker.exe\"\n";
        assert_eq!(
            parse_reg_query_output(sample_expand_sz),
            Some("%LOCALAPPDATA%\\worker.exe".to_string())
        );

        let sample_missing = "ERROR: The system was unable to find the specified registry key or value.\r\n";
        assert_eq!(parse_reg_query_output(sample_missing), None);

        assert_eq!(parse_reg_query_output(""), None);
    }

    #[test]
    fn test_windows_status_from_output() {
        let stdout = "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\n    ShapePackingWorker    REG_SZ    \"C:\\app\\worker.exe\"\n";
        let status = windows_status_from_output(true, stdout, "").unwrap();
        assert!(status.enabled);
        assert_eq!(
            status.target_path,
            Some("C:\\app\\worker.exe".to_string())
        );

        let status_missing = windows_status_from_output(
            false,
            "",
            "ERROR: The system was unable to find the specified registry key or value.\r\n",
        )
        .unwrap();
        assert!(!status_missing.enabled);
        assert_eq!(status_missing.target_path, None);

        let err_result =
            windows_status_from_output(false, "", "ERROR: Access is denied.\r\n");
        assert!(err_result.is_err());
        assert!(err_result.unwrap_err().contains("Access is denied"));
    }

    #[test]
    fn test_linux_generate_and_parse_desktop_entry() {
        let exe_no_space = "/usr/local/bin/shape-packing-worker";
        let content1 = generate_desktop_entry(exe_no_space);
        assert!(content1.contains("Exec=/usr/local/bin/shape-packing-worker"));
        assert!(content1.contains("Type=Application"));
        let (enabled1, parsed1) = parse_desktop_entry(&content1);
        assert!(enabled1);
        assert_eq!(parsed1, Some(exe_no_space.to_string()));

        let exe_with_space = "/opt/my tools/shape-packing-worker";
        let content2 = generate_desktop_entry(exe_with_space);
        assert!(content2.contains("Exec=\"/opt/my tools/shape-packing-worker\""));
        let (enabled2, parsed2) = parse_desktop_entry(&content2);
        assert!(enabled2);
        assert_eq!(parsed2, Some(exe_with_space.to_string()));

        let hidden_content = "[Desktop Entry]\nHidden=true\nExec=/bin/worker\n";
        let (enabled_hidden, parsed_hidden) = parse_desktop_entry(hidden_content);
        assert!(!enabled_hidden);
        assert_eq!(parsed_hidden, Some("/bin/worker".to_string()));
    }

    #[test]
    fn test_linux_enable_status_disable_lifecycle() {
        let unique_id = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let temp_dir = std::env::temp_dir().join(format!("test_linux_autostart_{unique_id}"));
        let _ = std::fs::remove_dir_all(&temp_dir);

        // Initially disabled
        let initial_status = linux_status_in(&temp_dir).unwrap();
        assert!(!initial_status.enabled);
        assert_eq!(initial_status.target_path, None);

        // Enable
        let target_exe = Path::new("/usr/bin/shape-packing-worker");
        linux_enable_in(&temp_dir, target_exe).unwrap();

        // Status after enable
        let status = linux_status_in(&temp_dir).unwrap();
        assert!(status.enabled);
        assert_eq!(
            status.target_path,
            Some("/usr/bin/shape-packing-worker".to_string())
        );

        // Disable
        linux_disable_in(&temp_dir).unwrap();
        let status_after_disable = linux_status_in(&temp_dir).unwrap();
        assert!(!status_after_disable.enabled);
        assert_eq!(status_after_disable.target_path, None);

        // Disable again (idempotent)
        linux_disable_in(&temp_dir).unwrap();

        let _ = std::fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_macos_generate_and_parse_plist() {
        let exe = "/usr/local/bin/shape-packing-worker";
        let content = generate_launchd_plist(exe);
        assert!(content.contains(MACOS_PLIST_LABEL));
        assert!(content.contains("<string>/usr/local/bin/shape-packing-worker</string>"));
        assert!(content.contains("<key>RunAtLoad</key>"));

        let (enabled, parsed) = parse_launchd_plist(&content);
        assert!(enabled);
        assert_eq!(parsed, Some(exe.to_string()));
    }

    #[test]
    fn test_macos_enable_status_disable_lifecycle() {
        let unique_id = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let temp_dir = std::env::temp_dir().join(format!("test_macos_autostart_{unique_id}"));
        let _ = std::fs::remove_dir_all(&temp_dir);

        // Initially disabled
        let initial_status = macos_status_in(&temp_dir).unwrap();
        assert!(!initial_status.enabled);
        assert_eq!(initial_status.target_path, None);

        // Enable
        let target_exe = Path::new("/Applications/ShapePackingWorker.app/Contents/MacOS/worker");
        macos_enable_in(&temp_dir, target_exe).unwrap();

        // Status after enable
        let status = macos_status_in(&temp_dir).unwrap();
        assert!(status.enabled);
        assert_eq!(
            status.target_path,
            Some("/Applications/ShapePackingWorker.app/Contents/MacOS/worker".to_string())
        );

        // Disable
        macos_disable_in(&temp_dir).unwrap();
        let status_after_disable = macos_status_in(&temp_dir).unwrap();
        assert!(!status_after_disable.enabled);
        assert_eq!(status_after_disable.target_path, None);

        // Disable again (idempotent)
        macos_disable_in(&temp_dir).unwrap();

        let _ = std::fs::remove_dir_all(&temp_dir);
    }
}
