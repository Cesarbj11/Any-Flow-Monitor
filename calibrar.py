# calibrar_imagen.py - Script único para capturar el botón Reset, este script solo se ejecuta una vez para calibrar la imagen del botón Reset. Luego, el watchdog.py usará esta imagen para detectar el botón en la pantalla.
import pyautogui
import pygetwindow as gw
import time

WINDOW_TITLE = "any-FLOW Job Manager"

print("=" * 50)
print("  CAPTURADOR DE BOTÓN RESET")
print("=" * 50)
print()

# Buscar ventana
windows = gw.getWindowsWithTitle(WINDOW_TITLE)
if not windows:
    print(f"❌ Ventana '{WINDOW_TITLE}' no encontrada.")
    input("Presiona Enter para salir...")
    exit()

win = windows[0]
win.activate()
time.sleep(1)

print("✅ Ventana encontrada. Ahora:")
print("1. Mueve el mouse encima del botón RESET")
print("2. Espera 3 segundos después de posicionarlo")
print("3. Se capturará automáticamente el botón")
print()

input("Presiona Enter cuando estés listo...")

# Dar tiempo para posicionar el mouse
for i in range(3, 0, -1):
    print(f"Capturando en {i}...")
    time.sleep(1)

# Capturar área alrededor del mouse
x, y = pyautogui.position()
capture_size = 80  # Capturar 80x80 píxeles alrededor del mouse

left = x - capture_size // 2
top = y - capture_size // 2
right = x + capture_size // 2
bottom = y + capture_size // 2

screenshot = pyautogui.screenshot(region=(left, top, capture_size, capture_size))
screenshot.save("reset_button.png")

print(f"\n✅ Botón capturado y guardado como 'reset_button.png'")
print(f"   Ubicación: {left}, {top} (tamaño: {capture_size}x{capture_size})")
print("\nYa puedes ejecutar el watchdog actualizado.")