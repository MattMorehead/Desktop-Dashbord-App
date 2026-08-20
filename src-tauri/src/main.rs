// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Emitter;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

#[tauri::command]
async fn open_external_url(url: String) -> Result<(), String> {
    open::that(url).map_err(|e| e.to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![open_external_url])
        .setup(|app| {
            let handle = app.handle().clone();

            if cfg!(debug_assertions) {
                // In debug mode, manually spawn the virtual environment Python script
                // bypassing tauri_plugin_shell's strict capability mapping completely.
                std::thread::spawn(move || {
                    use std::process::{Command, Stdio};
                    use std::io::{BufRead, BufReader};

                    let mut child = Command::new("../.venv/Scripts/python.exe")
                        .args(["../agent-backend/manager_agent.py"])
                        .stdout(Stdio::piped())
                        .stderr(Stdio::inherit())
                        .spawn()
                        .expect("Failed to spawn python sidecar");

                    if let Some(stdout) = child.stdout.take() {
                        let reader = BufReader::new(stdout);
                        for line in reader.lines() {
                            if let Ok(line_str) = line {
                                let _ = handle.emit("agent-state", line_str);
                            }
                        }
                    }
                });
            } else {
                tauri::async_runtime::spawn(async move {
                    let (mut rx, _child) = handle
                        .shell()
                        .sidecar("agent_sidecar")
                        .expect("failed to setup sidecar")
                        .spawn()
                        .expect("failed to spawn agent sidecar");

                    while let Some(event) = rx.recv().await {
                        if let tauri_plugin_shell::process::CommandEvent::Stdout(line) = event {
                            if let Ok(line_str) = String::from_utf8(line) {
                                let _ = handle.emit("agent-state", line_str);
                            }
                        }
                    }
                });
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
