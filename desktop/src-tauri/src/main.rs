// Limn desktop: a thin Tauri shell around the Python core (SPEC §3 v3).
//
// On first launch it bootstraps a private Python runtime with uv (downloaded
// if absent), installs limn[serve] into an app-data venv, then runs
// `limn serve` as a localhost sidecar and shows its UI in the webview.
// Settings write the user's ~/.limn.yaml — bring your own provider/key;
// nothing ever leaves the machine except requests to that provider.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs;
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, RunEvent, State};

/// The limn release the runtime installs; bump together with PyPI releases.
const LIMN_VERSION: &str = "0.4.0";

struct Sidecar(Mutex<Option<Child>>);

#[derive(Serialize, Deserialize, Default, Clone)]
struct Settings {
    provider: String,
    base_url: String,
    api_key: String,
    model: String,
}

fn status(app: &AppHandle, message: &str) {
    let _ = app.emit("status", message.to_string());
}

fn config_path() -> Result<PathBuf, String> {
    dirs::home_dir()
        .map(|home| home.join(".limn.yaml"))
        .ok_or_else(|| "Could not determine home directory".into())
}

fn yaml_str(value: &serde_yaml::Value, key: &str) -> String {
    value
        .get(key)
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_string()
}

#[tauri::command]
fn get_settings() -> Settings {
    let Ok(path) = config_path() else {
        return Settings::default();
    };
    let Ok(text) = fs::read_to_string(&path) else {
        return Settings::default();
    };
    let Ok(root) = serde_yaml::from_str::<serde_yaml::Value>(&text) else {
        return Settings::default();
    };

    let provider = yaml_str(&root, "provider");
    // Mirror limn's resolve_settings: top-level keys, overridden by the
    // active provider's block under `providers:`.
    let mut settings = Settings {
        provider: provider.clone(),
        base_url: yaml_str(&root, "base_url"),
        api_key: yaml_str(&root, "api_key"),
        model: yaml_str(&root, "model"),
    };
    if let Some(overlay) = root.get("providers").and_then(|p| p.get(&provider)) {
        for (field, key) in [
            (&mut settings.base_url, "base_url"),
            (&mut settings.api_key, "api_key"),
            (&mut settings.model, "model"),
        ] {
            let value = yaml_str(overlay, key);
            if !value.is_empty() {
                *field = value;
            }
        }
    }
    settings
}

#[tauri::command]
fn save_settings(settings: Settings) -> Result<(), String> {
    if settings.provider.is_empty() {
        return Err("Pick a provider".into());
    }
    let path = config_path()?;

    // Preserve an existing config's other keys; only update what we own.
    let mut root = fs::read_to_string(&path)
        .ok()
        .and_then(|t| serde_yaml::from_str::<serde_yaml::Value>(&t).ok())
        .unwrap_or(serde_yaml::Value::Mapping(Default::default()));
    let serde_yaml::Value::Mapping(map) = &mut root else {
        return Err(format!("{} is not a YAML mapping; edit it by hand", path.display()));
    };

    map.insert("provider".into(), settings.provider.clone().into());

    let mut block = serde_yaml::Mapping::new();
    for (key, value) in [
        ("base_url", &settings.base_url),
        ("api_key", &settings.api_key),
        ("model", &settings.model),
    ] {
        if !value.is_empty() {
            block.insert(key.into(), value.clone().into());
        }
    }
    let providers = map
        .entry("providers".into())
        .or_insert(serde_yaml::Value::Mapping(Default::default()));
    if let serde_yaml::Value::Mapping(providers) = providers {
        providers.insert(settings.provider.clone().into(), block.into());
    }

    let text = serde_yaml::to_string(&root).map_err(|e| e.to_string())?;
    fs::write(&path, text).map_err(|e| e.to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(&path, fs::Permissions::from_mode(0o600));
    }
    Ok(())
}

fn command(program: impl AsRef<std::ffi::OsStr>) -> Command {
    let cmd = Command::new(program);
    #[cfg(windows)]
    let cmd = {
        use std::os::windows::process::CommandExt;
        let mut c = cmd;
        c.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
        c
    };
    cmd
}

fn run_ok(cmd: &mut Command) -> Result<(), String> {
    let output = cmd.output().map_err(|e| e.to_string())?;
    if output.status.success() {
        Ok(())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).trim().to_string())
    }
}

fn find_uv() -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Some(home) = dirs::home_dir() {
        candidates.push(home.join(".local/bin/uv"));
        candidates.push(home.join(".cargo/bin/uv"));
    }
    candidates.push("/opt/homebrew/bin/uv".into());
    candidates.push("/usr/local/bin/uv".into());
    #[cfg(windows)]
    if let Some(home) = dirs::home_dir() {
        candidates.push(home.join(".local\\bin\\uv.exe"));
    }
    for path in candidates {
        if path.exists() {
            return Some(path);
        }
    }
    // Fall back to PATH (GUI apps on macOS get a minimal PATH, hence the
    // absolute candidates above).
    let probe = command("uv").arg("--version").output();
    if matches!(probe, Ok(ref o) if o.status.success()) {
        return Some("uv".into());
    }
    None
}

fn install_uv(app: &AppHandle) -> Result<PathBuf, String> {
    status(app, "Downloading uv (one-time)…");
    #[cfg(not(windows))]
    run_ok(command("sh").args(["-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]))?;
    #[cfg(windows)]
    run_ok(command("powershell").args([
        "-NoProfile",
        "-ExecutionPolicy",
        "ByPass",
        "-Command",
        "irm https://astral.sh/uv/install.ps1 | iex",
    ]))?;
    find_uv().ok_or_else(|| "uv installed but not found".into())
}

fn limn_bin(venv: &Path) -> PathBuf {
    #[cfg(windows)]
    return venv.join("Scripts").join("limn.exe");
    #[cfg(not(windows))]
    venv.join("bin").join("limn")
}

fn venv_python(venv: &Path) -> PathBuf {
    #[cfg(windows)]
    return venv.join("Scripts").join("python.exe");
    #[cfg(not(windows))]
    venv.join("bin").join("python")
}

/// First run: create the app's private venv (uv downloads a managed Python,
/// no system Python needed) and install limn into it.
fn ensure_runtime(app: &AppHandle, force_update: bool) -> Result<PathBuf, String> {
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| e.to_string())?;
    fs::create_dir_all(&data_dir).map_err(|e| e.to_string())?;
    let venv = data_dir.join("runtime");
    let bin = limn_bin(&venv);

    // The marker records which limn release is installed, so bumping
    // LIMN_VERSION in a new app build upgrades existing runtimes.
    let marker = venv.join("limn-version");
    let installed = fs::read_to_string(&marker).unwrap_or_default();
    if bin.exists() && installed.trim() == LIMN_VERSION && !force_update {
        return Ok(bin);
    }

    let uv = match find_uv() {
        Some(uv) => uv,
        None => install_uv(app)?,
    };

    if !venv.exists() {
        status(app, "Setting up Python runtime (one-time, ~a minute)…");
        run_ok(command(&uv).args(["venv", "--python", "3.12"]).arg(&venv))?;
    }
    status(app, "Installing Limn…");
    run_ok(
        command(&uv)
            .args(["pip", "install", "--upgrade", "--python"])
            .arg(venv_python(&venv))
            .arg(format!("limn[serve]=={LIMN_VERSION}")),
    )?;
    let _ = fs::write(&marker, LIMN_VERSION);
    Ok(bin)
}

fn free_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    Ok(listener.local_addr().map_err(|e| e.to_string())?.port())
}

fn kill_sidecar(sidecar: &Sidecar) {
    if let Ok(mut guard) = sidecar.0.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn spawn_sidecar(app: &AppHandle, bin: &Path) -> Result<u16, String> {
    let port = free_port()?;
    let out_dir = dirs::picture_dir()
        .or_else(dirs::home_dir)
        .unwrap_or_else(|| ".".into())
        .join("Limn");

    status(app, "Starting Limn…");
    let child = command(bin)
        .args([
            "serve",
            "--no-browser",
            "--host",
            "127.0.0.1",
            "--port",
            &port.to_string(),
            "--out-dir",
        ])
        .arg(&out_dir)
        .spawn()
        .map_err(|e| format!("Could not start limn: {e}"))?;

    let sidecar: State<Sidecar> = app.state();
    kill_sidecar(&sidecar);
    *sidecar.0.lock().unwrap() = Some(child);

    // Wait until the server accepts connections.
    let deadline = Instant::now() + Duration::from_secs(30);
    let addr = format!("127.0.0.1:{port}");
    loop {
        if TcpStream::connect(&addr).is_ok() {
            std::thread::sleep(Duration::from_millis(300));
            return Ok(port);
        }
        if Instant::now() > deadline {
            return Err("Limn server did not come up within 30s".into());
        }
        std::thread::sleep(Duration::from_millis(200));
    }
}

#[tauri::command]
async fn start_server(app: AppHandle, update: bool) -> Result<u16, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let bin = ensure_runtime(&app, update)?;
        spawn_sidecar(&app, &bin)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn restart_server(app: AppHandle) -> Result<u16, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let bin = ensure_runtime(&app, false)?;
        spawn_sidecar(&app, &bin)
    })
    .await
    .map_err(|e| e.to_string())?
}

fn main() {
    tauri::Builder::default()
        .manage(Sidecar(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            get_settings,
            save_settings,
            start_server,
            restart_server
        ])
        .build(tauri::generate_context!())
        .expect("error while building Limn")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                kill_sidecar(&app.state::<Sidecar>());
            }
        });
}
