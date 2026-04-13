
import pyautogui
import pygetwindow as gw
import time
import json
import os
import sys
import atexit
import signal
import urllib.request
from datetime import datetime
from PIL import ImageGrab, Image
import pytesseract
import firebase_admin
from firebase_admin import credentials, db as admin_db

# ─────────────────────────────────────────────
#  COLORES TERMINAL
# ─────────────────────────────────────────────

class Colors:
    RESET      = "\033[0m"
    GREEN      = "\033[32m"
    YELLOW     = "\033[33m"
    CYAN       = "\033[36m"
    RED        = "\033[31m"
    GRAY       = "\033[90m"

if sys.platform == "win32":
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)
    except:
        pass

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────

WINDOW_TITLE         = "any-FLOW Job Manager"
CHECK_INTERVAL_SEC   = 10                  # Enviar estado a Firebase cada 10 s
MAX_RESETS_PER_HOUR  = 10
LOG_FILE             = "watchdog_log.json"
WAIT_AFTER_RESET_SEC = 10

RESET_BUTTON_IMAGES  = ["reset_button.png", "reset_button_alt.png"]
BUTTON_CONFIDENCE    = 0.8

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Estados conocidos 
KNOWN_STATES = ["FAULT", "SERVICING", "PRIMED_IDLE"]

# ─────────────────────────────────────────────
#  FIREBASE
# ─────────────────────────────────────────────

FIREBASE_URL = "https://monitor-maquina-22b37-default-rtdb.firebaseio.com"

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://monitor-maquina-22b37-default-rtdb.firebaseio.com"
})

def firebase_put(path: str, data: dict):
    """Sobreescribe un nodo (PUT)."""
    try:
        admin_db.reference(path).set(data)
    except Exception as e:
        print(f"{Colors.RED}[Firebase] PUT {path}: {e}{Colors.RESET}")

def firebase_post(path: str, data: dict):
    """Agrega con ID único (POST)."""
    try:
        admin_db.reference(path).push(data)
    except Exception as e:
        print(f"{Colors.RED}[Firebase] POST {path}: {e}{Colors.RESET}")

def push_current(state: str):
    """Actualiza current_status cada 10 segundos con el estado leído."""
    firebase_put("current_status", {
        "state":      state,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

def push_history(state: str):
    """Agrega al historial solo cuando cambia el estado."""
    firebase_post("history", {
        "state":     state,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

def push_reset(reset_num: int, success: bool):
    """Registra evento RESET en historial y last_reset."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    firebase_put("last_reset", {
        "reset_number": reset_num,
        "success":      success,
        "timestamp":    now
    })
    firebase_post("history", {
        "state":     "RESET",
        "reset_num": reset_num,
        "success":   success,
        "timestamp": now
    })

# ─────────────────────────────────────────────
#  CIERRE LIMPIO 
# ─────────────────────────────────────────────

_shutdown_sent = False   # evitar doble envío

def push_shutdown():
    """Envía estado WATCHDOG_DETENIDO a Firebase al cerrar el programa."""
    global _shutdown_sent
    if _shutdown_sent:
        return
    _shutdown_sent = True
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        firebase_put("current_status", {
            "state":      "PROGRAMA_APAGADO",
            "updated_at": now
        })
        firebase_post("history", {
            "state":     "PROGRAMA_APAGADO",
            "timestamp": now
        })
        print(f"{Colors.RED}[{now}] Watchdog cerrado — estado enviado a Firebase{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}[Firebase] No se pudo registrar cierre: {e}{Colors.RESET}")

# Handler para win32: captura la X, Ctrl+C, cierre de sesión, etc.
try:
    import win32api

    def _win32_handler(event):
        push_shutdown()
        return False   # False = Windows sigue con el cierre normal

    win32api.SetConsoleCtrlHandler(_win32_handler, True)
except ImportError:
    # win32api no disponible — fallback con atexit + signal
    atexit.register(push_shutdown)
    signal.signal(signal.SIGTERM, lambda s, f: (push_shutdown(), sys.exit(0)))
    try:
        signal.signal(signal.SIGBREAK, lambda s, f: (push_shutdown(), sys.exit(0)))
    except AttributeError:
        pass
# ─────────────────────────────────────────────
#  LOGGER LOCAL (JSON)
# ─────────────────────────────────────────────

def log(event_type: str, message: str, state: str = ""):
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type":      event_type,
        "state":     state,
        "message":   message
    }
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except:
            logs = []
    logs.append(entry)
    if len(logs) > 5000:
        logs = logs[-5000:]
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)

    symbols = {
        "INFO": "✅", "FAULT": "⚠️ ", "RESET": "🔄",
        "WARNING": "🔔", "ERROR": "❌", "SERVICING": "🔧", "PRIMED_IDLE": "🟢"
    }
    print(f"[{entry['timestamp']}] {symbols.get(event_type,'  ')} {message}")

# ─────────────────────────────────────────────
#  VENTANA
# ─────────────────────────────────────────────

def get_printer_window():
    wins = gw.getWindowsWithTitle(WINDOW_TITLE)
    return wins[0] if wins else None

# ─────────────────────────────────────────────
#  CLICK RESET
# ─────────────────────────────────────────────

def click_reset(window) -> bool:
    existing = [img for img in RESET_BUTTON_IMAGES if os.path.exists(img)]
    if not existing:
        log("ERROR", f"No se encuentran imágenes de Reset: {RESET_BUTTON_IMAGES}")
        return False
    try:
        window.activate(); time.sleep(0.5)
    except Exception as e:
        log("ERROR", f"No se pudo activar ventana: {e}"); return False

    for img in existing:
        log("INFO", f"Buscando Reset: {img}")
        try:
            loc = pyautogui.locateOnScreen(
                img, confidence=BUTTON_CONFIDENCE,
                region=(window.left, window.top, window.width, window.height)
            )
            if not loc:
                loc = pyautogui.locateOnScreen(img, confidence=BUTTON_CONFIDENCE)
            if loc:
                cx = loc.left + loc.width  // 2
                cy = loc.top  + loc.height // 2
                pyautogui.moveTo(cx, cy, duration=0.3)
                pyautogui.click(); time.sleep(0.5)
                log("INFO", f"Reset clickeado en ({cx}, {cy})")
                return True
            log("WARNING", f"No encontrado con '{img}'")
        except Exception as e:
            log("ERROR", f"Error con '{img}': {e}")

    log("ERROR", "No se encontró botón Reset")
    return False

# ─────────────────────────────────────────────
#  OCR — extraer SYSTEM STATE
# ─────────────────────────────────────────────

def get_system_state(window) -> str:
    """
    Lee el área de System State y devuelve la palabra de estado
    tal como aparece (FAULT, SERVICING, PRIMED_IDLE, o lo que sea).
    """
    try:
        wx, wy, ww, wh = window.left, window.top, window.width, window.height
        x1, y1 = wx + int(ww * 0.65), wy + int(wh * 0.15)
        x2, y2 = wx + ww,             wy + int(wh * 0.30)

        shot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        w, h = shot.size
        shot = shot.resize((w * 3, h * 3), Image.LANCZOS)

        raw   = pytesseract.image_to_string(shot, config="--psm 6")
        lines = raw.upper().strip().split('\n')

        # Buscar primero palabras clave conocidas en todo el texto
        full_text = ' '.join(lines)
        for state in KNOWN_STATES:
            if state in full_text.split():
                return state

        # Si no encontró palabra clave, extraer lo que viene después de SYSTEM STATE
        system_state_found = False
        for line in lines:
            if 'SYSTEM STATE' in line:
                system_state_found = True
                after = line.split('SYSTEM STATE')[-1].strip().lstrip(':').strip()
                if after:
                    return after.split()[0] if after.split() else after

        # Si nunca apareció "SYSTEM STATE" significa que la ventana esta oculta, minimizada o tapada
        if not system_state_found:
            return "PRINTER-INFO_OCULTO"

        # Fallback: primera línea no vacía
        for line in lines:
            if line.strip():
                return line.strip().split()[0]

        return "UNKNOWN"

    except Exception as e:
        log("ERROR", f"Fallo OCR: {e}")
        return "UNKNOWN"

# ─────────────────────────────────────────────
#  DEPENDENCIAS
# ─────────────────────────────────────────────

def check_dependencies():
    issues = []
    try:
        import cv2
    except ImportError:
        issues.append("❌ opencv-python no instalado: pip install opencv-python")

    existing = [img for img in RESET_BUTTON_IMAGES if os.path.exists(img)]
    if not existing:
        issues.append(f"❌ No se encuentran imágenes de Reset: {RESET_BUTTON_IMAGES}")
    else:
        print(f"✅ Imágenes: {', '.join(existing)}")

    if not os.path.exists(pytesseract.pytesseract.tesseract_cmd):
        issues.append(f"❌ Tesseract no encontrado en {pytesseract.pytesseract.tesseract_cmd}")

    if issues:
        print("\n".join(issues))
        return False
    return True

# ─────────────────────────────────────────────
#  LOOP PRINCIPAL
# ─────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  any-FLOW Watchdog — INICIADO")
    print(f"  Intervalo: {CHECK_INTERVAL_SEC}s | Max resets/hora: {MAX_RESETS_PER_HOUR}")
    print(f"  Firebase: {FIREBASE_URL}")
    print(f"  Log local: {os.path.abspath(LOG_FILE)}")
    print("  Ctrl+C para detener")
    print("=" * 55)

    if not check_dependencies():
        log("ERROR", "Faltan dependencias.")
        input("Presiona Enter para salir...")
        sys.exit(1)

    resets_this_hour = 0
    hour_mark        = datetime.now().hour
    last_state       = None  # último estado enviado al historial

    while True:
        try:
            if datetime.now().hour != hour_mark:
                hour_mark        = datetime.now().hour
                resets_this_hour = 0

            window = get_printer_window()
            if not window:
                log("WARNING", f"Ventana '{WINDOW_TITLE}' no encontrada")
                time.sleep(CHECK_INTERVAL_SEC)
                continue

            # 1. Leer estado OCR
            state = get_system_state(window)

            # 2. Mostrar en consola con color
            color = {
                "FAULT":          Colors.YELLOW,
                "SERVICING":      Colors.CYAN,
                "PRIMED_IDLE":    Colors.GREEN,
                "MONITOR_OCULTO": Colors.RED,
            }.get(state, Colors.GRAY)
            print(f"{color}[{datetime.now().strftime('%H:%M:%S')}] {state}{Colors.RESET}")

            # 3. Siempre actualizar current_status en Firebase (cada 10s)
            push_current(state)

            # 4. Historial solo si cambió el estado
            if state != last_state:
                push_history(state)
                log(state if state in KNOWN_STATES else "INFO",
                    f"Cambio de estado: {last_state} → {state}", state)
                last_state = state

            # 5. Ejecutar RESET si hay FAULT
            if state == "FAULT":
                if resets_this_hour >= MAX_RESETS_PER_HOUR:
                    log("WARNING", f"{resets_this_hour} resets esta hora — revisión manual.")
                    time.sleep(CHECK_INTERVAL_SEC)
                    continue

                log("RESET", f"Presionando RESET (#{resets_this_hour + 1} esta hora)...")
                success = click_reset(window)
                push_reset(resets_this_hour + 1, success)

                if success:
                    resets_this_hour += 1
                    log("RESET", "RESET ejecutado correctamente")
                    time.sleep(WAIT_AFTER_RESET_SEC)
                else:
                    log("ERROR", "No se pudo hacer clic en RESET.")

            time.sleep(CHECK_INTERVAL_SEC)

        except KeyboardInterrupt:
            log("INFO", "Watchdog detenido manualmente.")
            print("\n  Watchdog detenido")
            sys.exit(0)

        except Exception as e:
            log("ERROR", f"Error en loop: {e}")
            time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
    
#By Cesarbj11