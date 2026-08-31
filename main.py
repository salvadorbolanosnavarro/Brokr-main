from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from limites import exigir_cupo, exigir_sesion
from core.auth import get_user_id_from_token
from core.config import settings
from core.database import call_public_rpc, call_service_rpc, delete_rows, get_public_rows, get_rows, get_service_json, get_service_json_or_empty, patch_rows, patch_rows_ignoring_http_status, patch_rows_no_response, post_rows, upsert_rows
from core.legacy_main_config import legacy_main_settings
from core.legacy_admin import require_legacy_admin as require_admin
from core.telemetry import (_request_modulo, _track_anthropic, _track_gemini_image, _track_groq, track_usage)
from core.user_access import get_user_access_state, get_user_rol
from core.subscriptions import (expire_trial_subscription as _expirar_trial_suscripcion, trial_has_expired as _trial_ya_vencio, trial_max_available as _trial_max_disponible)
from core.stripe import (
    EMPRESA_ASIENTOS_BASE, EMPRESA_ASIENTOS_MAX, EMPRESA_TARIFAS,
    PROMO_CODE_AMPI, STRIPE_PRICE_AMPI, STRIPE_PRICE_PRO,
    STRIPE_PRICE_EMPRESA_ANUAL, STRIPE_PRICE_EMPRESA_EXTRA_ANUAL,
    STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL, STRIPE_PRICE_EMPRESA_MENSUAL,
    STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, TRIAL_MAX_DIAS,
    get_or_create_stripe_customer as _get_or_create_stripe_customer,
    precio_empresa as _precio_empresa, stripe_headers as _stripe_headers,
)
from core.facebook_tokens import facebook_token_state as _fb_estado_token
from core.cache import cache_get, cache_set
from core.contact_import import map_org_agents as _mapa_agentes_org
from core.easybroker import EB_API_KEY, EB_BASE, _EB_LOTE, _EB_PAUSA_LOTE, _eb_get_reintentos, eb_headers, extract_colonia, normalize
from core.easybroker_mapping import _EB_LIMITE_PROPIEDADES, _EB_STATUS_DEFAULT, _EB_STATUS_MAP, _eb_to_brokr
from core.easybroker_migration import set_import_progress as _prog
from core.pdf_design import theme_css_for_pdf
from core.pdf_store import _pdf_store
import httpx
import os
import time
import re
import asyncio
import base64
import uuid as _uuid
import io
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Pillow


from routers.admin_usage import router as admin_usage_router
from routers.account_delete import router as account_delete_router
from routers.avm_legacy import router as avm_legacy_router

from routers.avm_claude import router as avm_claude_router

from routers.avm_websearch import router as avm_websearch_router

from core.facebook_tokens import FACEBOOK_REQUIRED_SCOPES
from routers.facebook_connection_read import router as facebook_connection_read_router

from core.facebook_secrets import (decrypt_facebook_secret as descifrar_secreto, encrypt_facebook_secret as cifrar_secreto, facebook_secret_encryption_available)

from core.facebook_connection_store import get_facebook_meta_row as _fb_get_meta_row

from core.facebook_graph import (
    FB_API_VERSION,
    FB_GRAPH,
    _FB_CODIGOS_REINTENTABLES,
    _FB_CODIGOS_TOKEN,
    _FB_ERRORES_COMUNES,
    _FB_ESPERA_BASE,
    _FB_ESPERA_MAX,
    _FB_REINTENTOS,
    _FB_USAR_PROOF,
    _fb_appsecret_proof,
    _fb_debe_reintentar,
    _fb_espera_por_uso,
    _fb_exigir_ok,
    _fb_friendly_error,
    _fb_get_json,
    _fb_parse_error,
    _fb_batch,
)

from routers.facebook_pages import router as facebook_pages_router

from core.facebook_connection_store import patch_facebook_meta as _fb_patch_meta

from routers.facebook_select_page import router as facebook_select_page_router

from routers.facebook_select_ad_account import router as facebook_select_ad_account_router

from routers.facebook_encrypt_tokens import router as facebook_encrypt_tokens_router

from core.facebook_token_lifecycle import (FB_TOKEN_DEFAULT_LIFETIME_SECONDS as _FB_TOKEN_VIDA_DEFECTO, debug_facebook_token as _fb_debug_token)

from routers.facebook_refresh_token import router as facebook_refresh_token_router

from routers.facebook_disconnect import router as facebook_disconnect_router


from routers.facebook_ad_accounts import router as facebook_ad_accounts_router

from routers.facebook_city_search import router as facebook_city_search_router

from core.facebook_insights import (
    FB_BREAKDOWNS as _FB_BREAKDOWNS,
    FB_DATE_PRESETS as _FB_DATE_PRESETS,
    FB_INSIGHTS_FIELDS as _FB_INSIGHTS_FIELDS,
    FB_KEY_ACTIONS as _FB_ACCIONES_CLAVE,
    normalize_facebook_insights as _fb_normaliza_insights,
)


from routers.facebook_campaigns import router as facebook_campaigns_router

from routers.facebook_insights_read import router as facebook_insights_read_router

from routers.facebook_campaign_review import router as facebook_campaign_review_router

from core.facebook_leadgen_config import (
    FB_VERIFY_TOKEN,
    FB_WEBHOOK_SECRET as _FB_WEBHOOK_SECRET,
)

from routers.facebook_leadgen_verify import router as facebook_leadgen_verify_router

from routers.facebook_leadgen_status import router as facebook_leadgen_status_router

from routers.facebook_leadgen_subscribe import router as facebook_leadgen_subscribe_router

from core.facebook_persistence import (
    FACEBOOK_AD_ENTITIES_TABLE as _FB_TABLA_ENTIDADES,
    facebook_table_missing as _fb_tabla_falta,
    warn_facebook_migration as _fb_avisa_migracion,
)

from core.facebook_leadgen_processor import (
    FACEBOOK_LEAD_FIELDS as _FB_CAMPOS_LEAD,
    find_facebook_page_owner as _fb_buscar_dueno_de_pagina,
    process_facebook_lead as _fb_procesar_lead,
)

from routers.facebook_leadgen_webhook import router as facebook_leadgen_webhook_router

from routers.facebook_page_posts import router as facebook_page_posts_router

from routers.facebook_audiences_read import router as facebook_audiences_read_router

from routers.facebook_oauth_callback import router as facebook_oauth_callback_router

from routers.facebook_publish import router as facebook_publish_router

from routers.facebook_publish_property import router as facebook_publish_property_router

from routers.facebook_save_page import router as facebook_save_page_router

from routers.facebook_ad_description import router as facebook_ad_description_router

from routers.facebook_campaign_toggle import router as facebook_campaign_toggle_router

from core.facebook_persistence import (
    find_facebook_creation_by_idempotency as _fb_buscar_por_idempotencia,
    reserve_facebook_creation as _fb_reservar_creacion,
    update_facebook_entity as _fb_actualizar_entidad,
)

from routers.facebook_reconcile import router as facebook_reconcile_router

from routers.facebook_audiences import router as facebook_audiences_router

from routers.facebook_create_ad import router as facebook_create_ad_router
from routers.facebook_qa_selfcheck import router as facebook_qa_selfcheck_router
from routers.chat_claude import create_router as create_chat_claude_router
from routers.easybroker_migration import create_import_all_router
from routers.avm_pdf import create_router as create_avm_pdf_router
from routers.ficha_pdf import create_router as create_ficha_pdf_router
from routers.solicitud_arrendamiento import create_router as create_solicitud_arrendamiento_router
from routers.contact_file_import import create_router as create_contact_file_import_router
app = FastAPI()
app.include_router(create_contact_file_import_router(lambda: {
    "get_user_id_from_token": get_user_id_from_token,
    "HTTPException": HTTPException,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY,
    "re": re,
    "datetime": datetime,
    "get_org_id_for_user": get_org_id_for_user,
    "httpx": httpx,
    "get_rows": get_rows,
    "_mapa_agentes_org": _mapa_agentes_org,
    "patch_rows": patch_rows,
    "post_rows": post_rows,
    "_uuid": _uuid,
}))
app.include_router(create_solicitud_arrendamiento_router(lambda: {
    "get_user_id_from_token": get_user_id_from_token,
    "HTTPException": HTTPException,
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
    "ANTHROPIC_BASE": ANTHROPIC_BASE,
    "_track_anthropic": _track_anthropic,
    "httpx": httpx,
    "base64": base64,
    "io": io,
    "re": re,
    "json": json,
}))
app.include_router(create_ficha_pdf_router(lambda: {
    "get_user_id_from_token": get_user_id_from_token,
    "exigir_cupo": exigir_cupo,
    "exigir_sesion": exigir_sesion,
    "base64": base64,
    "asyncio": asyncio,
    "build_ficha_html": build_ficha_html,
    "async_playwright": async_playwright,
    "_uuid": _uuid,
    "_pdf_store": _pdf_store,
}))
app.include_router(create_avm_pdf_router(lambda: {
    "HTTPException": HTTPException,
    "theme_css_for_pdf": theme_css_for_pdf,
    "_pdf_store": _pdf_store,
    "_uuid": _uuid,
    "time": time,
}))
app.include_router(create_import_all_router(lambda: {
    "get_user_id_from_token": get_user_id_from_token,
    "get_eb_key_for_user": get_eb_key_for_user,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY,
    "_EB_STATUS_MAP": _EB_STATUS_MAP,
    "_EB_STATUS_DEFAULT": _EB_STATUS_DEFAULT,
    "_EB_LIMITE_PROPIEDADES": _EB_LIMITE_PROPIEDADES,
    "get_rows": get_rows,
    "_eb_get_reintentos": _eb_get_reintentos,
    "EB_BASE": EB_BASE,
    "eb_headers": eb_headers,
    "get_org_id_for_user": get_org_id_for_user,
    "_eb_to_brokr": _eb_to_brokr,
    "_EB_LOTE": _EB_LOTE,
    "_EB_PAUSA_LOTE": _EB_PAUSA_LOTE,
    "_prog": _prog,
    "upsert_rows": upsert_rows,
    "_migrar_fotos_org": _migrar_fotos_org,
    "httpx": httpx,
    "asyncio": asyncio,
    "time": time,
}))
app.include_router(create_chat_claude_router(lambda: {
    "get_user_id_from_token": get_user_id_from_token,
    "exigir_cupo": exigir_cupo,
    "exigir_sesion": exigir_sesion,
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
    "ANTHROPIC_BASE": ANTHROPIC_BASE,
    "_request_modulo": _request_modulo,
    "_track_anthropic": _track_anthropic,
    "SHAARK_SYSTEM_PROMPT": SHAARK_SYSTEM_PROMPT,
}))
app.include_router(facebook_qa_selfcheck_router)
app.include_router(facebook_create_ad_router)

app.include_router(facebook_audiences_router)

app.include_router(facebook_reconcile_router)

app.include_router(facebook_refresh_token_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# whatsapp.py es el módulo de WhatsApp (multi-número, IA de recepción, webhook
# propio bajo /whatsapp2 — el prefijo interno del router no cambió aunque el
# archivo ya se llama whatsapp.py). Import defensivo: si algo le falta, el
# resto del backend sigue vivo.
try:
    from whatsapp import router as whatsapp_router
    app.include_router(whatsapp_router)
except Exception as _e:
    import logging as _logging
    _logging.getLogger("broquer.main").error("No se pudo cargar whatsapp: %s", _e)

# Motor agéntico de Broq (tool-use nativo + loop de varios pasos + voz Whisper).
# Import defensivo: si por cualquier razón fallara la carga, el resto del backend
# sigue funcionando con normalidad.
try:
    from routers.agente import router as agente_router
    app.include_router(agente_router)
except Exception as _e:
    print(f"[agente] No se pudo montar el router agéntico: {_e}")

# Broquer para empresas: miembros, invitaciones, roles y permisos.
# Mismo import defensivo: si falla, el resto del backend sigue vivo.
try:
    from routers.organizaciones import router as org_router
    app.include_router(org_router)
except Exception as _e:
    print(f"[org] No se pudo montar el router de organizaciones: {_e}")

# WhatsApp de ChatGPT: onboarding real por Meta Embedded Signup, separado del módulo legacy.
try:
    from routers.whatsapp_chatgpt import router as whatsapp_chatgpt_router
    app.include_router(whatsapp_chatgpt_router)
except Exception as _e:
    print(f"[whatsapp-chatgpt] No se pudo montar el router: {_e}")
# Cumplimiento PLD/UIF: expediente único, umbrales, avisos y bitácora.
# Mismo import defensivo: si falla, el resto del backend sigue vivo.
try:
    from routers.cumplimiento import router as pld_router
    app.include_router(pld_router)
except Exception as _e:
    print(f"[pld] No se pudo montar el router de cumplimiento: {_e}")

# Firma electrónica: documentos, firmantes, código de verificación, constancia
# y verificación pública por folio. Mismo import defensivo: si falla, el resto
# del backend sigue vivo.
try:
    from routers.firmas import router as firmas_router
    app.include_router(firmas_router)
except Exception as _e:
    print(f"[firmas] No se pudo montar el router de firma electrónica: {_e}")

# Video de ficha: arma un recorrido con ffmpeg a partir de las fotos que ya
# viven en la propiedad. Mismo import defensivo: si falla, el resto del
# backend sigue vivo.
try:
    from routers.video import router as video_router
    app.include_router(video_router)
except Exception as _e:
    print(f"[video] No se pudo montar el router de video: {_e}")

# Correo electrónico: conexión IMAP/SMTP, bandeja, lectura, respuesta y
# envío. Mismo import defensivo: si falla, el resto del backend sigue vivo.
try:
    from routers.correo import router as correo_router
    app.include_router(correo_router)
except Exception as _e:
    print(f"[correo] No se pudo montar el router de correo: {_e}")

# Bolsa inmobiliaria: inventario compartido entre agentes Broquer con
# comisión compartida. Mismo import defensivo: si falla, el resto del
# backend sigue vivo.
try:
    from routers.bolsa import router as bolsa_router
    app.include_router(bolsa_router)
except Exception as _e:
    print(f"[bolsa] No se pudo montar el router de la bolsa: {_e}")

# Finanzas: cuentas, ingresos, gastos, rentabilidad por propiedad, lectura
# de tickets con Broq y reportes PDF/CSV. Mismo import defensivo: si falla,
# el resto del backend sigue vivo.
try:
    from routers.finanzas import router as finanzas_router
    app.include_router(finanzas_router)
except Exception as _e:
    print(f"[finanzas] No se pudo montar el router de finanzas: {_e}")

# Solicitud pública de demos.
from routers.demo import router as demo_router
app.include_router(demo_router)

# Cuadrícula pública de Instagram para el landing.
from routers.instagram import router as instagram_router
app.include_router(instagram_router)

# Captura pública de leads desde los sitios de agentes.
from routers.public_site_leads import router as public_site_leads_router
app.include_router(public_site_leads_router)

# Estado mínimo del servicio.
from routers.system import router as system_router
app.include_router(system_router)

# INPC y UDIS desde Banxico SIE.
from routers.banxico import router as banxico_router
app.include_router(banxico_router)

# Heartbeat de uso por módulo.
from routers.telemetry import router as telemetry_router
app.include_router(telemetry_router)

# Proxy de chat Groq.
from routers.chat import router as chat_router
app.include_router(chat_router)

# Configuración pública para el frontend.
from routers.public_config import router as public_config_router
app.include_router(public_config_router)

# Conexión EasyBroker compartida por organización.
from routers.easybroker_config import get_eb_key_for_user, router as easybroker_config_router
app.include_router(easybroker_config_router)

# Importación del historial de leads de EasyBroker.
from routers.easybroker_import_stats import router as easybroker_import_stats_router
app.include_router(easybroker_import_stats_router)

# Coordinador de migración completa EasyBroker.
from routers.easybroker_migration import router as easybroker_migration_router
app.include_router(easybroker_migration_router)

# Importación de contactos directamente desde EasyBroker.
from routers.easybroker_contact_import import router as easybroker_contact_import_router
app.include_router(easybroker_contact_import_router)

# Estado de migración de fotos EasyBroker.
from routers.easybroker_photo_status import (_migrar_fotos_org, router as easybroker_photo_status_router)
app.include_router(easybroker_photo_status_router)

# Diagnóstico de la API de EasyBroker (solo lectura).
from routers.easybroker_diagnostics import router as easybroker_diagnostics_router
app.include_router(easybroker_diagnostics_router)

# Lectura autenticada de propiedades EasyBroker.
from routers.easybroker_properties import router as easybroker_properties_router
app.include_router(easybroker_properties_router)

# Listado legacy de propiedades EasyBroker (solo lectura).
from routers.easybroker_catalog import router as easybroker_catalog_router
app.include_router(easybroker_catalog_router)

# Autocomplete de colonias desde EasyBroker.
from routers.easybroker_colonias import router as easybroker_colonias_router
app.include_router(easybroker_colonias_router)

# Descargas de PDFs generados en memoria.
from routers.pdf_downloads import router as pdf_downloads_router
app.include_router(pdf_downloads_router)

# Generación de PDF para ISR.
from routers.isr_pdf import router as isr_pdf_router
app.include_router(isr_pdf_router)

# Noticias inmobiliarias RSS.
from routers.news import router as news_router
app.include_router(news_router)

# Descripción IA para ficha manual.
from routers.ficha_manual import router as ficha_manual_router
app.include_router(ficha_manual_router)

# Comparables AVM vía Apify/Inmuebles24.
from routers.avm_apify import router as avm_apify_router
app.include_router(avm_apify_router)

# Colonias AVM vía Google Places.
from routers.avm_places import router as avm_places_router
app.include_router(avm_places_router)

# Comparables AVM cercanos vía Supabase/PostGIS.
from routers.avm_nearby import router as avm_nearby_router
app.include_router(avm_nearby_router)

# Limpieza y edición de imágenes inmobiliarias.
from routers.image_cleaner import router as image_cleaner_router
app.include_router(image_cleaner_router)

# Recordatorios de tareas/citas en background.
from routers.reminders import router as reminders_router
app.include_router(reminders_router)

# Generación de contrato DOCX estándar.
from routers.contracts_basic import router as contracts_basic_router
app.include_router(contracts_basic_router)

# Contratos personalizados (machotes).
from routers.machotes import router as machotes_router
app.include_router(machotes_router)

# Compatibility aliases while main.py is progressively decomposed. All runtime
# environment names and public/privileged Supabase key policy live in Core.
GROQ_API_KEY     = settings.groq_api_key
ANTHROPIC_API_KEY = settings.anthropic_api_key
GEMINI_API_KEY    = settings.gemini_api_key
GROQ_BASE        = "https://api.groq.com/openai/v1"
ANTHROPIC_BASE   = "https://api.anthropic.com/v1"
GEMINI_BASE      = "https://generativelanguage.googleapis.com/v1beta"
APIFY_API_KEY = settings.apify_api_key
GOOGLE_PLACES_KEY = settings.google_places_key
SUPABASE_URL      = settings.supabase_url
SUPABASE_KEY      = settings.supabase_anon_key
FB_APP_ID     = settings.legacy_main_fb_app_id
FB_APP_SECRET = settings.legacy_main_fb_app_secret
FRONTEND_URL  = settings.legacy_main_frontend_url
# Banxico SIE — INPC + UDIS para calculadora ISR
BANXICO_TOKEN     = settings.banxico_token
BANXICO_BASE      = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"
BANXICO_SERIE_UDIS = settings.banxico_series_udis  # Valor de UDIS (diaria)
BANXICO_SERIE_INPC = settings.banxico_series_inpc  # INPC mensual base 2Q-jul-2018=100
# service_role key — bypasea RLS. Solo para operaciones del backend en nombre
# del usuario, DESPUÉS de validar su JWT con get_user_id_from_token().
# NUNCA expongas esta variable al frontend.
SUPABASE_SERVICE_KEY = settings.supabase_service_key
# Pagos — Stripe

# ════════════════════════════════════════════════════════════════
# CONTEXTO DE ORGANIZACIÓN (Broquer para empresas)
# Tras la migración, la RLS filtra por org_id — NO por user_id. Todo registro
# que cree el backend debe llevar org_id o queda huérfano e invisible para
# todos. El backend usa service key y se brinca la RLS, así que un olvido aquí
# no truena: silenciosamente crea basura. Por eso va explícito en cada INSERT.
# ════════════════════════════════════════════════════════════════
from routers.organizaciones import (
    get_org_id_for_user, get_org_context, permiso_efectivo,
    exigir_gestion_integraciones,
)


# Suscripción de Broquer para Empresas.
from routers.subscription_enterprise import router as subscription_enterprise_router
app.include_router(subscription_enterprise_router)

# Checkout web de suscripción individual.
from routers.subscription_checkout import router as subscription_checkout_router
app.include_router(subscription_checkout_router)

# Cancelación de suscripción web.
from routers.subscription_cancel import router as subscription_cancel_router
app.include_router(subscription_cancel_router)

# Activación interna de suscripciones.
from routers.subscription_activate import router as subscription_activate_router
app.include_router(subscription_activate_router)

# Webhook de suscripciones web vía Stripe.
from routers.stripe_webhook import router as stripe_webhook_router
app.include_router(stripe_webhook_router)

# Webhook de suscripciones iOS vía RevenueCat.
from routers.revenuecat import router as revenuecat_router
app.include_router(revenuecat_router)

# Estado de suscripción y trial de Broquer Max.
from routers.subscription_status import router as subscription_status_router
app.include_router(subscription_status_router)

# Eliminación administrativa total (aislada; nunca se invoca en la auditoría).
from routers.admin_delete import router as admin_delete_router
app.include_router(admin_delete_router)

# Mutaciones administrativas no destructivas.
from routers.admin_accounts import router as admin_accounts_router
app.include_router(admin_accounts_router)

# Lecturas administrativas legacy.
from routers.admin_read import router as admin_read_router
app.include_router(admin_read_router)

# Estado unificado de perfil e integraciones.
from routers.profile_status import router as profile_status_router
app.include_router(profile_status_router)

# ────────────────────────────────────────────
# CLAUDE CHAT PROXY — BROQ IA SUPERINTELIGENTE
# ────────────────────────────────────────────
from routers.chat_claude_prompt import SHAARK_SYSTEM_PROMPT




# ──────────────────────────────────────────────────────────────
# SOLICITUD DE ARRENDAMIENTO — Análisis con Claude (vision/PDF/DOCX)
# ──────────────────────────────────────────────────────────────


# ════════════════════════════════════════════════════════════════
# IMPORTACIÓN MASIVA DESDE EASYBROKER
# Trae TODAS las propiedades del agente desde su cuenta de EasyBroker
# y las inserta en Supabase (tabla propiedades) bajo SU user_id.
# Deduplicación por eb_public_id: si ya existe, la salta.
# ════════════════════════════════════════════════════════════════



# Borrado masivo de propiedades y contactos.
from routers.bulk_delete import router as bulk_delete_router
app.include_router(bulk_delete_router)

app.include_router(admin_usage_router)
app.include_router(account_delete_router)
app.include_router(avm_legacy_router)

app.include_router(avm_claude_router)

app.include_router(avm_websearch_router)

app.include_router(facebook_connection_read_router)

app.include_router(facebook_pages_router)

app.include_router(facebook_select_page_router)

app.include_router(facebook_select_ad_account_router)

app.include_router(facebook_encrypt_tokens_router)

app.include_router(facebook_disconnect_router)

app.include_router(facebook_ad_accounts_router)

app.include_router(facebook_city_search_router)

app.include_router(facebook_campaigns_router)

app.include_router(facebook_insights_read_router)

app.include_router(facebook_campaign_review_router)

app.include_router(facebook_leadgen_verify_router)

app.include_router(facebook_leadgen_status_router)

app.include_router(facebook_leadgen_subscribe_router)

app.include_router(facebook_leadgen_webhook_router)

app.include_router(facebook_page_posts_router)

app.include_router(facebook_audiences_read_router)

app.include_router(facebook_oauth_callback_router)

app.include_router(facebook_publish_router)

app.include_router(facebook_publish_property_router)

app.include_router(facebook_save_page_router)

app.include_router(facebook_ad_description_router)

app.include_router(facebook_campaign_toggle_router)




# ────────────────────────────────────────────
# COLONIAS AUTOCOMPLETE
# ────────────────────────────────────────────
# ────────────────────────────────────────────
# AVM — HELPERS
# ────────────────────────────────────────────







# ────────────────────────────────────────────
# HEDONIC MODEL
# ────────────────────────────────────────────


# ────────────────────────────────────────────
# AVM ENDPOINT
# ────────────────────────────────────────────




# ────────────────────────────────────────────
# AVM — CLAUDE AI OPINION DE VALOR
# ────────────────────────────────────────────




# ────────────────────────────────────────────
# AVM — OPINIÓN DE VALOR CON INVESTIGACIÓN CONTROLADA DE COMPARABLES
# ────────────────────────────────────────────



# ────────────────────────────────────────────
# AVM — PDF DE OPINIÓN DE VALOR
# ────────────────────────────────────────────



# ────────────────────────────────────────────
# CONTRATOS
# ────────────────────────────────────────────

# ── PDF GENERATION ──────────────────────────────────────────────
from playwright.async_api import async_playwright




from routers.ficha_pdf_renderer import build_ficha_html



# ────────────────────────────────────────────
# NOTICIAS INMOBILIARIAS — RSS REAL
# ────────────────────────────────────────────


# ════════════════════════════════════════════════════════════════
# META GRAPH API — capa común
# ════════════════════════════════════════════════════════════════
# Todas las llamadas al Graph API de Meta (Facebook) pasan por aquí.
# Antes cada endpoint hacía su propio httpx.get/post: la versión de la API
# estaba escrita a mano en ~40 lugares (y una se quedó en v18.0), nadie
# reintentaba cuando Meta contestaba 429, y los errores se devolvían como
# texto crudo. Esta capa arregla las tres cosas de un solo lugar.
#
# Es el espejo de _eb_get_reintentos() (EasyBroker), pero para Meta:
# Meta además codifica el motivo real del rechazo en `error.code`, no solo
# en el status HTTP, y publica su presupuesto de llamadas en la cabecera
# X-Business-Use-Case-Usage. Ambas cosas se honran abajo.



# ─── Cifrado de tokens en reposo ──────────────────────────────────────────────
# Los tokens de Meta (página y usuario) vivían en texto plano en Supabase.
# Quien leyera esa tabla —un respaldo filtrado, una service_role key expuesta,
# un empleado con acceso a la consola— podía publicar y GASTAR en nombre del
# agente. Ahora se guardan cifrados con Fernet (AES-128-CBC + HMAC).
#
# Compatibilidad: los valores viejos siguen en claro y se leen igual. Se
# vuelven a escribir cifrados en cuanto la fila se actualiza, o de un jalón con
# POST /facebook/encrypt-tokens.
#
# Sin TOKEN_ENC_KEY configurada todo sigue funcionando en claro (y se avisa una
# vez en el log). Generar una llave:
#     python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"










# Códigos de error de Meta que significan "vuelve a intentar", NO "estás mal".
#   1     · API Unknown (error transitorio del lado de Meta)
#   2     · API Service (servicio temporalmente caído)
#   4     · Application request limit reached (límite de la app)
#   17    · User request limit reached (límite del usuario)
#   32    · Page-level throttling
#   341   · Application limit reached (límite temporal)
#   613   · Calls to this API have exceeded the rate limit
#   80000-80006 · Rate limits por caso de uso (80004 = ads_management)

# Códigos que significan "el token murió" — reintentar no sirve de nada.

# Interruptor de emergencia: si el appsecret_proof rompiera algo en producción
# se apaga con FB_APPSECRET_PROOF=0 en Railway sin tocar código.






# Errores de Meta traducidos a español de negocio. La llave es el
# error_subcode (o el code si no hay subcode) que manda Meta.
















# ─── Tokens: vida, permisos y avisos de expiración ────────────────────────────

# Los tokens de larga duración de Meta duran ~60 días. Cuando Meta no manda
# expires_in (tokens de página, que no expiran solos), asumimos este valor para
# poder avisar de todas formas.

# Días antes de la expiración en que empezamos a avisar en la UI.

# Permisos sin los cuales el módulo de anuncios no puede funcionar.






# ════════════════════════════════════════════════════════════════
# META — memoria de lo que Broquer creó (tabla fb_ad_entities)
# ════════════════════════════════════════════════════════════════
# Antes, crear un anuncio era una operación sin memoria: si el flujo se rompía
# a la mitad, los IDs se perdían y los recursos quedaban huérfanos en la cuenta
# publicitaria sin que nadie supiera que existían. Y un doble clic creaba dos
# campañas cobrando en paralelo.
#
# Todo esto degrada con elegancia: si la tabla no existe todavía (migración sin
# correr), se registra un aviso en el log y el anuncio se crea igual. Perder la
# bitácora no puede ser motivo para no poder anunciar.















# ─── FACEBOOK OAUTH ───────────────────────────────────────────────────────────

# ────────────────────────────────────────────
# FACEBOOK — guardar / leer conexión por usuario
# ────────────────────────────────────────────





























# ─── FACEBOOK ADS ─────────────────────────────────────────────────────────────













# Periodos que Meta acepta en `date_preset`. Se valida contra esta lista para
# no reenviar a Meta cualquier cosa que llegue por query string.

# Breakdowns soportados. Meta no deja combinar cualquiera con cualquiera; esta
# lista es la que el módulo ofrece y sabe pintar.

# Las acciones que de verdad importan para un anuncio Click-to-Messenger.
# El KPI real del agente inmobiliario NO son las impresiones: son las
# conversaciones abiertas en Messenger y lo que cuesta cada una.









# Traducción de los effective_status de Meta. Un anuncio puede decir ACTIVE y
# no entregar nada porque Meta lo rechazó: sin esto el agente solo ve que "no
# llegan mensajes" y no sabe por qué.




# ════════════════════════════════════════════════════════════════
# META — Lead Ads: webhook y captura automática de prospectos
# ════════════════════════════════════════════════════════════════
# Un "Lead Ad" es el anuncio con formulario dentro de Facebook: la persona
# llena sus datos sin salir de la app. Meta avisa por webhook y hay que ir a
# recoger el lead con el token de la página.
#
# Sin esto, los leads se quedaban en Meta hasta que alguien se acordaba de
# bajarlos a mano — y un prospecto inmobiliario que espera dos días ya le
# compró a alguien más.

# Token que Meta usa para verificar la suscripción. Si no está configurado, el
# webhook queda cerrado (no se acepta ninguna suscripción a ciegas).
# Secreto para validar la firma. Se cae a FB_APP_SECRET porque los Lead Ads
# viven en la misma app de Meta que los anuncios.








# Cómo se llaman los campos estándar de Meta y a qué columna del CRM van.








# ════════════════════════════════════════════════════════════════
# META — públicos personalizados y similares (desde el CRM)
# ════════════════════════════════════════════════════════════════
# Sube los contactos del agente a Meta HASHEADOS (SHA-256) para poder
# anunciarle a su propia cartera, y para generar "públicos similares"
# (lookalikes): gente parecida a quienes ya le compraron.
#
# Meta NUNCA recibe datos en claro: el hash se hace aquí y es irreversible.
# Aun así, subir datos de clientes exige que el dueño de la cuenta haya
# aceptado las Condiciones de Públicos Personalizados en Business Manager;
# si no lo hizo, Meta rechaza con el código 2654 y aquí se traduce a
# instrucciones concretas en vez de un error críptico.

























# ════════════════════════════════════════════════════════════════
# META — AUTODIAGNÓSTICO (solo contra cuenta de PRUEBAS)
# ════════════════════════════════════════════════════════════════
# Ejercita la integración de punta a punta contra una TEST AD ACCOUNT de Meta:
# crea campaña, conjunto, creativo y anuncio de verdad, los lee, los prende y
# apaga, y al final los borra. Las cuentas de prueba de Meta NO cobran.
#
# Tres candados para que esto no pueda correr contra producción:
#   1. FB_QA_ENABLED=1 en el entorno.
#   2. FB_QA_AD_ACCOUNT_ID apuntando explícitamente a la cuenta de pruebas.
#   3. Verificación CONTRA META de que esa cuenta aparece en la lista de
#      cuentas de prueba de la app (/{app_id}/adaccounts). Si no aparece, se
#      aborta. No hay bandera para saltarse este candado.











# ════════════════════════════════════════════════════════════════
# STRIPE — SUSCRIPCIONES
# ════════════════════════════════════════════════════════════════


# IDs de Precios en Stripe (crear en dashboard.stripe.com → Productos → Precios)

# ── Broquer para Empresas ────────────────────────────────────────
# Se cobra en DOS líneas dentro de la misma suscripción de Stripe:
#   · base  → paquete de 5 usuarios, cantidad siempre 1
#   · extra → usuario adicional, cantidad = asientos - 5
# Así el dueño puede subir o bajar lugares sin cambiar de suscripción.


# Solo para pintar la pantalla. El cobro real siempre lo manda Stripe.




# ════════════════════════════════════════════════════════════════
# Contactos / Importar desde EasyBroker
# ════════════════════════════════════════════════════════════════




# ════════════════════════════════════════════════════════════════
# Migración completa EasyBroker como TRABAJO EN SEGUNDO PLANO
# El navegador ya no sostiene peticiones largas (se caían con cualquier
# corte o reinicio): inicia el trabajo y consulta el avance cada pocos
# segundos. El trabajo corre en el servidor y sobrevive a recargas de
# página. Los tres pasos se llaman internamente (localhost) reusando la
# lógica existente sin duplicarla.
# ════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────
# ADMIN
# Endpoints basados en rol (admin/equipo/agente) + activo (bool).
# El rol gobierna el acceso; las suscripciones de Stripe son solo para agentes.
# Solo accesibles si el caller tiene rol=admin (verificado vía service key).
# ─────────────────────────────────────────────



# ════════════════════════════════════════════════════════════════
# Eliminar cuenta y datos del usuario (acción irreversible)
# ════════════════════════════════════════════════════════════════
