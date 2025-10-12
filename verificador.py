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
# Destinatarios con API key propia
destinatarios = [
    {"telefono": "+573007975452", "apikey": "8887083"},     # ✅ activo
    {"telefono": "+573208095251", "apikey": "7893471"},
    {"telefono": "+573174374244", "apikey": "2890771"},
]

# Fuente de la M3U (URL pública en Hostinger)
ruta_archivo = "https://freshcampo.com.co/public/aaprueba/Lista25.m3u"

# Dónde guardar el TXT de resumen (local en tu PC/servidor)
ruta_resumen = r"C:\Users\Fabian\Desktop\IPTV\Lista Canales\Canales_Caidos.txt"

# User-Agent "tipo reproductor" para probar streams
HEADERS_STREAM = {"User-Agent": "VLC/3.0.11 LibVLC/3.0.11"}


# ====== UTILIDADES ======
def cargar_m3u(ruta: str) -> List[Tuple[str, str]]:
    """
    Carga una lista M3U desde URL (http/https) o desde ruta local.
    Devuelve lista de (nombre, url).
    """
    if ruta.lower().startswith(("http://", "https://")):
        # Comprobación rápida de disponibilidad
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
                if url:  # evitar líneas vacías
                    canales.append((nombre, url))
    return canales


def verificar_canal(nombre: str, url: str, timeout: int = 3) -> bool:
    try:
        r = requests.get(url, headers=HEADERS_STREAM, timeout=timeout, stream=False)
        return r.status_code == 200
    except requests.exceptions.RequestException as e:
        print(f"   ⚠ Error verificando {nombre}: {e}")
        return False


def enviar_whatsapp(mensaje: str) -> None:
    """
    Envía el mismo mensaje a todos los destinatarios.
    Muestra diagnóstico si CallMeBot devuelve error (p.ej. 203 o APIKey inválida).
    """
    mensaje_encoded = requests.utils.quote(mensaje)
    for d in destinatarios:
        telefono = d["telefono"]
        apikey = d["apikey"]
        url = (
            "https://api.callmebot.com/whatsapp.php"
            f"?phone={telefono}&text={mensaje_encoded}&apikey={apikey}"
        )
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                print(f"📲 Mensaje enviado a {telefono}.")
            else:
                print(f"⚠ Error enviando a {telefono}: {r.status_code} - {r.text}")
            time.sleep(2)  # pequeña pausa para evitar rate limit
        except Exception as e:
            print(f"⚠ Excepción al enviar a {telefono}: {e}")


# ====== LÓGICA PRINCIPAL ======
def monitorear_lista(ruta: str) -> None:
    print("🔎 Verificando canales...\n")

    # 🔔 Alerta si la URL no responde (HEAD no OK) y salir
    if ruta.lower().startswith(("http://", "https://")) and not requests.head(
        ruta, timeout=15, allow_redirects=True
    ).ok:
        enviar_whatsapp(f"⚠️ No pude acceder a la lista M3U: {ruta}")
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

    mensaje_whatsapp = f"📺 Reporte IPTV\n✅ Activos: {activos}\n❌ Caídos: {caidos}"

    if lista_caidos:
        mensaje_whatsapp += "\n📄 Lista Caídos:\n"
        with open(ruta_resumen, "w", encoding="utf-8") as f:
            f.write("🛑 RESUMEN DE CANALES CAÍDOS\n\n")
            for nombre, url in lista_caidos:
                f.write(f"❌ {nombre} → {url}\n")
                mensaje_whatsapp += f"- {nombre}: {url}\n"
    else:
        with open(ruta_resumen, "w", encoding="utf-8") as f:
            f.write("✅ Todos los canales están activos\n")

    print(f"\n📄 Resumen también guardado en: {ruta_resumen}")
    enviar_whatsapp(mensaje_whatsapp)


# ====== ENTRYPOINT ======
if __name__ == "__main__":
    try:
        monitorear_lista(ruta_archivo)
    except KeyboardInterrupt:
        print("\n⛔ Verificación interrumpida por el usuario.")
