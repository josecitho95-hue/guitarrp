// Shell Tauri de Audio2Tab: lanza el sidecar Python al iniciar y lo termina al salir.
use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::Manager;

/// Proceso del sidecar gestionado por la app.
struct Sidecar(Mutex<Option<Child>>);

fn resolve_local_paths(app_handle: &tauri::AppHandle) -> (String, String) {
    // 1. Intentar resolver desde resource_dir (producción empaquetada)
    if let Ok(resource_path) = app_handle.path().resource_dir() {
        let python_path = resource_path.join(".venv/Scripts/python.exe");
        let sidecar_dir = resource_path.join("sidecar");
        if python_path.exists() && sidecar_dir.exists() {
            return (
                python_path.to_string_lossy().to_string(),
                resource_path.to_string_lossy().to_string(),
            );
        }
    }

    // 2. Fallback de desarrollo/ejecución local: buscar subiendo directorios desde el ejecutable actual
    if let Ok(exe_path) = std::env::current_exe() {
        let mut dir = exe_path.parent();
        while let Some(d) = dir {
            let python_path = d.join(".venv/Scripts/python.exe");
            let sidecar_dir = d.join("sidecar");
            if python_path.exists() && sidecar_dir.exists() {
                return (
                    python_path.to_string_lossy().to_string(),
                    d.to_string_lossy().to_string(),
                );
            }
            dir = d.parent();
        }
    }

    // 3. Fallback final relativo (si todo lo demás falla)
    (".venv/Scripts/python.exe".to_string(), ".".to_string())
}

/// Lanza el sidecar (FastAPI). Detecta en runtime si se está ejecutando desde
/// el paquete instalado o resolviendo dinámicamente desde el área de trabajo local.
fn spawn_sidecar(app_handle: &tauri::AppHandle) -> Option<Child> {
    let (resolved_python, resolved_cwd) = resolve_local_paths(app_handle);

    let python = std::env::var("AUDIO2TAB_PYTHON").unwrap_or(resolved_python);
    let cwd = std::env::var("AUDIO2TAB_CWD").unwrap_or(resolved_cwd);

    log::info!("Lanzando sidecar: python={}, cwd={}", python, cwd);

    let mut cmd = Command::new(python);
    cmd.args(["-m", "sidecar"]).env("PYTHONUTF8", "1");
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
