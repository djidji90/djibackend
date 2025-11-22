from django.urls import get_resolver
from django.http import HttpResponse
import json

def list_endpoints():
    resolver = get_resolver()
    patterns = resolver.url_patterns

    endpoints = []

    def extract(patterns, prefix=""):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                extract(p.url_patterns, prefix + str(p.pattern))
            else:
                endpoints.append(str(prefix + str(p.pattern)))

    extract(patterns)
    return sorted(endpoints)


def api_home(request):
    endpoints = list_endpoints()

    html = f"""
    <html>
    <head>
        <title>DjidjiMusic API</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #0d0d0d;
                color: #f2f2f2;
                margin: 40px;
            }}

            h1 {{
                color: #00d4ff;
            }}

            .box {{
                background: #1a1a1a;
                padding: 20px;
                border-radius: 10px;
                margin-bottom: 30px;
                box-shadow: 0 0 10px #00d4ff55;
            }}

            ul {{
                list-style: none;
                padding: 0;
            }}

            li {{
                margin: 8px 0;
            }}

            .endpoint {{
                padding: 8px 12px;
                background: #262626;
                border-radius: 6px;
                display: inline-block;
            }}

            footer {{
                margin-top: 40px;
                color: #777;
            }}
        </style>
    </head>
    <body>
        <h1>🎵 DjidjiMusic API</h1>

        <div class="box">
            <h2>📌 Información</h2>
            <p><b>Estado:</b> OK ✔️</p>
            <p><b>Versión:</b> v1.0.0</p>
            <p><b>Debug:</b> False (producción)</p>
        </div>

        <div class="box">
            <h2>📡 Endpoints disponibles ({len(endpoints)})</h2>
            <ul>
                {''.join(f'<li><span class="endpoint">/{e}</span></li>' for e in endpoints)}
            </ul>
        </div>

        <footer>© DjidjiMusic — API Backend</footer>
    </body>
    </html>
    """

    return HttpResponse(html)
