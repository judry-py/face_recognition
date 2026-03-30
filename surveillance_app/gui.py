from __future__ import annotations

import os
import subprocess
import sys
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

import cv2

from .config import AppConfig, build_dashboard_url, ensure_directories, load_config, resolve_project_path
from .logging_utils import get_logger, setup_logging
from .services import (
    alert_beep,
    append_csv_row,
    generate_html_report,
    get_startup_bat_path,
    load_csv_rows,
    send_telegram_message,
)
from .utils import (
    create_preview_image,
    is_time_in_window,
    safe_timestamp,
    sanitize_name,
    save_snapshot,
    timestamp_label,
)
from .vision import (
    detect_motion,
    detect_people,
    draw_overlay,
    evaluate_suspicious_activity,
    list_available_cameras,
    load_known_faces,
    recognize_faces,
)

LOGGER = get_logger(__name__)


class SurveillanceGUI:
    def __init__(self, root: tk.Tk | object, auto_start: bool | None = None):
        self.root = root
        self.config = load_config()
        ensure_directories(self.config)

        self.capture = None
        self.running = False
        self.frame_index = 0
        self.previous_gray = None
        self.face_results = []
        self.motion_streak = 0
        self.last_alert_time = 0.0
        self.last_unknown_alert = 0.0
        self.last_unknown_snapshot = 0.0
        self.last_log_times = {}
        self.last_alert_message = ""
        self.pending_unknown_crop = None
        self.current_frame = None
        self.dashboard_process = None
        self.recording_writer = None
        self.recording_until = 0.0
        self.recording_path = ""
        self.known_face_encodings = []
        self.known_face_names = []
        self.is_prompt_open = False
        self.available_cameras = []
        self.person_detections = []
        self.history_box = None
        self.settings_box = None
        self.log_box = None

        self.status_var = tk.StringVar(value="Prêt")
        self.detail_var = tk.StringVar(value="Caméra inactive")
        self.schedule_var = tk.StringVar(value="Horaires non vérifiés")
        self.people_var = tk.StringVar(value="Aucune base chargée")
        self.mode_var = tk.StringVar(value="Mode: attente")
        self.profile_var = tk.StringVar(value="Profil: jour")
        self.time_var = tk.StringVar(value=f"Heure: {timestamp_label()}")
        self.faces_var = tk.StringVar(value="Visages détectés: aucun")
        self.human_var = tk.StringVar(value="IA humain: en attente")
        self.motion_var = tk.StringVar(value="Mouvement: 0.00%")
        self.recording_var = tk.StringVar(value="Enregistrement: inactif")
        self.telegram_var = tk.StringVar(value="Telegram: actif" if self.config.telegram_enabled else "Telegram: inactif")
        self.camera_var = tk.StringVar(value=str(self.config.camera_index))
        self.alerts_var = tk.StringVar(value="Aucune alerte récente")
        self.session_var = tk.StringVar(value="Système prêt")
        self.fullscreen_var = tk.StringVar(value="Mode fenêtre")

        self.build_ui()
        self.reload_faces(show_popup=False)

        should_auto_start = self.config.auto_start_camera if auto_start is None else auto_start
        if should_auto_start:
            self.root.after(200, self.start_surveillance)

    def setup_styles(self) -> None:
        if ctk is not None:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")

        if ctk is not None and isinstance(self.root, ctk.CTk):
            self.root.configure(fg_color="#0b1120")
        else:
            self.root.configure(bg="#0b1120")

    def create_status_card(self, parent, title: str, variable: tk.StringVar, column: int) -> None:
        card = ctk.CTkFrame(parent, corner_radius=16, fg_color="#111827") if ctk else tk.Frame(parent, bg="#111827")
        card.grid(row=0, column=column, sticky="nsew", padx=6, pady=6)
        if ctk:
            ctk.CTkLabel(card, text=title, text_color="#93c5fd", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=12, pady=(10, 0))
            ctk.CTkLabel(card, textvariable=variable, text_color="#f8fafc", wraplength=220, justify="left", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(6, 10))
        else:
            tk.Label(card, text=title, bg="#111827", fg="#93c5fd", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
            tk.Label(card, textvariable=variable, bg="#111827", fg="#f8fafc", wraplength=220, justify="left", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(6, 10))

    def create_action_button(self, parent, text: str, command, row: int, column: int, color: str) -> None:
        if ctk:
            button = ctk.CTkButton(
                parent,
                text=text,
                command=command,
                fg_color=color,
                hover_color="#1d4ed8" if color == "#2563eb" else color,
                corner_radius=10,
                height=38,
                font=ctk.CTkFont(size=13, weight="bold"),
            )
            button.grid(row=row, column=column, sticky="ew", padx=5, pady=5)
        else:
            tk.Button(parent, text=text, command=command, bg=color, fg="white").grid(row=row, column=column, sticky="ew", padx=5, pady=5)

    def build_ui(self) -> None:
        self.root.title("Surveillance intelligente - interface premium")
        default_width = max(self.config.window_width, 1360)
        default_height = max(self.config.window_height, 860)
        self.root.geometry(f"{default_width}x{default_height}")
        self.root.minsize(1280, 820)
        self.setup_styles()

        main_frame = ctk.CTkFrame(self.root, fg_color="#0b1120", corner_radius=0) if ctk else tk.Frame(self.root, bg="#0b1120")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        header = ctk.CTkFrame(main_frame, fg_color="transparent") if ctk else tk.Frame(main_frame, bg="#0b1120")
        header.pack(fill="x", pady=(0, 10))
        if ctk:
            ctk.CTkLabel(header, text="🛡 Surveillance intelligente", text_color="#f8fafc", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w")
            ctk.CTkLabel(header, text="Architecture modulaire, surveillance locale et interface premium.", text_color="#94a3b8", font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(2, 0))

        metrics_frame = ctk.CTkFrame(main_frame, fg_color="transparent") if ctk else tk.Frame(main_frame, bg="#0b1120")
        metrics_frame.pack(fill="x", pady=(0, 10))
        for index in range(4):
            metrics_frame.columnconfigure(index, weight=1)
        self.create_status_card(metrics_frame, "État système", self.status_var, 0)
        self.create_status_card(metrics_frame, "Alertes", self.alerts_var, 1)
        self.create_status_card(metrics_frame, "Détection", self.people_var, 2)
        self.create_status_card(metrics_frame, "Session", self.session_var, 3)

        content_frame = ctk.CTkFrame(main_frame, fg_color="transparent") if ctk else tk.Frame(main_frame, bg="#0b1120")
        content_frame.pack(fill="both", expand=True)
        content_frame.columnconfigure(0, weight=5)
        content_frame.columnconfigure(1, weight=2)
        content_frame.rowconfigure(0, weight=1)

        left_panel = ctk.CTkFrame(content_frame, fg_color="transparent") if ctk else tk.Frame(content_frame, bg="#0b1120")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_panel.rowconfigure(0, weight=1)
        left_panel.columnconfigure(0, weight=1)

        video_group = ctk.CTkFrame(left_panel, corner_radius=18, fg_color="#111827") if ctk else tk.Frame(left_panel, bg="#111827")
        video_group.grid(row=0, column=0, sticky="nsew")
        video_group.rowconfigure(1, weight=1)
        video_group.columnconfigure(0, weight=1)
        if ctk:
            ctk.CTkLabel(video_group, text="Vue caméra", text_color="#93c5fd", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))

        self.video_label = tk.Label(video_group, text="Démarre la caméra pour afficher le flux", bg="#020617", fg="#cbd5e1", font=("Segoe UI", 12, "bold"), relief="flat", bd=0, highlightthickness=0)
        self.video_label.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        details_group = ctk.CTkFrame(left_panel, corner_radius=18, fg_color="#111827") if ctk else tk.Frame(left_panel, bg="#111827")
        details_group.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        if ctk:
            ctk.CTkLabel(details_group, text="Informations en direct", text_color="#93c5fd", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(10, 4))
            for variable in (
                self.mode_var,
                self.profile_var,
                self.time_var,
                self.faces_var,
                self.human_var,
                self.detail_var,
                self.schedule_var,
                self.motion_var,
                self.recording_var,
                self.telegram_var,
                self.fullscreen_var,
            ):
                ctk.CTkLabel(details_group, textvariable=variable, text_color="#e5e7eb", anchor="w", justify="left", wraplength=700).pack(anchor="w", padx=12, pady=2)
        else:
            tk.Label(details_group, text="Informations en direct", bg="#111827", fg="#93c5fd", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(10, 4))
            for variable in (
                self.mode_var,
                self.profile_var,
                self.time_var,
                self.faces_var,
                self.human_var,
                self.detail_var,
                self.schedule_var,
                self.motion_var,
                self.recording_var,
                self.telegram_var,
                self.fullscreen_var,
            ):
                tk.Label(details_group, textvariable=variable, bg="#111827", fg="#e5e7eb", anchor="w", justify="left", wraplength=700).pack(anchor="w", padx=12, pady=2)

        right_panel = ctk.CTkFrame(content_frame, fg_color="transparent") if ctk else tk.Frame(content_frame, bg="#0b1120")
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.rowconfigure(1, weight=1)
        right_panel.columnconfigure(0, weight=1)

        controls_group = ctk.CTkFrame(right_panel, corner_radius=18, fg_color="#111827") if ctk else tk.Frame(right_panel, bg="#111827")
        controls_group.grid(row=0, column=0, sticky="ew")
        controls_group.columnconfigure(0, weight=1)
        controls_group.columnconfigure(1, weight=1)
        if ctk:
            ctk.CTkLabel(controls_group, text="Actions rapides", text_color="#93c5fd", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 4))
            ctk.CTkLabel(controls_group, text="Caméra active", text_color="#e5e7eb").grid(row=1, column=0, columnspan=2, sticky="w", padx=12)
            self.camera_combo = ctk.CTkComboBox(controls_group, variable=self.camera_var, values=[str(self.config.camera_index)], command=lambda _=None: self.change_camera())
            self.camera_combo.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 8))
        else:
            self.camera_combo = ttk.Combobox(controls_group, textvariable=self.camera_var, state="readonly")
            self.camera_combo.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 8))
            self.camera_combo.bind("<<ComboboxSelected>>", self.change_camera)

        buttons = [
            ("↻ Actualiser", self.refresh_camera_list, "#334155"),
            ("▶ Démarrer", self.start_surveillance, "#2563eb"),
            ("■ Arrêter", self.stop_surveillance, "#dc2626"),
            ("📸 Capture", self.manual_snapshot, "#0f766e"),
            ("👤 Recharger", self.reload_faces, "#334155"),
            ("➕ Ajouter", self.save_pending_unknown_face, "#0f766e"),
            ("📄 Rapport", self.export_report, "#334155"),
            ("⚙ Windows", self.install_startup_shortcut, "#334155"),
            ("🖥 Plein écran", self.toggle_fullscreen, "#2563eb"),
            ("🌐 Dashboard", self.launch_dashboard, "#2563eb"),
            ("✕ Quitter", self.on_close, "#dc2626"),
        ]
        for idx, (label, command, color) in enumerate(buttons):
            row = 3 + (idx // 2)
            column = idx % 2
            self.create_action_button(controls_group, label, command, row, column, color)

        self.tabview = ctk.CTkTabview(right_panel, corner_radius=18, fg_color="#111827", segmented_button_fg_color="#0f172a") if ctk else ttk.Notebook(right_panel)
        self.tabview.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

        if ctk:
            surveillance_tab = self.tabview.add("Surveillance")
            history_tab = self.tabview.add("Historique")
            settings_tab = self.tabview.add("Paramètres")

            info_lines = [
                "• reconnaissance faciale locale",
                "• détection IA de présence humaine",
                "• détection de mouvement suspect affinée",
                "• enregistrement vidéo automatique",
                "• horaires + mode nuit",
                "• support multi-caméras",
                f"• dashboard: {build_dashboard_url(self.config)}",
            ]
            ctk.CTkLabel(surveillance_tab, text="Vue d’ensemble", text_color="#93c5fd", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(10, 6))
            ctk.CTkLabel(surveillance_tab, text="\n".join(info_lines), justify="left", text_color="#e5e7eb").pack(anchor="w", padx=12, pady=(0, 10))
            for variable in (self.mode_var, self.profile_var, self.time_var, self.faces_var, self.human_var, self.detail_var, self.fullscreen_var):
                ctk.CTkLabel(surveillance_tab, textvariable=variable, text_color="#cbd5e1", justify="left", wraplength=360).pack(anchor="w", padx=12, pady=(0, 6))

            top_history = ctk.CTkFrame(history_tab, fg_color="transparent")
            top_history.pack(fill="x", padx=10, pady=(10, 6))
            ctk.CTkButton(top_history, text="↻ Actualiser historique", command=self.refresh_history_views, height=34).pack(side="left")

            ctk.CTkLabel(history_tab, text="Historique alertes & détections", text_color="#93c5fd", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(0, 4))
            self.history_box = ScrolledText(history_tab, height=10, wrap=tk.WORD, state="disabled", bg="#020617", fg="#e2e8f0", insertbackground="#f8fafc", selectbackground="#2563eb", relief="flat", font=("Consolas", 10))
            self.history_box.pack(fill="both", expand=False, padx=12, pady=(0, 10))

            ctk.CTkLabel(history_tab, text="Journal en direct", text_color="#93c5fd", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(0, 4))
            self.log_box = ScrolledText(history_tab, height=12, wrap=tk.WORD, state="disabled", bg="#020617", fg="#e2e8f0", insertbackground="#f8fafc", selectbackground="#2563eb", relief="flat", font=("Consolas", 10))
            self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

            ctk.CTkLabel(settings_tab, text="Paramètres & conseils", text_color="#93c5fd", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(10, 6))
            self.settings_box = ScrolledText(settings_tab, height=18, wrap=tk.WORD, state="disabled", bg="#020617", fg="#e2e8f0", insertbackground="#f8fafc", selectbackground="#2563eb", relief="flat", font=("Consolas", 10))
            self.settings_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        else:
            logs_group = tk.Frame(right_panel, bg="#111827")
            logs_group.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
            self.log_box = ScrolledText(logs_group, height=16, wrap=tk.WORD, state="disabled", bg="#020617", fg="#e2e8f0", insertbackground="#f8fafc", selectbackground="#2563eb", relief="flat", font=("Consolas", 10))
            self.log_box.pack(fill="both", expand=True, padx=12, pady=12)

        self.root.bind("<F11>", lambda _event: self.toggle_fullscreen())
        self.root.bind("<Escape>", lambda _event: self.exit_fullscreen())

        self.refresh_camera_list(initial=True)
        self.refresh_history_views()

    def toggle_fullscreen(self) -> None:
        is_fullscreen = bool(self.root.attributes("-fullscreen"))
        self.root.attributes("-fullscreen", not is_fullscreen)
        self.fullscreen_var.set("Mode plein écran" if not is_fullscreen else "Mode fenêtre")
        self.session_var.set("Plein écran activé" if not is_fullscreen else "Retour au mode fenêtre")

    def exit_fullscreen(self) -> None:
        self.root.attributes("-fullscreen", False)
        self.fullscreen_var.set("Mode fenêtre")

    def set_text_widget(self, widget, text: str) -> None:
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.configure(state="disabled")

    def refresh_history_views(self) -> None:
        alerts = load_csv_rows(self.config.alerts_log)[-8:]
        detections = load_csv_rows(self.config.detections_log)[-10:]
        alert_lines = [
            f"- {row.get('timestamp', '-')} | {row.get('reason', '-')} | {row.get('faces_detected', 'aucun')}"
            for row in reversed(alerts)
        ] or ["Aucune alerte récente."]
        detection_lines = [
            f"- {row.get('timestamp', '-')} | {row.get('name', '-')} | {row.get('status', '-')} | {row.get('confidence', '-')}%"
            for row in reversed(detections)
        ] or ["Aucune détection récente."]
        history_text = "Dernières alertes\n" + "\n".join(alert_lines) + "\n\nDernières détections\n" + "\n".join(detection_lines)
        self.set_text_widget(self.history_box, history_text)
        self.refresh_settings_view()

    def refresh_settings_view(self) -> None:
        settings_text = (
            f"camera_index = {self.config.camera_index}\n"
            f"tolerance = {self.config.tolerance}\n"
            f"surveillance = {self.config.surveillance_start_time} -> {self.config.surveillance_end_time}\n"
            f"mode_nuit = {self.config.night_start_time} -> {self.config.night_end_time}\n"
            f"dashboard = {build_dashboard_url(self.config)}\n"
            f"telegram = {'activé' if self.config.telegram_enabled else 'désactivé'}\n"
            f"ia_humain = {'activée' if self.config.person_detection_enabled else 'désactivée'}\n"
            f"alerte_motion_humaine = {'requise' if self.config.require_human_for_motion_alert else 'optionnelle'}\n"
            f"dossier_visages = {self.config.faces_dir}\n"
            f"dossier_alertes = {self.config.alerts_dir}\n"
            f"dossier_captures = {self.config.captures_dir}\n\n"
            "Conseils rapides\n"
            "- utilise plusieurs photos par personne\n"
            "- baisse `tolerance` pour être plus strict\n"
            "- ajuste les horaires dans `config.json`\n"
            "- utilise le dashboard pour suivre les alertes\n"
            "- F11 active le plein écran, Échap le quitte\n"
        )
        self.set_text_widget(self.settings_box, settings_text)

    def log_message(self, message: str) -> None:
        stamped = f"[{timestamp_label()}] {message}"
        LOGGER.info(message)
        self.session_var.set(message)
        if self.log_box is not None:
            self.log_box.configure(state="normal")
            self.log_box.insert(tk.END, stamped + "\n")
            self.log_box.see(tk.END)
            self.log_box.configure(state="disabled")
        self.refresh_history_views()

    def require_admin_access(self, reason: str = "cette action") -> bool:
        if not self.config.admin_password:
            return True
        password = simpledialog.askstring("Accès administrateur", f"Mot de passe requis pour {reason} :", show="*", parent=self.root)
        if password == self.config.admin_password:
            return True
        messagebox.showerror("Accès refusé", "Mot de passe administrateur incorrect.")
        return False

    def refresh_camera_list(self, initial: bool = False) -> None:
        self.available_cameras = list_available_cameras(self.config.max_camera_index)
        if not self.available_cameras:
            self.available_cameras = [self.config.camera_index]

        values = [str(index) for index in self.available_cameras]
        if ctk and hasattr(self.camera_combo, "configure"):
            self.camera_combo.configure(values=values)
        else:
            self.camera_combo["values"] = values

        if self.camera_var.get() not in values:
            self.camera_var.set(str(self.available_cameras[0]))

        if not initial:
            self.log_message(f"Caméras détectées : {', '.join(values)}")

    def change_camera(self, _event=None) -> None:
        try:
            selected_index = int(self.camera_var.get())
        except ValueError:
            return

        if selected_index == self.config.camera_index:
            return

        was_running = self.running
        if was_running:
            self.stop_surveillance()

        self.config.camera_index = selected_index
        self.detail_var.set(f"Caméra sélectionnée : index {selected_index}")
        self.log_message(f"Caméra changée vers l'index {selected_index}.")

        if was_running:
            self.root.after(250, self.start_surveillance)

    def start_surveillance(self) -> None:
        if self.running:
            self.log_message("La caméra est déjà active.")
            return

        self.capture = cv2.VideoCapture(self.config.camera_index)
        if not self.capture.isOpened():
            self.capture = None
            self.status_var.set("Erreur caméra")
            self.detail_var.set("Impossible d'ouvrir la caméra. Vérifie camera_index dans config.json.")
            messagebox.showerror("Caméra", "Impossible d'ouvrir la caméra.")
            return

        self.running = True
        self.previous_gray = None
        self.frame_index = 0
        self.status_var.set("Surveillance active")
        self.mode_var.set("Mode: surveillance active")
        self.human_var.set("IA humain: analyse en cours")
        self.detail_var.set("Caméra connectée et analyse en cours.")
        self.log_message("Surveillance démarrée.")
        self.update_loop()

    def stop_surveillance(self, show_popup: bool = False) -> None:
        self.running = False
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        self.stop_recording()
        self.person_detections = []
        self.status_var.set("Surveillance arrêtée")
        self.mode_var.set("Mode: arrêtée")
        self.profile_var.set("Profil: -")
        self.time_var.set(f"Heure: {timestamp_label()}")
        self.faces_var.set("Visages détectés: aucun")
        self.human_var.set("IA humain: inactif")
        self.detail_var.set("Caméra inactive")
        if show_popup:
            messagebox.showinfo("Caméra", "La caméra a été arrêtée.")

    def reload_faces(self, show_popup: bool = True) -> None:
        self.known_face_encodings, self.known_face_names = load_known_faces(self.config, logger=self.log_message)
        people_count = len(set(self.known_face_names))
        self.people_var.set(f"Base connue: {people_count} personne(s)")
        if show_popup:
            messagebox.showinfo("Visages", f"Base rechargée : {people_count} personne(s) connue(s).")

    def manual_snapshot(self) -> None:
        if self.current_frame is None:
            messagebox.showinfo("Capture", "Aucune image disponible pour le moment.")
            return
        snapshot_path = save_snapshot(self.current_frame, self.config.captures_dir, "manual")
        self.log_message(f"Capture manuelle enregistrée : {snapshot_path}")
        self.status_var.set("Capture enregistrée")

    def export_report(self) -> None:
        if not self.require_admin_access("exporter un rapport"):
            return
        report_path = generate_html_report(self.config)
        webbrowser.open(Path(report_path).as_uri())
        self.status_var.set(f"Rapport exporté : {Path(report_path).name}")
        self.log_message(f"Rapport HTML généré : {report_path}")

    def install_startup_shortcut(self) -> None:
        if not self.require_admin_access("configurer le démarrage automatique"):
            return

        startup_path = get_startup_bat_path()
        startup_path.parent.mkdir(parents=True, exist_ok=True)

        if startup_path.exists():
            should_remove = messagebox.askyesno("Démarrage Windows", "Le démarrage automatique est déjà installé. Voulez-vous le retirer ?")
            if should_remove:
                startup_path.unlink(missing_ok=True)
                self.status_var.set("Démarrage automatique retiré")
                self.log_message("Démarrage automatique Windows supprimé.")
            return

        app_path = Path(__file__).resolve().parent.parent / "app.py"
        content = f'@echo off\ncd /d "{app_path.parent}"\n"{sys.executable}" "{app_path}"\n'
        startup_path.write_text(content, encoding="utf-8")
        self.status_var.set("Démarrage automatique installé")
        self.log_message(f"Démarrage automatique Windows activé : {startup_path}")
        messagebox.showinfo("Démarrage Windows", "L'application se lancera au démarrage de Windows.")

    def launch_dashboard(self) -> None:
        if not self.require_admin_access("ouvrir le dashboard"):
            return

        script_path = Path(__file__).resolve().parent.parent / "dashboard.py"
        if not script_path.exists():
            messagebox.showerror("Dashboard", "Le fichier dashboard.py est introuvable.")
            return

        if self.dashboard_process is None or self.dashboard_process.poll() is not None:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.dashboard_process = subprocess.Popen([sys.executable, str(script_path)], cwd=str(script_path.parent), creationflags=creationflags)
            self.log_message("Dashboard local lancé.")

        webbrowser.open(build_dashboard_url(self.config))
        self.status_var.set(f"Dashboard ouvert : {build_dashboard_url(self.config)}")

    def is_surveillance_allowed(self) -> bool:
        if not self.config.schedule_enabled:
            return True
        return is_time_in_window(self.config.surveillance_start_time, self.config.surveillance_end_time)

    def is_night_mode_active(self) -> bool:
        if not self.config.night_mode_enabled:
            return False
        return is_time_in_window(self.config.night_start_time, self.config.night_end_time)

    def log_detections(self) -> None:
        now = time.time()
        for face in self.face_results:
            person_key = face["name"]
            if now - self.last_log_times.get(person_key, 0.0) < self.config.detection_log_cooldown_seconds:
                continue
            self.last_log_times[person_key] = now
            append_csv_row(
                self.config.detections_log,
                ["timestamp", "name", "confidence", "status"],
                {
                    "timestamp": timestamp_label(),
                    "name": face["name"],
                    "confidence": f"{face['confidence']:.1f}",
                    "status": "reconnu" if face["name"] != "Inconnu" else "inconnu",
                },
            )

    def maybe_save_unknown_snapshot(self, frame) -> None:
        if not self.config.save_unknown_snapshots:
            return
        if not any(face["name"] == "Inconnu" for face in self.face_results):
            return

        now = time.time()
        if now - self.last_unknown_snapshot < self.config.unknown_snapshot_cooldown_seconds:
            return

        snapshot_path = save_snapshot(frame, self.config.captures_dir, "unknown")
        self.last_unknown_snapshot = now
        self.log_message(f"Capture inconnue enregistrée : {snapshot_path}")

    def start_recording(self, frame) -> str:
        if self.recording_writer is None:
            height, width = frame.shape[:2]
            video_dir = Path(self.config.alerts_dir)
            self.recording_path = str(Path(video_dir) / f"alert_video_{safe_timestamp()}.avi")
            writer = cv2.VideoWriter(self.recording_path, cv2.VideoWriter_fourcc(*"XVID"), float(self.config.video_fps), (width, height))
            if not writer.isOpened():
                self.recording_path = ""
                self.log_message("Impossible de démarrer l'enregistrement vidéo.")
                return ""
            self.recording_writer = writer
            self.log_message(f"Enregistrement vidéo démarré : {self.recording_path}")

        self.recording_until = max(self.recording_until, time.time() + self.config.alert_record_seconds)
        self.recording_var.set(f"Enregistrement: actif ({Path(self.recording_path).name})")
        return self.recording_path

    def stop_recording(self) -> None:
        if self.recording_writer is not None:
            self.recording_writer.release()
            self.recording_writer = None
            self.log_message("Enregistrement vidéo terminé.")
        self.recording_var.set("Enregistrement: inactif")

    def extract_face_crop(self, frame, face: dict):
        top = max(0, int(face["top"]))
        right = min(frame.shape[1], int(face["right"]))
        bottom = min(frame.shape[0], int(face["bottom"]))
        left = max(0, int(face["left"]))
        crop = frame[top:bottom, left:right]
        return crop.copy() if crop.size else None

    def send_alert_notifications(self, reason: str, motion_ratio: float) -> None:
        message = f"🚨 {reason}\nHeure: {timestamp_label()}\nCaméra: {self.config.camera_index}\nMouvement: {motion_ratio * 100:.2f}%"
        success, info = send_telegram_message(self.config, message)
        if self.config.telegram_enabled:
            self.telegram_var.set(info)
            self.log_message(info)
        else:
            self.telegram_var.set("Telegram: inactif")

    def trigger_alert(self, frame, reason: str, motion_ratio: float) -> None:
        snapshot_path = save_snapshot(frame, self.config.alerts_dir, "alert")
        video_path = self.start_recording(frame)
        append_csv_row(
            self.config.alerts_log,
            ["timestamp", "reason", "motion_percent", "faces_detected", "snapshot", "video"],
            {
                "timestamp": timestamp_label(),
                "reason": reason,
                "motion_percent": f"{motion_ratio * 100:.2f}",
                "faces_detected": ", ".join(face["name"] for face in self.face_results) or "aucun",
                "snapshot": snapshot_path,
                "video": video_path,
            },
        )
        alert_beep()
        self.send_alert_notifications(reason, motion_ratio)

    def raise_alert(self, frame, reason: str, motion_ratio: float) -> None:
        if time.time() - self.last_alert_time < self.config.alert_cooldown_seconds and "inconnu" not in reason.lower():
            return

        self.trigger_alert(frame, reason, motion_ratio)
        self.last_alert_time = time.time()
        self.last_alert_message = f"{reason} - {timestamp_label()}"
        self.status_var.set(self.last_alert_message)
        self.alerts_var.set(reason)
        self.log_message(reason)

    def handle_unknown_face(self, frame, motion_ratio: float) -> None:
        unknown_face = next((face for face in self.face_results if face["name"] == "Inconnu"), None)
        if unknown_face is None:
            return
        now = time.time()
        if now - self.last_unknown_alert < self.config.unknown_alert_cooldown_seconds:
            return

        self.last_unknown_alert = now
        self.pending_unknown_crop = self.extract_face_crop(frame, unknown_face)
        self.raise_alert(frame, "Visage inconnu détecté", motion_ratio)

        if self.config.prompt_save_unknown_face and self.pending_unknown_crop is not None and not self.is_prompt_open:
            self.root.after(150, self.prompt_save_unknown_face)

    def prompt_save_unknown_face(self) -> None:
        if self.pending_unknown_crop is None or self.is_prompt_open:
            return
        self.is_prompt_open = True
        try:
            should_save = messagebox.askyesno("Nouveau visage détecté", "Un visage inconnu a été détecté. Voulez-vous l'enregistrer dans la base ?")
            if should_save:
                self.save_pending_unknown_face()
        finally:
            self.is_prompt_open = False

    def save_pending_unknown_face(self) -> None:
        if self.pending_unknown_crop is None:
            messagebox.showinfo("Enregistrer visage", "Aucun visage inconnu récent n'est disponible.")
            return
        if not self.require_admin_access("enregistrer un nouveau visage"):
            return

        person_name = simpledialog.askstring("Nom du visage", "Nom de cette personne :", parent=self.root)
        if not person_name:
            return

        safe_name = sanitize_name(person_name)
        person_folder = resolve_project_path(self.config.faces_dir) / safe_name
        person_folder.mkdir(parents=True, exist_ok=True)
        file_path = person_folder / f"{safe_name}_{safe_timestamp()}.jpg"
        cv2.imwrite(str(file_path), self.pending_unknown_crop)

        self.pending_unknown_crop = None
        self.reload_faces(show_popup=False)
        self.status_var.set(f"Visage ajouté : {safe_name}")
        self.log_message(f"Nouveau visage enregistré : {file_path}")
        messagebox.showinfo("Visage ajouté", f"Le visage a été enregistré pour : {safe_name}")

    def update_loop(self) -> None:
        if not self.running or self.capture is None:
            return

        ret, frame = self.capture.read()
        if not ret:
            self.status_var.set("Erreur lecture caméra")
            self.detail_var.set("Impossible de lire le flux vidéo.")
            self.log_message("Erreur de lecture de la caméra.")
            self.stop_surveillance()
            return

        self.current_frame = frame.copy()
        self.frame_index += 1

        schedule_active = self.is_surveillance_allowed()
        night_mode = self.is_night_mode_active()
        motion_threshold = self.config.night_motion_ratio_threshold if night_mode else self.config.motion_ratio_threshold
        suspicious_threshold = self.config.night_suspicious_motion_ratio if night_mode else self.config.suspicious_motion_ratio

        motion_ratio, motion_boxes, self.previous_gray = detect_motion(frame, self.previous_gray, self.config)
        if self.config.person_detection_enabled and self.frame_index % max(1, self.config.person_detection_every_n_frames) == 0:
            self.person_detections = detect_people(frame, self.config)

        human_present = bool(self.person_detections) or bool(self.face_results)
        human_count = max(len(self.person_detections), len(self.face_results))

        self.time_var.set(f"Heure: {timestamp_label()}")
        self.profile_var.set(f"Profil: {'nuit' if night_mode else 'jour'}")
        self.motion_var.set(f"Mouvement: {motion_ratio * 100:.2f}%")
        self.human_var.set(f"IA humain: {'détecté' if human_present else 'non détecté'} ({human_count})")

        suspicious = False
        if schedule_active:
            motion_detected = motion_ratio >= motion_threshold
            self.motion_streak = self.motion_streak + 1 if motion_detected else 0

            if self.frame_index % max(1, self.config.process_every_n_frames) == 0:
                self.face_results = recognize_faces(frame, self.known_face_encodings, self.known_face_names, self.config)
                self.log_detections()
                self.maybe_save_unknown_snapshot(frame)
                self.handle_unknown_face(frame, motion_ratio)

            people_count = len(set(self.known_face_names))
            detected_names = ", ".join(face["name"] for face in self.face_results) if self.face_results else "aucun"
            self.people_var.set(f"Base connue: {people_count} personne(s) | Détectés: {len(self.face_results)}")
            self.faces_var.set(f"Visages détectés: {detected_names}")

            unknown_present = any(face["name"] == "Inconnu" for face in self.face_results)
            suspicious, suspicious_reason = evaluate_suspicious_activity(
                motion_streak=self.motion_streak,
                motion_ratio=motion_ratio,
                suspicious_threshold=suspicious_threshold,
                unknown_present=unknown_present,
                human_present=human_present,
                config=self.config,
            )

            if suspicious and suspicious_reason and "inconnu" not in suspicious_reason.lower():
                self.raise_alert(frame, suspicious_reason, motion_ratio)
            elif time.time() - self.last_alert_time > 4:
                self.last_alert_message = ""

            current_mode = "ALERTE IA" if suspicious else "SURVEILLANCE"
            mode_label = "Mode nuit" if night_mode else "Mode jour"
            self.mode_var.set(f"Mode: {current_mode}")
            self.schedule_var.set(f"Horaires actifs | {mode_label} | {self.config.surveillance_start_time}-{self.config.surveillance_end_time}")
            self.detail_var.set("Analyse faciale, mouvement et présence humaine en cours")
        else:
            self.face_results = []
            self.motion_streak = 0
            self.last_alert_message = "Surveillance en pause (hors horaires)"
            self.mode_var.set("Mode: hors horaires")
            self.faces_var.set("Visages détectés: aucun")
            self.schedule_var.set(f"Pause planning | Actif entre {self.config.surveillance_start_time} et {self.config.surveillance_end_time}")
            self.detail_var.set("Flux caméra actif, détection suspendue par horaires")

        display_frame = frame.copy()
        draw_overlay(display_frame, self.face_results, motion_boxes, motion_ratio, suspicious, self.motion_streak, len(set(self.known_face_names)), self.last_alert_message, schedule_active, night_mode, self.recording_writer is not None, self.config)

        if self.recording_writer is not None:
            self.recording_writer.write(display_frame)
            if time.time() >= self.recording_until:
                self.stop_recording()

        rgb_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        target_width = max(1040, self.video_label.winfo_width())
        target_height = max(680, self.video_label.winfo_height())
        photo = create_preview_image(rgb_frame, target_width, target_height)
        self.video_label.configure(image=photo, text="")
        self.video_label.image = photo

        self.root.after(30, self.update_loop)

    def on_close(self) -> None:
        self.stop_surveillance()
        if self.dashboard_process is not None and self.dashboard_process.poll() is None:
            self.dashboard_process.terminate()
        self.root.destroy()


def main() -> None:
    setup_logging()
    LOGGER.info("Démarrage de l'application de surveillance")
    root = ctk.CTk() if ctk is not None else tk.Tk()
    app = SurveillanceGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
