# api2/endpoint_inspector.py
from django.urls import get_resolver
from django.http import HttpResponse
from django.conf import settings
from datetime import datetime

def list_endpoints(staff_only=True):
    """
    Extrae todos los endpoints registrados.
    Si staff_only=True, solo muestra endpoints que no tengan permisos restrictivos.
    """
    resolver = get_resolver()
    patterns = resolver.url_patterns
    endpoints = []

    def extract_patterns(patterns, prefix=""):
        for pattern in patterns:
            # Handle nested URLs (include, namespace)
            if hasattr(pattern, "url_patterns"):
                new_prefix = prefix + str(pattern.pattern).lstrip('^').rstrip('$')
                extract_patterns(pattern.url_patterns, new_prefix)
            else:
                url_pattern = str(pattern.pattern).lstrip('^').rstrip('$')
                full_url = f"/{prefix}{url_pattern}".replace('//','/')
                methods = extract_http_methods(pattern)
                view_name = extract_view_name(pattern)
                
                # Opcional: filtrar endpoints internos/admin
                if staff_only and ('admin/' in full_url or 'swagger' in full_url):
                    continue
                
                endpoints.append({
                    "url": full_url,
                    "methods": methods,
                    "view": view_name,
                    "pattern": str(pattern.pattern)
                })

    def extract_http_methods(pattern):
        """Detecta métodos HTTP permitidos"""
        callback = getattr(pattern, 'callback', None)
        if hasattr(callback, 'view_class'):
            view_class = callback.view_class
            return [m.upper() for m in getattr(view_class, 'http_method_names', ['get'])]
        if hasattr(callback, 'methods'):
            return [m.upper() for m in callback.methods]
        return ["GET"]

    def extract_view_name(pattern):
        callback = getattr(pattern, 'callback', None)
        if hasattr(callback, 'view_class'):
            return callback.view_class.__name__
        if hasattr(callback, '__name__'):
            return callback.__name__
        return str(callback).split(' ')[1] if ' ' in str(callback) else str(callback)

    extract_patterns(patterns)
    return sorted(endpoints, key=lambda x: x["url"])

def api_home(request):
    """
    Página principal de documentación de la API
    """
    if not settings.DEBUG and not (request.user.is_staff if request.user.is_authenticated else False):
        return HttpResponse("🔒 Acceso restringido", status=403)

    endpoints = list_endpoints(staff_only=True)
    
    endpoints_rows = []
    for ep in endpoints:
        methods_html = "".join(
            f'<span class="method {m.lower()}">{m}</span>' for m in ep["methods"]
        )
        endpoints_rows.append(f"""
            <tr>
                <td class="url">{ep['url']}</td>
                <td class="methods">{methods_html}</td>
                <td class="view">{ep['view']}</td>
                <td>
                    <button class="copy-btn" onclick="copyEndpoint('{ep['url']}')">📋 Copiar</button>
                </td>
            </tr>
        """)

    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>DjidjiMusic API</title>
        <style>
            :root {{
                --primary: #00d4ff;
                --primary-dark: #0099cc;
                --bg-dark: #0d0d0d;
                --bg-card: #1a1a1a;
                --bg-row: #262626;
                --text-light: #f2f2f2;
                --text-gray: #777;
            }}
            * {{ margin:0; padding:0; box-sizing:border-box; }}
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                background: var(--bg-dark);
                color: var(--text-light);
                padding:20px; min-height:100vh;
            }}
            h1 {{ color: var(--primary); font-size:2.5em; margin-bottom:10px; }}
            .box {{ background:var(--bg-card); padding:25px; border-radius:12px; margin-bottom:30px; box-shadow:0 4px 20px rgba(0,212,255,0.1); border:1px solid rgba(0,212,255,0.1); }}
            table {{ width:100%; border-collapse:collapse; margin-top:15px; }}
            th, td {{ padding:12px 15px; text-align:left; border-bottom:1px solid rgba(255,255,255,0.1); }}
            th {{ background: var(--bg-row); color: var(--primary); font-weight:600; text-transform:uppercase; }}
            tr:hover {{ background: rgba(0,212,255,0.05); }}
            .url {{ font-family:'Monaco','Consolas',monospace; font-size:0.9em; color:var(--primary); }}
            .methods {{ display:flex; gap:5px; flex-wrap:wrap; }}
            .method {{ padding:3px 8px; border-radius:4px; font-size:0.8em; font-weight:bold; text-transform:uppercase; }}
            .method.get {{ background:#10b981; color:white; }}
            .method.post {{ background:#f59e0b; color:white; }}
            .method.put {{ background:#3b82f6; color:white; }}
            .method.patch {{ background:#8b5cf6; color:white; }}
            .method.delete {{ background:#ef4444; color:white; }}
            .view {{ font-family:'Monaco','Consolas',monospace; font-size:0.85em; color:var(--text-gray); }}
            .copy-btn {{ background:var(--primary); border:none; color:var(--bg-dark); padding:6px 12px; border-radius:6px; cursor:pointer; font-size:0.85em; font-weight:600; transition:all 0.2s ease; }}
            .copy-btn:hover {{ background:var(--primary-dark); transform:translateY(-1px); }}
            footer {{ margin-top:50px; text-align:center; color:var(--text-gray); padding:20px; border-top:1px solid rgba(255,255,255,0.1); }}
            @media(max-width:768px) {{ table{{display:block; overflow-x:auto;}} .methods{{flex-direction:column;}} }}
        </style>
    </head>
    <body>
        <h1>🎵 DjidjiMusic API</h1>
        <div class="box">
            <p><b>Estado:</b> ✔️ Operativo</p>
            <p><b>Versión:</b> v1.0.0</p>
            <p><b>Debug:</b> {'✅ Activado' if settings.DEBUG else '❌ Desactivado'}</p>
            <p><b>Endpoints:</b> {len(endpoints)}</p>
        </div>
        <div class="box">
            <h2>📡 Endpoints Disponibles</h2>
            <table>
                <thead>
                    <tr><th>URL</th><th>Métodos</th><th>Vista</th><th>Acción</th></tr>
                </thead>
                <tbody>{''.join(endpoints_rows)}</tbody>
            </table>
        </div>
        <footer>
            <p>© {datetime.now().year} DjidjiMusic — API Backend</p>
            <p style="font-size:0.9em;margin-top:5px;">Documentación generada automáticamente</p>
        </footer>
        <script>
            function copyEndpoint(url){{
                navigator.clipboard.writeText(url).then(()=>{{
                    const btn=event.target;
                    const original=btn.textContent;
                    btn.textContent='✅ Copiado!';
                    btn.style.background='#10b981';
                    setTimeout(()=>{{btn.textContent=original;btn.style.background='';}},2000);
                }}).catch(err=>{{console.error('Error:',err); alert('Error: '+err);}});
            }}
        </script>
    </body>
    </html>
    """
    return HttpResponse(html)
