import logging
import requests
import html
import os

logger = logging.getLogger(__name__)

_ESTADO_LABELS = {
    "confirmada": "✅ Confirmada",
    "anunciada": "📣 Anunciada",
    "en_evaluacion": "🔍 En evaluación",
}

_ESTADO_EMOJI = {
    "confirmada": "🏗️",
    "anunciada": "📢",
    "en_evaluacion": "🔎",
}

_MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

def _formatear_monto(monto_usd: int) -> str:
    """Convierte un entero a texto compacto, ej: USD 40M."""
    if monto_usd >= 1_000_000_000:
        valor = monto_usd / 1_000_000_000
        texto = f"{valor:.1f}".rstrip("0").rstrip(".")
        return f"USD {texto}B"
    if monto_usd >= 1_000_000:
        valor = monto_usd / 1_000_000
        texto = f"{valor:.1f}".rstrip("0").rstrip(".")
        return f"USD {texto}M"
    return f"USD {monto_usd:,}".replace(",", ".")

def _formatear_fecha(fecha_str: str) -> str:
    """Intenta parsear 'YYYY-MM-DD' a 'DD de mes de YYYY'."""
    if not fecha_str:
        return "Fecha no disponible"
    try:
        anio, mes, dia = str(fecha_str).split("-")
        return f"{int(dia)} de {_MESES_ES[int(mes) - 1]} de {anio}"
    except Exception:
        return str(fecha_str)

def enviar_inversion_a_telegram(inversion: dict):
    """
    Envía la información de la inversión al canal de Telegram configurado usando parse_mode="HTML".
    Maneja silenciosamente excepciones para no romper el main thread.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    
    if not token or not channel_id:
        logger.warning("TELEGRAM_BOT_TOKEN o TELEGRAM_CHANNEL_ID no están configurados. Se omite envío a Telegram.")
        return

    estado_raw = inversion.get("estado", "")
    empresa = html.escape(str(inversion.get("empresa", "Inversión Desconocida")))
    descripcion = html.escape(str(inversion.get("descripcion", "Sin descripción")))
    
    monto = inversion.get("monto_usd")
    ubicacion = inversion.get("ubicacion")
    empleos = inversion.get("empleos")
    fecha_raw = inversion.get("fecha_anuncio")
    
    emoji_cabecera = _ESTADO_EMOJI.get(estado_raw, "📌")
    
    # Manejo del label de estado (fallback en caso de estado inválido)
    fallback_estado = html.escape(estado_raw.replace('_', ' ').capitalize() if estado_raw else "No especificado")
    estado_label = _ESTADO_LABELS.get(estado_raw, fallback_estado)
    
    fecha_legible = _formatear_fecha(fecha_raw)

    lineas = [
        f"{emoji_cabecera} <b>{empresa}</b>",
        "",
        descripcion,
    ]

    detalles = []
    if monto is not None and isinstance(monto, (int, float)):
        detalles.append(f"💰 <b>{_formatear_monto(int(monto))}</b>")
    if ubicacion:
        detalles.append(f"📍 {html.escape(str(ubicacion))}")
    if empleos is not None and isinstance(empleos, (int, float)):
        detalles.append(f"👥 {int(empleos):,} empleos directos".replace(",", "."))
        
    if detalles:
        lineas.append("")
        lineas.extend(detalles)
        
    lineas.append("")
    lineas.extend([
        f"📋 {estado_label}",
        f"📅 {html.escape(fecha_legible)}"
    ])

    mensaje = "\n".join(lineas)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": channel_id,
        "text": mensaje,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True}
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        # Parseo opcional si el error es en JSON antes de largar excepción HTTP
        data = response.json() if response.ok or response.status_code == 400 else {}
        
        response.raise_for_status()
        
        if data and not data.get("ok"):
            logger.error(f"    Telegram API devolvió error para '{empresa}': {data.get('description')}")
        else:
            logger.info(f"    Inversión '{empresa}' enviada a Telegram exitosamente.")
            
    except requests.exceptions.RequestException as e:
         logger.error(f"    Fallo al enviar la inversión '{empresa}' a Telegram: {e}")
    except Exception as e:
        logger.error(f"    Error inesperado al notificar a Telegram para '{empresa}': {e}")
