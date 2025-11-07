# check_iptv.py
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
# Fallback: si no defines RECIPIENTS_JSON en Secrets, usa esto (puedes editarlo localmente)
DEFAULT_DESTINATARIOS = [
    {"telefono": "+573007975452", "apikey": "8887083"},
    {"telefono": "+573208095251", "apikey": "7893471"},
    {"telefono": "+573174374244", "apikey": "2890771"},
]

# La URL/ruta de la M3U la puedes pasar por ENV M3U_URL (recomendado).
M3U_RUTA = os.environ.get("M3U_URL", "https://freshcampo.com.co/public/aaprueba/Lista25.m3u")

# Archivo local donde se guardará el resumen dentro del workspace de Actions
RUTA_RESUMEN = os.environ.get("RUTA_RESUMEN", "Canales_Caidos.txt")

# Cabeceras para probar streams IPTV (compatibles)
HEADERS_STREAM = {
    "User-Agent": "VLC/3.0.18 LibVLC/3.0.18",
    "Accept": "*/*",
    "Connection": "keep-alive",
    "Range": "bytes=0-1024",
}

# ====== UTILIDADES ======
def obtener_destinatarios() -> List[dict]:
    """Toma destinatarios de la variable RECIPIENTS_JSON (JSON) o usa el fallback."""
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
            print(f"⚠ Error parseando RECIPIENTS_JSON: {e}. Usando fallback.")
    print("ℹ Usando destinatarios por defecto (hardcoded).")
    return DEFAULT_DESTINATARIOS


def cargar_m3u(ruta: str) -> List[Tuple[str, str]]:
    """Carga lista M3U desde URL o archivo local."""
    print(f"🔁 Cargando M3U desde: {ruta}")
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
    print(f"🔢 Canales encontrados: {len(canales)}")
    return canales


def verificar_canal(nombre: str, url: str, timeout: int = 6) -> bool:
    """Verifica si un canal IPTV está activo (HEAD -> GET parcial)."""
    try:
        # Primer intento: HEAD
        r = requests.head(url, headers=HEADERS_STREAM, timeout=timeout, allow_redirects=True)
        if 200 <= r.status_code < 400:
            print(f"   → HEAD OK ({r.status_code})")
            return True

        # Segundo intento: GET parcial (stream)
        r = requests.get(url, headers=HEADERS_STREAM, timeout=timeout, stream=True)
        if r.status_code == 200:
            # opcional: leer un pequeño chunk para confirmar data
            try:
                chunk = next(r.iter_content(chunk_size=1024), b"")
                if chunk:
                    print("   → GET parcial OK (data recibida)")
                    return True
                else:
                    print("   → GET parcial OK (sin bytes recibidos aún)")
                    return True
            except Exception:
                return True

        print(f"   ⚠ Respuesta inesperada: {r.status_code}")
        return False

    except requests.exceptions.Timeout:
        print("   ⏱ Timeout")
        return False
    except requests.exceptions.ConnectionError:
        print("   ❌ ConnectionError")
        return False
    except requests.exceptions.RequestException as e:
        print(f"   ⚠ RequestException: {e}")
        return False


def enviar_whatsapp(mensaje: str, destinatarios: List[dict]) -> None:
    """Envía el mensaje a todos los destinatarios vía CallMeBot (diagnósticos incluidos)."""
    mensaje_encoded = requests.utils.quote(mensaje)
    for d in destinatarios:
        telefono = d.get("telefono")
        apikey = d.get("apikey")
        if not telefono or not apikey:
            print(f"   ⚠ Destinatario inválido: {d}")
            continue
        url = f"https://api.callmebot.com/whatsapp.php?phone={telefono}&text={mensaje_encoded}&apikey={apikey}"
        print(f"📤 Intentando enviar a {telefono} -> {url}")
        try:
            r = requests.get(url, timeout=20)
            print(f"📩 Respuesta: {r.status_code} | {r.text[:200]}")
            if r.status_code == 200:
                print(f"✅ Mensaje enviado a {telefono}")
            else:
                print(f"⚠ Error al enviar a {telefono}: {r.status_code}")
        except Exception as e:
            print(f"⚠ Excepción enviando a {telefono}: {e}")
        time.sleep(2)


# ====== LÓGICA PRINCIPAL ======
def monitorear_lista(ruta: str) -> None:
    destinatarios = obtener_destinatarios()
    print("🔎 Verificando canales...\n")

    # chequeo rápido de disponibilidad de M3U
    if ruta.lower().startswith(("http://", "https://")):
        try:
            resp = requests.head(ruta, timeout=15, allow_redirects=True)
            if not resp.ok:
                print("❌ La M3U no está disponible (HEAD fallo).")
                enviar_whatsapp(f"⚠️ No pude acceder a la lista M3U: {ruta}", destinatarios)
                return
        except Exception as e:
            print(f"❌ Error accediendo a la M3U: {e}")
            enviar_whatsapp(f"⚠️ No pude acceder a la lista M3U: {e}", destinatarios)
            return

    try:
        canales = cargar_m3u(ruta)
    except Exception as e:
        msg = f"⚠️ No pude cargar la M3U ({e})."
        print(msg)
        enviar_whatsapp(msg, destinatarios)
        return

    total = len(canales)
    activos = 0
    caidos = 0
    lista_caidos: List[Tuple[str, str]] = []

    for idx, (nombre, url) in enumerate(canales, start=1):
        print(f"[{idx}/{total}] Verificando: {nombre} -> {url}")
        ok = verificar_canal(nombre, url)
        if ok:
            print(f"✅ ACTIVO: {nombre}")
            activos += 1
        else:
            print(f"❌ CAÍDO: {nombre}")
            caidos += 1
            lista_caidos.append((nombre, url))

    print("\n✅ Verificación completada")
    print(f"✔ Canales activos: {activos}")
    print(f"❌ Canales caídos: {caidos}")

    # crear output.txt (artifact)
    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(f"Activos: {activos}\nCaídos: {caidos}\n\n")
        for nombre, url in lista_caidos:
            f.write(f"{nombre} → {url}\n")

    # guardar resumen humano en RUTA_RESUMEN (opcional)
    with open(RUTA_RESUMEN, "w", encoding="utf-8") as f:
        if lista_caidos:
            f.write("🛑 RESUMEN DE CANALES CAÍDOS\n\n")
            for nombre, url in lista_caidos:
                f.write(f"❌ {nombre} → {url}\n")
        else:
            f.write("✅ Todos los canales están activos\n")

    # preparar mensaje whatsapp (breve)
    mensaje_whatsapp = f"📺 Reporte IPTV\n✅ Activos: {activos}\n❌ Caídos: {caidos}"
    if lista_caidos:
        mensaje_whatsapp += "\n📄 Revisa output.txt en artifacts."

    # intento de envío (puede fallar desde GitHub si bloquean)
    enviar_whatsapp(mensaje_whatsapp, destinatarios)
    print("📄 Output guardado: output.txt y", RUTA_RESUMEN)


if __name__ == "__main__":
    try:
        monitorear_lista(M3U_RUTA)
    except KeyboardInterrupt:
        print("\n⛔ Interrumpido por el usuario.")
