"""
PPE Detector Module
Runs YOLOv8 + ByteTrack object tracking and person-PPE association in a
background thread, generating annotated frames for MJPEG live streaming,
calculating compliance KPIs, managing alert debouncing, ROI zones, and saving snapshots.
"""

import os
import sys
import time
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# Root project directory
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# Color Palette (BGR)
COLOR_SAFE = (76, 175, 80)       # Green
COLOR_DANGER = (54, 67, 244)     # Red (BGR: 54, 67, 244)
COLOR_WARN = (38, 166, 254)      # Orange/Yellow
COLOR_PERSON = (212, 188, 0)     # Cyan/Blue
COLOR_ZONE = (255, 140, 0)       # Deep sky blue boundary


class PPEDetector:
    PPE_ITEMS = ["Hardhat", "Safety Vest", "Gloves", "Mask"]
    NO_PPE_MAP = {
        "NO-Hardhat": "Hardhat",
        "NO-Safety Vest": "Safety Vest",
        "NO-Mask": "Mask",
    }
    CLASS_NAMES = [
        'Excavator', 'Gloves', 'Hardhat', 'Ladder', 'Mask', 'NO-Hardhat', 'NO-Mask', 'NO-Safety Vest',
        'Person', 'SUV', 'Safety Cone', 'Safety Vest', 'bus', 'dump truck', 'fire hydrant', 'machinery',
        'mini-van', 'sedan', 'semi', 'trailer', 'truck and trailer', 'truck', 'van', 'vehicle', 'wheel loader'
    ]

    def __init__(self, model_path: str = "best.pt", tracker_cfg: str = "bytetrack.yaml"):
        self.model_path = model_path
        self.tracker_cfg = tracker_cfg
        self.model = None

        # Threading & Control
        self._thread = None
        self._running = False
        self._run_id = 0
        self.cap = None
        self._track_remap: Dict[int, int] = {}
        self._lock = threading.Lock()
        self._frame_lock = threading.Lock()

        # Frame Cache for MJPEG
        self.current_frame = None
        self.current_jpeg = None

        # Source & Configuration
        self.source = 0  # 0 or file path or rtsp
        self.camera_name = "Default Camera"
        self.camera_id = 1
        self.confidence_threshold = 0.25
        self.alert_cooldown = 30  # seconds
        self.polygon_roi: Optional[List[Tuple[int, int]]] = None

        # State tracking (matching GUI_W.py)
        self.person_states: Dict[int, dict] = {}
        self.last_alert_time: Dict[Tuple[int, str], float] = {}

        # Real-time Metrics
        self.metrics = {
            "active_workers": 0,
            "wearing": {k: 0 for k in self.PPE_ITEMS},
            "not_wearing": {k: 0 for k in ["Hardhat", "Safety Vest", "Mask"]},
            "compliance_rate": 100.0,
            "fps": 0.0,
            "is_running": False,
            "source_display": "Webcam (0)",
        }

        # Recent violations cache for SSE
        self.recent_violations: List[dict] = []
        self._smoothed_compliance: Optional[float] = 100.0
        self._app_context_callback = None

        # Stream viewer & camera auto-release tracking
        self._active_stream_viewers = 0
        self._last_viewer_disconnect_time = 0.0

        # Anti-false-alarm filters & warmup grace period
        self.WARMUP_SECONDS = 4.0
        self.CONSECUTIVE_FRAMES_REQUIRED = 8
        self._detection_start_time = 0.0
        self._violation_consecutive_counts: Dict[Tuple[int, str], int] = {}

    def set_app_context_callback(self, callback):
        """Pass a callback function that returns Flask app context."""
        self._app_context_callback = callback

    def _ensure_model(self):
        """Lazy load YOLO model to optimize startup time."""
        if self.model is None:
            from ultralytics import YOLO
            resolved_path = Path(self.model_path)
            if not resolved_path.is_absolute():
                resolved_path = ROOT_DIR / resolved_path
            print(f"[*] Loading YOLOv8 model from {resolved_path}...")
            self.model = YOLO(str(resolved_path))
            print("[+] Model loaded successfully.")

    @staticmethod
    def box_center(x1, y1, x2, y2):
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @staticmethod
    def point_in_box(px, py, bx1, by1, bx2, by2):
        return bx1 <= px <= bx2 and by1 <= py <= by2

    def associate_to_person(self, ppe_box, people_boxes):
        """
        Associates detected PPE/NO-PPE bounding box with closest person,
        reusing logic from GUI_W.py.
        """
        x1, y1, x2, y2 = ppe_box
        cx, cy = self.box_center(x1, y1, x2, y2)
        best_tid, best_area = None, None
        for tid, (px1, py1, px2, py2) in people_boxes.items():
            if self.point_in_box(cx, cy, px1, py1, px2, py2):
                area = (px2 - px1) * (py2 - py1)
                if best_area is None or area < best_area:
                    best_area = area
                    best_tid = tid
        return best_tid

    def is_inside_roi(self, cx, cy) -> bool:
        """Checks if point (cx, cy) is inside configured polygon ROI."""
        if not self.polygon_roi or len(self.polygon_roi) < 3:
            return True
        pts = np.array(self.polygon_roi, dtype=np.int32)
        dist = cv2.pointPolygonTest(pts, (float(cx), float(cy)), False)
        return dist >= 0

    def compute_unique_counts(self):
        """Reuses compute_unique_counts from GUI_W.py."""
        wearing = {k: 0 for k in self.PPE_ITEMS}
        not_wearing = {k: 0 for k in self.PPE_ITEMS if k != "Gloves"}
        for st in self.person_states.values():
            for i in self.PPE_ITEMS:
                if st["ppe"].get(i, False):
                    wearing[i] += 1
            for i in not_wearing.keys():
                if st["no"].get(i, False):
                    not_wearing[i] += 1
        return wearing, not_wearing

    def _trigger_violation(self, track_id: int, violation_type: str, conf: float, frame_copy):
        """
        Handles debounce, database logging, snapshot saving, and real-time events.
        Suppresses false alerts during the initial warmup stabilization window.
        """
        now = time.time()
        # Suppress alerts during camera startup / warmup window
        if (now - self._detection_start_time) < self.WARMUP_SECONDS:
            return

        key = (track_id, violation_type)
        last_time = self.last_alert_time.get(key, 0)

        # Check alert cooldown / debouncing
        if now - last_time < self.alert_cooldown:
            return

        self.last_alert_time[key] = now

        # Save snapshot image
        snapshots_dir = ROOT_DIR / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        filename = f"viol_t{track_id}_{violation_type.lower().replace(' ', '_')}_{int(now)}.jpg"
        filepath = snapshots_dir / filename
        cv2.imwrite(str(filepath), frame_copy)
        rel_path = f"snapshots/{filename}"

        violation_payload = {
            "track_id": track_id,
            "violation_type": violation_type,
            "camera": self.camera_name,
            "snapshot_path": rel_path,
            "confidence": round(conf, 2),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Add to live queue for UI updates
        with self._lock:
            self.recent_violations.insert(0, violation_payload)
            if len(self.recent_violations) > 50:
                self.recent_violations.pop()

        # Database logging in background thread
        def _persist_and_alert():
            try:
                if self._app_context_callback:
                    with self._app_context_callback():
                        from app.models.violation import Violation
                        from app.extensions import db

                        v = Violation(
                            track_id=track_id,
                            violation_type=violation_type,
                            camera=self.camera_name,
                            snapshot_path=rel_path,
                            confidence=conf,
                        )
                        db.session.add(v)
                        db.session.commit()
                        print(f"[+] Saved violation #{v.id}: {violation_type} (Track {track_id})")
            except Exception as ex:
                print(f"[!] Error recording violation: {ex}")

        threading.Thread(target=_persist_and_alert, daemon=True).start()

    def start(self, source=None, camera_name=None, camera_id=None, roi=None):
        """Starts the detection thread."""
        with self._lock:
            # Stop any previous capture and wait for release
            self.stop()

            self._run_id += 1
            current_run_id = self._run_id

            if source is not None:
                self.source = source
            if camera_name is not None:
                self.camera_name = camera_name
            if camera_id is not None:
                self.camera_id = camera_id
            if roi is not None:
                self.polygon_roi = roi

            self.person_states.clear()
            self._track_remap.clear()
            self._violation_consecutive_counts.clear()
            self._smoothed_compliance = 100.0
            self._detection_start_time = time.time()
            self._running = True
            self.metrics["is_running"] = True
            self.metrics["compliance_rate"] = 100.0
            self.metrics["source_display"] = str(self.source)

            self._thread = threading.Thread(
                target=self._run_loop,
                args=(current_run_id,),
                daemon=True,
                name=f"DetectorThread-{current_run_id}"
            )
            self._thread.start()
            print(f"[+] Detection started on source: {self.source} (run #{current_run_id})")

    def stop(self):
        """Stops the detection thread gracefully and completely releases hardware."""
        self._running = False
        if hasattr(self, 'cap') and self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        if self._thread and self._thread.is_alive():
            if threading.current_thread() != self._thread:
                self._thread.join(timeout=1.5)
            self._thread = None

        self.metrics["is_running"] = False
        with self._frame_lock:
            self.current_jpeg = None
            self.current_frame = None
        print("[+] Detection stopped and camera hardware released.")

    def is_running(self) -> bool:
        return self._running

    def _run_loop(self, run_id: int):
        """Background detection worker running YOLOv8 tracking."""
        if self._run_id != run_id:
            return

        try:
            self._ensure_model()
        except Exception as e:
            print(f"[!] Failed to load model: {e}")
            if self._run_id == run_id:
                self._running = False
                self.metrics["is_running"] = False
            return

        # Prepare source
        src = self.source
        is_numeric = False
        if isinstance(src, int):
            is_numeric = True
        elif isinstance(src, str):
            src_str = src.strip()
            if src_str.isdigit():
                src = int(src_str)
                is_numeric = True
            elif not src_str.startswith("rtsp://") and not os.path.isabs(src_str):
                candidate = ROOT_DIR / src_str
                if candidate.exists():
                    src = str(candidate)

        cap = None
        if is_numeric:
            src_idx = int(src)
            backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if os.name == 'nt' else [cv2.CAP_ANY]
            for backend in backends:
                try:
                    c = cv2.VideoCapture(src_idx, backend)
                    if c.isOpened():
                        cap = c
                        break
                    else:
                        c.release()
                except Exception:
                    pass

            # If not yet opened, retry twice with short delay to allow USB hardware enumeration
            if cap is None or not cap.isOpened():
                for retry in range(2):
                    time.sleep(0.4)
                    try:
                        c = cv2.VideoCapture(src_idx, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
                        if c.isOpened():
                            cap = c
                            break
                        else:
                            c.release()
                    except Exception:
                        pass
        else:
            cap = cv2.VideoCapture(src)

        # If webcam could not be opened (e.g. cloud server or no physical webcam connected),
        # automatically fall back to sample video (pp2.mp4) so detection works immediately!
        if (cap is None or not cap.isOpened()) and is_numeric:
            for fallback_video in ["pp2.mp4", "ppe.mp4", "ppe-1-1.mp4"]:
                vid_path = ROOT_DIR / fallback_video if not os.path.isabs(fallback_video) else Path(fallback_video)
                if os.path.exists(vid_path):
                    c = cv2.VideoCapture(str(vid_path))
                    if c.isOpened():
                        cap = c
                        src = str(vid_path)
                        is_numeric = False
                        self.camera_name = f"{self.camera_name} (Sample Video Fallback)"
                        print(f"[*] Webcam unavailable on server; fell back to {fallback_video}")
                        break

        if cap is None or not cap.isOpened():
            print(f"[!] Could not open video source: {self.source}")
            standby_frame = np.zeros((480, 720, 3), dtype=np.uint8)
            cv2.putText(standby_frame, f"Camera Source '{self.source}' Offline", (140, 220),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (200, 200, 200), 2)
            cv2.putText(standby_frame, "Please connect a webcam or choose demo video in dropdown", (90, 260),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (130, 130, 130), 1)
            _, buf = cv2.imencode(".jpg", standby_frame)
            if self._run_id == run_id:
                with self._frame_lock:
                    self.current_jpeg = buf.tobytes()
                self._running = False
                self.metrics["is_running"] = False
            return

        self.cap = cap

        if is_numeric:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        prev_time = time.time()

        try:
            while self._running and self._run_id == run_id:
                # Auto-release camera hardware if all browser tabs/viewers closed
                if self._active_stream_viewers == 0 and (time.time() - self._detection_start_time > 8.0):
                    print("[*] No active viewers on stream. Terminating camera capture to release hardware.")
                    break

                success, frame = cap.read()
                if not success:
                    # If reading a file, loop back to start reliably for continuous playback
                    if isinstance(src, str) and os.path.exists(src):
                        cap.release()
                        cap = cv2.VideoCapture(src)
                        self.cap = cap
                        time.sleep(0.03)
                        continue
                    else:
                        time.sleep(0.05)
                        continue

                self._ensure_model()
                model = self.model
                if model is None:
                    time.sleep(0.05)
                    continue

                # Run YOLO tracking with ByteTrack (or fallback to detection if tracker fails)
                try:
                    results = model.track(
                        source=frame,
                        stream=True,
                        persist=True,
                        tracker=self.tracker_cfg,
                        conf=self.confidence_threshold,
                        verbose=False,
                    )
                except Exception:
                    results = model(
                        source=frame,
                        stream=True,
                        conf=self.confidence_threshold,
                        verbose=False,
                    )

                annotated = frame.copy()
                people_boxes = {}
                active_tids = set()

                for result in results:
                    # Draw ROI Polygon if active
                    if self.polygon_roi and len(self.polygon_roi) >= 3:
                        pts = np.array(self.polygon_roi, np.int32).reshape((-1, 1, 2))
                        cv2.polylines(annotated, [pts], isClosed=True, color=COLOR_ZONE, thickness=2)
                        overlay = annotated.copy()
                        cv2.fillPoly(overlay, [pts], (255, 180, 50))
                        cv2.addWeighted(overlay, 0.15, annotated, 0.85, 0, annotated)

                    # 1. Parse Person Boxes
                    res_boxes = getattr(result, "boxes", None)
                    if res_boxes is not None:
                        for b in res_boxes:
                            cls = int(b.cls[0])
                            label = self.CLASS_NAMES[cls] if cls < len(self.CLASS_NAMES) else "Unknown"
                            raw_id = int(b.id[0]) if (b.id is not None) else 1

                            x1, y1, x2, y2 = map(int, b.xyxy[0])
                            conf = float(b.conf[0]) if b.conf is not None else 0.0

                            if label == "Person":
                                cx, cy = self.box_center(x1, y1, x2, y2)
                                if not self.is_inside_roi(cx, cy):
                                    continue

                                # Constant Worker ID mapping (keep worker ID stable and constant)
                                if raw_id not in self._track_remap:
                                    self._track_remap[raw_id] = (len(self._track_remap) % 10) + 1
                                tid = self._track_remap[raw_id]

                                active_tids.add(tid)
                                people_boxes[tid] = (x1, y1, x2, y2)
                                if tid not in self.person_states:
                                    self.person_states[tid] = {
                                        "ppe": {k: False for k in self.PPE_ITEMS},
                                        "no": {k: False for k in ["Hardhat", "Safety Vest", "Mask"]},
                                    }

                                # Draw worker box
                                cv2.rectangle(annotated, (x1, y1), (x2, y2), COLOR_PERSON, 2)
                                cv2.putText(annotated, f"Worker #{tid} ({conf:.2f})", (x1, max(20, y1 - 8)),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_PERSON, 2)

                    # 2. Parse PPE and Non-Compliance detections
                    if res_boxes is not None:
                        for b in res_boxes:
                            cls = int(b.cls[0])
                            label = self.CLASS_NAMES[cls] if cls < len(self.CLASS_NAMES) else "Unknown"
                            if label not in self.PPE_ITEMS and label not in self.NO_PPE_MAP:
                                continue

                            x1, y1, x2, y2 = map(int, b.xyxy[0])
                            conf = float(b.conf[0]) if b.conf is not None else 0.0
                            tid = self.associate_to_person((x1, y1, x2, y2), people_boxes)

                            if tid is not None and tid in self.person_states:
                                if label in self.PPE_ITEMS:
                                    self.person_states[tid]["ppe"][label] = True
                                    self.person_states[tid]["no"][label] = False
                                    # Reset consecutive violation counter when compliant gear is observed
                                    self._violation_consecutive_counts[(tid, label)] = 0

                                    cv2.rectangle(annotated, (x1, y1), (x2, y2), COLOR_SAFE, 2)
                                    cv2.putText(annotated, f"{label} {conf:.2f}", (x1, max(20, y1 - 6)),
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_SAFE, 2)
                                elif label in self.NO_PPE_MAP:
                                    base = self.NO_PPE_MAP[label]
                                    self.person_states[tid]["no"][base] = True
                                    self.person_states[tid]["ppe"][base] = False

                                    v_key = (tid, base)
                                    cur_count = self._violation_consecutive_counts.get(v_key, 0) + 1
                                    self._violation_consecutive_counts[v_key] = cur_count

                                    cv2.rectangle(annotated, (x1, y1), (x2, y2), COLOR_DANGER, 2)
                                    cv2.putText(annotated, f"NO {base}! {conf:.2f}", (x1, max(20, y1 - 6)),
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_DANGER, 2)

                                    # Trigger violation ONLY after consecutive verification frames and solid confidence
                                    if cur_count >= self.CONSECUTIVE_FRAMES_REQUIRED and conf >= 0.35:
                                        self._trigger_violation(tid, base, conf, frame)

                # Real-time breakdown counts for active visible workers
                current_wearing = {k: 0 for k in self.PPE_ITEMS}
                current_not_wearing = {"Hardhat": 0, "Safety Vest": 0, "Mask": 0}

                total_detected = len(people_boxes)
                if total_detected > 0:
                    for tid in people_boxes.keys():
                        st = self.person_states.get(tid)
                        if st:
                            for item in self.PPE_ITEMS:
                                if st["ppe"].get(item, False):
                                    current_wearing[item] += 1
                            for item in ["Hardhat", "Safety Vest", "Mask"]:
                                if st["no"].get(item, False):
                                    current_not_wearing[item] += 1

                    total_required = total_detected * 3  # Hardhat, Vest, Mask
                    active_viols = sum(current_not_wearing.values())
                    active_viols = min(active_viols, total_required)
                    instant_comp = max(0.0, ((total_required - active_viols) / total_required) * 100.0)
                else:
                    # If no workers are in the frame, hold steady at 100.0%
                    instant_comp = 100.0

                # Exponential Moving Average (EMA) smoothing for rock-solid stability
                if self._smoothed_compliance is None:
                    self._smoothed_compliance = instant_comp
                else:
                    self._smoothed_compliance = 0.90 * self._smoothed_compliance + 0.10 * instant_comp

                comp_rate = max(0.0, min(100.0, round(float(self._smoothed_compliance), 1)))

                # FPS Calculation
                now_t = time.time()
                fps = 1.0 / (now_t - prev_time) if (now_t - prev_time) > 0 else 30.0
                prev_time = now_t

                # Update live metrics dictionary
                with self._lock:
                    self.metrics.update({
                        "active_workers": total_detected,
                        "wearing": current_wearing,
                        "not_wearing": current_not_wearing,
                        "compliance_rate": comp_rate,
                        "fps": round(fps, 1),
                        "is_running": True,
                    })

                # Draw Sleek Live Status HUD on frame
                hud_text = f"Protecto.AI Live | FPS: {fps:.1f} | Workers: {total_detected} | Compliance: {comp_rate:.1f}%"
                cv2.rectangle(annotated, (10, 10), (550, 42), (20, 20, 20), -1)
                cv2.putText(annotated, hud_text, (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

                # Write frame to MJPEG buffer ONLY if run_id is active
                if self._run_id == run_id:
                    success, encoded_jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if success:
                        with self._frame_lock:
                            self.current_frame = annotated
                            self.current_jpeg = encoded_jpeg.tobytes()

                time.sleep(0.02)

        except Exception as err:
            print(f"[!] Error in detector loop: {err}")
        finally:
            if hasattr(self, 'cap') and self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
            if self._run_id == run_id:
                self._running = False
                self.metrics["is_running"] = False
            print(f"[*] Detector loop #{run_id} terminated.")

    def generate_mjpeg_frames(self, demo_mode=False):
        """Generator function yielding multipart MJPEG frames for HTTP stream."""
        placeholder = None
        with self._lock:
            self._active_stream_viewers += 1
            print(f"[+] Client connected to stream. Active viewers: {self._active_stream_viewers}")

        try:
            while True:
                with self._frame_lock:
                    frame_bytes = self.current_jpeg

                if frame_bytes is None:
                    # Generate a sleek placeholder frame if detector hasn't started yet
                    if placeholder is None:
                        blank = np.zeros((480, 720, 3), dtype=np.uint8)
                        title = "Protecto.AI - Stream Standby"
                        subtitle = "Select camera source or click 'Start Detection' to begin"
                        cv2.putText(blank, title, (145, 220),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (140, 140, 140), 2)
                        cv2.putText(blank, subtitle, (110, 260),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 100, 100), 1)
                        _, buf = cv2.imencode(".jpg", blank)
                        placeholder = buf.tobytes()
                    frame_bytes = placeholder

                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
                time.sleep(1.0 if demo_mode else 0.04)
        finally:
            with self._lock:
                self._active_stream_viewers = max(0, self._active_stream_viewers - 1)
                self._last_viewer_disconnect_time = time.time()
                print(f"[-] Client disconnected from stream. Remaining viewers: {self._active_stream_viewers}")
                if self._active_stream_viewers == 0:
                    self.stop()


# Global singleton detector instance
detector = PPEDetector()
