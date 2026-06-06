# social-mcps

Sistema de MCP servers en Python para publicación automática en redes sociales. Cada plataforma vive en su propia carpeta completamente independiente: arrancan como procesos separados, tienen sus propias credenciales y no comparten ningún código entre sí. Añadir una nueva plataforma es tan simple como crear una nueva carpeta.

## Plataformas disponibles

| Carpeta | Plataforma | API | Herramientas |
|---|---|---|---|
| `linkedin/` | LinkedIn | UGC Posts API | publish_post, get_last_posts, delete_post, get_account_info |
| `instagram/` | Instagram | Instagram Graph API | publish_post, get_last_posts, delete_post, get_account_info |
| `facebook/` | Facebook | Pages API | publish_post, get_last_posts, delete_post, get_account_info |
| `wordpress/` | WordPress.com | REST API v1.1 | publish_post, get_last_posts, delete_post, get_account_info |

---

## Cómo funciona

Cada MCP server se lanza como un proceso independiente en modo stdio. El cliente MCP (Claude Desktop u otro) se comunica con él a través de stdin/stdout usando el protocolo JSON-RPC de MCP.

```
Cliente MCP  ──stdin/stdout──►  linkedin/server.py   ──►  LinkedIn API
             ──stdin/stdout──►  instagram/server.py  ──►  Instagram API
             ──stdin/stdout──►  facebook/server.py   ──►  Facebook API
             ──stdin/stdout──►  wordpress/server.py  ──►  WordPress.com API
```

---

## Primeros pasos

Cada plataforma tiene su propio proceso de configuración en dos fases. Lee el README de la carpeta correspondiente antes de empezar.

### Resumen rápido

**Para cada plataforma:**

1. **Crear la app** en el portal de desarrolladores de la plataforma (manual, una sola vez) y obtener `CLIENT_ID` + `CLIENT_SECRET`.
2. **Copiar y rellenar** el `.env`:
   ```bash
   cp .env.example .env
   # Editar .env con CLIENT_ID y CLIENT_SECRET
   ```
3. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Ejecutar el asistente de autorización** (obtiene tokens automáticamente):
   ```bash
   python oauth_setup.py
   ```
5. **Arrancar el servidor:**
   ```bash
   python server.py
   ```

### Dónde crear cada app

| Plataforma | Portal | Notas |
|---|---|---|
| LinkedIn | [linkedin.com/developers/apps](https://www.linkedin.com/developers/apps) | Activar productos "Share on LinkedIn" y "Sign In with LinkedIn" |
| Instagram | [developers.facebook.com](https://developers.facebook.com) | App de tipo Business, añadir producto Instagram Graph API. Requiere cuenta Business/Creator |
| Facebook | [developers.facebook.com](https://developers.facebook.com) | Se puede reutilizar la misma app que Instagram |
| WordPress | [developer.wordpress.com/apps](https://developer.wordpress.com/apps) | El más sencillo, sin revisión ni restricciones |

---

## Arquitectura

```
social-mcps/
├── linkedin/
│   ├── server.py       # Punto de entrada MCP (FastMCP + lifespan)
│   ├── auth.py         # Gestión del ciclo de vida de tokens OAuth
│   ├── api.py          # Cliente HTTP contra la API de LinkedIn
│   ├── tools.py        # Funciones handler de cada herramienta MCP
│   ├── models.py       # Modelos Pydantic
│   ├── logger.py       # Logging a stderr + archivo rotativo
│   ├── oauth_setup.py  # Asistente de autorización inicial
│   ├── .env.example    # Plantilla de variables de entorno
│   └── logs/           # Logs persistentes (gitignored)
├── instagram/          # Misma estructura
├── facebook/           # Misma estructura
└── wordpress/          # Misma estructura
```

**Principios de diseño:**
- **Open/Closed:** el núcleo no cambia al añadir plataformas. Cada carpeta es un silo completo.
- **Single Responsibility:** cada archivo tiene una sola responsabilidad.
- **Sin credenciales en código:** todo en `.env`, nunca en el repositorio.
- **Reintentos automáticos:** backoff exponencial (2s → 4s → 8s, 3 intentos) en todas las llamadas a API.
- **Respuestas estructuradas:** todas las herramientas devuelven `{"success": true/false, "data": ..., "error": ...}`.

---

## Configuración en Claude Desktop

Para usar todos los MCPs simultáneamente, añade cada uno a `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "linkedin": {
      "command": "python",
      "args": ["/ruta/absoluta/social-mcps/linkedin/server.py"]
    },
    "instagram": {
      "command": "python",
      "args": ["/ruta/absoluta/social-mcps/instagram/server.py"]
    },
    "facebook": {
      "command": "python",
      "args": ["/ruta/absoluta/social-mcps/facebook/server.py"]
    },
    "wordpress": {
      "command": "python",
      "args": ["/ruta/absoluta/social-mcps/wordpress/server.py"]
    }
  }
}
```
