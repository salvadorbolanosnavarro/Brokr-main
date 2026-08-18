from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Heartbeat de uso por módulo.\nfrom routers.telemetry import router as telemetry_router\napp.include_router(telemetry_router)\n'''
mount_block = mount_anchor + '''\n# Proxy de chat Groq.\nfrom routers.chat import router as chat_router\napp.include_router(chat_router)\n'''
if source.count('from routers.chat import router as chat_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected chat mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.chat import router as chat_router') != 1:
    raise SystemExit("unexpected chat router mount state")

start_marker = '''# ────────────────────────────────────────────\n# GROQ CHAT PROXY\n'''
end_marker = '''# ────────────────────────────────────────────\n# CLAUDE CHAT PROXY — BROQ IA SUPERINTELIGENTE\n'''
if start_marker in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    source = source[:start] + source[end:]
elif '@app.post("/chat")' in source or 'class ChatRequest(BaseModel):' in source:
    raise SystemExit("unexpected partially extracted chat state")

if '@app.post("/chat")' in source or 'class ChatRequest(BaseModel):' in source:
    raise SystemExit("chat symbols remain in main")
if source.count('app.include_router(chat_router)') != 1:
    raise SystemExit("chat router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
