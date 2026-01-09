import requests
from urllib.parse import urlparse, parse_qs
import time
from datetime import datetime
from dotenv import load_dotenv
import os
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

URL_PRODUCTO = "https://clevercel.mx/products/iphone-13?variant=45475249422492"
INTERVALO_MINUTOS = 60

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

ultimo_check = {"timestamp": None, "status": "iniciando"}

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Handler simple para responder health checks de Fly.io"""
    def do_GET(self):
        if self.path == "/" or self.path == "/health":
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            mensaje = f"OK - Última revisión: {ultimo_check['timestamp']} - Status: {ultimo_check['status']}"
            self.wfile.write(mensaje.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass

def iniciar_servidor_http():
    """Inicia un servidor HTTP simple en el puerto 8080"""
    port = int(os.getenv('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"Servidor HTTP iniciado en puerto {port}")
    server.serve_forever()

def enviar_telegram(mensaje: str):
    """Envía un mensaje de texto a tu cuenta de Telegram usando un bot."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Telegram no configurado, no se envía mensaje.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": mensaje
    }
    try:
        resp = requests.post(url, data=data, timeout=10)
        resp.raise_for_status()
        print("Notificación enviada por Telegram.")
    except Exception as e:
        print("Error al enviar notificación de Telegram:", e)


def disponibilidad_variant_shopify(product_url: str):
    """Consulta el JSON público de Shopify para un producto y regresa info de la variante indicada en ?variant=..."""
    product_url = product_url.strip()

    parsed = urlparse(product_url)
    path_parts = parsed.path.strip("/").split("/")
    try:
        products_index = path_parts.index("products")
        handle = path_parts[products_index + 1]
    except (ValueError, IndexError):
        raise ValueError("No pude encontrar el handle del producto en la URL")

    query = parse_qs(parsed.query)
    if "variant" not in query:
        raise ValueError("La URL no tiene parámetro ?variant=...")

    variant_id_str = query["variant"][0]
    try:
        variant_id = int(variant_id_str)
    except ValueError:
        raise ValueError("El variant_id no es un número válido")

    json_url = f"{parsed.scheme}://{parsed.netloc}/products/{handle}.js"

    try:
        resp = requests.get(json_url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print("Error de red al pedir el JSON:", e)
        return None

    try:
        data = resp.json()
    except ValueError:
        print("No se pudo decodificar el JSON de Shopify.")
        return None

    for v in data.get("variants", []):
        if v.get("id") == variant_id:
            titulo = v.get("title")
            disponible = v.get("available", False)
            return {
                "variant_id": variant_id,
                "title": titulo,
                "available": disponible,
            }

    return None


def monitor_stock():
    """Función que ejecuta el monitoreo de stock en loop"""
    global ultimo_check
    
    print("Iniciando monitor de stock para:")
    print(URL_PRODUCTO)
    print(f"Revisión cada {INTERVALO_MINUTOS} minutos.\n")

    while True:
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ahora}] Revisando variante...")
        ultimo_check["timestamp"] = ahora

        info = disponibilidad_variant_shopify(URL_PRODUCTO)

        if info is None:
            print("No encontré información de esa variante (o hubo error).")
            ultimo_check["status"] = "error"
        else:
            print(f"Variante: {info['title']} (ID {info['variant_id']})")

            nombre_producto = "iPhone 13"
            color_variante = info['title'].split(' / ')[-1] 

            if info["available"]:
                mensaje = (
                    f"¡La variante {nombre_producto} ({color_variante}) está DISPONIBLE!\n\n"
                    f"ID: {info['variant_id']}\n"
                    f"URL: {URL_PRODUCTO}"
                )
                ultimo_check["status"] = "disponible"
            else:
                mensaje = (
                    f"La variante {nombre_producto} ({color_variante}) sigue AGOTADA\n\n"
                    f"ID: {info['variant_id']}\n"
                    f"URL: {URL_PRODUCTO}"
                )
                ultimo_check["status"] = "agotado"

            enviar_telegram(mensaje)

        print(f"Esperando {INTERVALO_MINUTOS} minutos para la siguiente revisión...\n")
        time.sleep(INTERVALO_MINUTOS * 60)


def main():
    http_thread = Thread(target=iniciar_servidor_http, daemon=True)
    http_thread.start()
    
    time.sleep(2)
    
    monitor_stock()


if __name__ == "__main__":
    main()
