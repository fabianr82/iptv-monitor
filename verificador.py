import requests
import sys
import time
import os
import json
from typing import List, Tuple

# ====== Consola/Logs en UTF-8 (Windows) ======
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ====== CONFIGURACIÓN ======
# Lista de destinatarios en caso de no recibir RECIPIENTS_JSON
DEFAULT_DESTINATARIOS = [
    {"telefono": "+573007975452", "apikey": "1005921"}
]

# CRÍTICO: CAMBIO DE RUTA
# La ruta ahora es local (M3U_FILE = "Lista25.m3u") para usar el archivo subido al repositorio.
M3U_RUTA = os.environ.get("M3U_URL", "Lista25.m3u") 

# Archivo de resumen
RUTA_RESUMEN = os.environ.get("RUTA_RESUMEN", "Canales_Caidos.txt")

# Cabeceras para probar streams IPTV
HEADERS_STREAM = {
    "User-Agent": "VLC/3.0.18 LibVLC/3.0.18",
    "Accept": "*/*",
    "Connection": "keep-alive",
    "Range": "bytes=0-1024",
}


# ====== FUNCIONES ======
def obtener_destinatarios() -> List[dict]:
    """Toma destinatarios desde RECIPIENTS_JSON o usa los configurados en el código."""
    raw = os.environ.get("RECIPIENTS_JSON")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                print("🔐 Destinatarios cargados desde RECIPIENTS_JSON")
                return data
            else:
                print("⚠ RECIPIENTS_JSON no es una lista. Usando fallback.")
        except Exception as e:
            print(f"⚠ Error procesando RECIPIENTS_JSON: {e}. Usando fallback.")

    print("ℹ Usando número/clave definidos en el archivo.")
    return DEFAULT_DESTINATARIOS


def cargar_m3u(ruta: str) -> List[Tuple[str, str]]:
    """Carga la lista M3U desde web o archivo local."""
    print(f"🔁 Cargando M3U desde: {ruta}")

    # Si la ruta comienza con http, intenta descargar (Comportamiento heredado)
    if ruta.lower().startswith(("http://", "https://")):
        resp = requests.get(ruta, timeout=30)
        resp.raise_for_status()
        # Nota: La codificación latin-1 es común en M3U, pero UTF-8 es preferible si es posible.
        lineas = resp.content.decode("latin-1", errors="ignore").splitlines()
    else:
        # AQUÍ SE LEE EL ARCHIVO LOCAL DEL REPOSITORIO
        try:
            with open(ruta, "r", encoding="latin-1", errors="ignore") as f:
                lineas = f.readlines()
        except FileNotFoundError:
            print(f"❌ Error: Archivo local M3U no encontrado en la ruta: {ruta}")
            raise # Lanza el error para que el job falle
            

    canales = []
    for i in range(len(lineas)):
        if lineas[i].startswith("#EXTINF"):
            nombre = lineas[i].strip().split(",")[-1]
            if i + 1 < len(lineas):
                url = lineas[i + 1].strip()
                if url and url.startswith(("http://", "https://")): # Asegurar que es una URL válida
                    canales.append((nombre, url))

    print(f"🔢 Canales encontrados: {len(canales)}")
    return canales


def verificar_canal(nombre: str, url: str, timeout: int = 6) -> bool:
    """Verifica si un canal responde."""
    # Reducción de la prueba de conexión para ahorrar tiempo y recursos
    
    # 1. Intento con HEAD (más rápido, ideal para CDN)
    try:
        r = requests.head(url, headers=HEADERS_STREAM, timeout=timeout, allow_redirects=True)
        if 200 <= r.status_code < 400:
            print(f"   → HEAD OK ({r.status_code})")
            return True
    except requests.exceptions.Timeout:
        print("   ⏱ Timeout (HEAD)")
    except requests.exceptions.ConnectionError:
        print("   ❌ ConnectionError (HEAD)")
    except Exception:
        pass # Ignorar errores en HEAD y probar GET

    # 2. Intento con GET parcial (para verificar contenido de stream)
    try:
        # stream=True y limitando la lectura a un chunk_size=512
        r = requests.get(url, headers=HEADERS_STREAM, timeout=timeout, stream=True)
        
        if 200 <= r.status_code < 400:
            try:
                # Intenta leer un chunk muy pequeño para verificar que el stream esté activo
                chunk = next(r.iter_content(chunk_size=512), b"")
                if chunk:
                    print(f"   → GET parcial OK ({r.status_code}, recibiendo datos)")
                    return True
            except Exception:
                 # Si falla al leer el chunk, pero el estado HTTP es 200, aún lo marcamos como activo
                 return True 
        
        print(f"   ⚠ Código inesperado: {r.status_code}")
        return False

    except requests.exceptions.Timeout:
        print("   ⏱ Timeout (GET)")
        return False
    except requests.exceptions.ConnectionError:
        print("   ❌ ConnectionError (GET)")
        return False
    except Exception as e:
        print(f"   ⚠ Error: {e}")
        return False


def enviar_whatsapp(mensaje: str, destinatarios: List[dict]) -> None:
    """Envía mensaje WhatsApp vía CallMeBot."""
    mensaje_encoded = requests.utils.quote(mensaje)

    for d in destinatarios:
        telefono = d.get("telefono")
        apikey = d.get("apikey")

        if not telefono or not apikey:
            print(f"⚠ Destinatario inválido: {d}")
            continue

        url = (
            f"https://api.callmebot.com/whatsapp.php?"
            f"phone={telefono}&text={mensaje_encoded}&apikey={apikey}"
        )

        print(f"📤 Enviando a {telefono} ...")
        try:
            r = requests.get(url, timeout=20)
            print(f"📩 Respuesta: {r.status_code} | {r.text[:200]}")

            if r.status_code == 200:
                print(f"✅ Mensaje enviado a {telefono}")
            else:
                print(f"⚠ Error al enviar a {telefono}")
        except Exception as e:
            print(f"⚠ Excepción enviando a {telefono}: {e}")

        time.sleep(2)


# ====== PROCESO PRINCIPAL ======
def monitorear_lista(ruta: str) -> None:
    destinatarios = obtener_destinatarios()
    print("🔎 Iniciando verificación...\n")

    # Intento de carga M3U
    try:
        canales = cargar_m3u(ruta)
    except Exception as e:
        msg = f"⚠ No pude cargar la M3U ({e}). Asegúrese de que '{ruta}' exista."
        print(msg)
        enviar_whatsapp(msg, destinatarios)
        return

    total = len(canales)
    activos = 0
    caidos = []
    
    for idx, (nombre, url) in enumerate(canales, start=1):
        print(f"[{idx}/{total}] {nombre}")
        if verificar_canal(nombre, url):
            # Agregar una pequeña pausa para evitar saturar el servidor de streams
            # time.sleep(0.1) 
            print(f"✅ ACTIVO: {nombre}")
            activos += 1
        else:
            print(f"❌ CAÍDO: {nombre}")
            caidos.append((nombre, url))

    # Resumen
    print("\n📊 Resultados")
    print(f"✔ Activos: {activos}")
    print(f"❌ Caídos:  {len(caidos)}")

    # Crear archivos
    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(f"Activos: {activos}\nCaídos: {len(caidos)}\n\n")
        for n, u in caidos:
            f.write(f"{n} → {u}\n")

    with open(RUTA_RESUMEN, "w", encoding="utf-8") as f:
        if caidos:
            f.write("🛑 CANALES CAÍDOS\n\n")
            for n, u in caidos:
                f.write(f"❌ {n} → {u}\n")
        else:
            f.write("✅ Todos los canales están activos\n")

    # ENVÍO DE WHATSAPP MEJORADO (Ajuste solicitado)
    if caidos:
        # Construye la lista detallada de canales caídos incluyendo NOMBRE y URL
        # Se usa un formato multilínea simple para WhatsApp.
        detalle_caidos = "\n" + "\n".join([f"❌ {n} -> {u}" for n, u in caidos])
        
        mensaje = (
            f"🛑 Reporte IPTV (FALLOS)\n"
            f"✔ Activos: {activos}\n"
            f"❌ Caídos: {len(caidos)}\n\n"
            f"-- DETALLE --{detalle_caidos}"
        )
    else:
        # Mensaje simple si todos están activos
        mensaje = f"✅ Reporte IPTV\n✔ Activos: {activos}\n❌ Caídos: {len(caidos)}"


    enviar_whatsapp(mensaje, destinatarios)

    print("📁 Archivo generado: output.txt")
    print("📁 Resumen:", RUTA_RESUMEN)


# ====== EJECUCIÓN ======
if __name__ == "__main__":
    try:
        monitorear_lista(M3U_RUTA)
    except KeyboardInterrupt:
        print("\n⛔ Interrumpido por el usuario.")
