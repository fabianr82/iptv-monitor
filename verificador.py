import requests
import sys
import time
from typing import List, Tuple

# ====== Consola/Logs en UTF-8 (Windows) ======
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ====== CONFIGURACIÓN ======
destinatarios = [
    {"telefono": "+573007975452", "apikey": "8887083"},
    {"telefono": "+573208095251", "apikey": "7893471"},
    {"telefono": "+573174374244", "apikey": "2890771"},
]

# Fuente de la lista M3U desde hosting o GitHub
ruta_archivo = "https://freshcampo.com.co/public/aaprueba/Lista25.m3u"

# Archivo local donde se guarda el resumen
ruta_resumen = r"C:\Users\Fabian\Desktop\IPTV\Lista Canales\Canales_Caidos.txt"

# Cabeceras para probar streams IPTV (más compatibles)
HEADERS_STREAM = {
    "User-Agent": "VLC/3.0.18 LibVLC/3.0.18",
    "Accept": "*/*",
    "Connection": "keep-alive",
    "Range": "bytes=0-1024",
}


# ====== FUNCIONES ======
def cargar_m3u(ruta: str) -> List[Tuple[str, str]]:
    """Carga lista M3U desde URL o archivo local."""
    if ruta.lower().startswith(("http://", "https://")):
        resp_head = requests.head(ruta, timeout=15, allow_redirects=True)
        resp_head.raise_for_status()
        resp = requests.get(ruta, timeout=30)
        resp.raise_for_status()
        lineas = resp.content.decode("latin-1", errors="ignore").splitlines()
    else:
        with open(ruta, "r", encoding="latin-1", errors="ignore") as f:
            lineas = f.readlines()

    canales = []
    for i in range(len(lineas)):
        if lineas[i].startswith("#EXTINF"):
            nombre = lineas[i].strip().split(",")[-1]
            if i + 1 < len(lineas):
                url = lineas[i + 1].strip()
                if url:
                    canales.append((nombre, url))
    return canales


def verificar_canal(nombre: str, url: str, timeout: int = 6) -> bool:
    """
    Verifica si un canal IPTV está activo.
    Soporta URLs tipo:
      - /play/a00z
      - /user/pass/streamid.ts
    """
    try:
        # Primer intento: HEAD rápido
        r = requests.head(url, headers=HEADERS_STREAM, timeout=timeout, allow_redirects=True)
        if 200 <= r.status_code < 400:
            return True

        # Segundo intento: GET parcial (por si el servidor no soporta HEAD)
        r = requests.get(url, headers=HEADERS_STREAM, timeout=timeout, stream=True)
        if r.status_code == 200:
            return True

        print(f"   ⚠ {nombre} respondió código {r.status_code}")
        return False

    except requests.exceptions.Timeout:
        print(f"   ⏱ Tiempo agotado verificando {nombre}")
        return False
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Sin conexión al servidor ({url})")
        return False
    except requests.exceptions.RequestException as e:
        print(f"   ⚠ Error verificando {nombre}: {e}")
        return False


def enviar_whatsapp(mensaje: str) -> None:
    """Envía el mismo mensaje a todos los destinatarios vía CallMeBot."""
    mensaje_encoded = requests.utils.quote(mensaje)
    for d in destinatarios:
        telefono = d["telefono"]
        apikey = d["apikey"]
        url = (
            f"https://api.callmebot.com/whatsapp.php?phone={telefono}"
            f"&text={mensaje_encoded}&apikey={apikey}"
        )
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                print(f"📲 Mensaje enviado a {telefono}.")
            else:
                print(f"⚠ Error enviando a {telefono}: {r.status_code} - {r.text}")
            time.sleep(2)
        except Exception as e:
            print(f"⚠ Excepción al enviar a {telefono}: {e}")


def monitorear_lista(ruta: str) -> None:
    print("🔎 Verificando canales...\n")

    # Verificar que la lista remota esté disponible
    if ruta.lower().startswith(("http://", "https://")):
        try:
            resp = requests.head(ruta, timeout=15, allow_redirects=True)
            if not resp.ok:
                enviar_whatsapp(f"⚠️ No se pudo acceder a la lista M3U: {ruta}")
                return
        except Exception as e:
            enviar_whatsapp(f"⚠️ Error accediendo a la lista M3U: {e}")
            return

    try:
        canales = cargar_m3u(ruta)
    except Exception as e:
        msg = f"⚠️ No pude cargar la M3U ({e}). Revisa la URL o el hosting."
        print(msg)
        enviar_whatsapp(msg)
        return

    total = len(canales)
    activos = 0
    caidos = 0
    lista_caidos: List[Tuple[str, str]] = []

    for idx, (nombre, url) in enumerate(canales, start=1):
        print(f"[{idx}/{total}] Verificando: {nombre}")
        if verificar_canal(nombre, url):
            print(f"✅ ACTIVO: {nombre}")
            activos += 1
        else:
            print(f"❌ CAÍDO: {nombre}")
            caidos += 1
            lista_caidos.append((nombre, url))

    print("\n✅ Verificación completada")
    print(f"✔ Canales activos: {activos}")
    print(f"❌ Canales caídos: {caidos}")

    # Crear resumen TXT
    mensaje_whatsapp = f"📺 Reporte IPTV\n✅ Activos: {activos}\n❌ Caídos: {caidos}"
    with open(ruta_resumen, "w", encoding="utf-8") as f:
        if lista_caidos:
            f.write("🛑 RESUMEN DE CANALES CAÍDOS\n\n")
            mensaje_whatsapp += "\n📄 Lista Caídos:\n"
            for nombre, url in lista_caidos:
                f.write(f"❌ {nombre} → {url}\n")
                mensaje_whatsapp += f"- {nombre}\n"
        else:
            f.write("✅ Todos los canales están activos\n")

    print(f"\n📄 Resumen también guardado en: {ruta_resumen}")
    enviar_whatsapp(mensaje_whatsapp)


# ====== ENTRYPOINT ======
if __name__ == "__main__":
    try:
        monitorear_lista(ruta_archivo)
    except KeyboardInterrupt:
        print("\n⛔ Verificación interrumpida por el usuario.")
