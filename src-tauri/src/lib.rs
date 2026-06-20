// Shell Tauri de Audio2Tab: lanza el sidecar Python al iniciar y lo termina al salir.
use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::Manager;

/// Proceso del sidecar gestionado por la app.
struct Sidecar(Mutex<Option<Child>>);

/// Lanza el sidecar (FastAPI). Detecta en runtime si se está ejecutando desde
/// el paquete instalado (usando resource_dir) o desde el área de trabajo local.
fn spawn_sidecar(app_handle: &tauri::AppHandle) -> Option<Child> {
    let python = std::env::var("AUDIO2TAB_PYTHON").unwrap_or_else(|_| {
        let bundled_python = app_handle.path().resource_dir()
            .map(|p| p.join(".venv/Scripts/python.exe"))
            .unwrap_or_default();
        if bundled_python.exists() {
            bundled_python.to_string_lossy().to_string()
        } else {
            ".venv/Scripts/python.exe".to_string()
        }
    });

    let mut cmd = Command::new(python);
    cmd.args(["-m", "sidecar"]).env("PYTHONUTF8", "1");

    // Directorio de trabajo: donde está el paquete `sidecar` (y .mt3_checkpoints).
    let cwd = std::env::var("AUDIO2TAB_CWD").unwrap_or_else(|_| {
        let bundled_cwd = app_handle.path().resource_dir().unwrap_or_default();
        if bundled_cwd.join("sidecar").exists() {
            bundled_cwd.to_string_lossy().to_string()
        } else {
            ".".to_string()
        }
    });
    cmd.current_dir(cwd);

    match cmd.spawn() {
        Ok(child) => {
            log::info!("sidecar lanzado (pid {})", child.id());
            Some(child)
        }
        Err(e) => {
            log::error!("no se pudo lanzar el sidecar: {e}");
            None
        }
    }
}

fn kill_sidecar(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<Sidecar>() {
        if let Some(mut child) = state.0.lock().unwrap().take() {
            let _ = child.kill();
            log::info!("sidecar terminado");
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            app.manage(Sidecar(Mutex::new(spawn_sidecar(app.handle()))));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error al construir la app Tauri")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                kill_sidecar(app_handle);
            }
        });
}
