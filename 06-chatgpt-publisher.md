# 📤 Agente 6B: ChatGPT Publisher

## Objetivo

Flujo especializado de publicación para ejecuciones realizadas desde ChatGPT o un modelo/agente de OpenAI que disponga de generación nativa de imágenes y enlaces compartidos de ChatGPT.

Este archivo NO sustituye a `06-publisher.md`.

`06-publisher.md` continúa siendo el Publisher general y debe utilizarse en Claude, otros agentes, automatizaciones externas y cualquier entorno donde no esté disponible el flujo visual específico de ChatGPT.

---

## Cuándo utilizar este Publisher

Utilizar `06-chatgpt-publisher.md` únicamente cuando se cumplan estas condiciones:

1. La ejecución se realiza desde ChatGPT o un entorno OpenAI compatible.
2. El modelo puede generar la imagen de la noticia mediante las herramientas nativas de OpenAI.
3. La imagen puede obtenerse mediante una URL compartida de ChatGPT con formato:

`https://chatgpt.com/s/...`

4. Está disponible el conector `Social-Mcps-Cloud`.

Si cualquiera de estas condiciones no se cumple, utilizar el flujo general definido en:

`06-publisher.md`

---

## Principio del flujo visual

El flujo específico de ChatGPT es:

ChatGPT genera → ChatGPT Share → bucket temporal → WordPress → URL permanente → redes sociales

La URL compartida de ChatGPT es únicamente el origen de la imagen.

El bucket temporal de Social-Mcps-Cloud actúa como puente.

WordPress proporciona finalmente el alojamiento permanente de la imagen.

---

## 1. Preparar y revisar la noticia

Antes de publicar:

1. Recuperar los contenidos preparados para:
   - WordPress
   - LinkedIn
   - Facebook / Instagram
   - Threads
   - X.
2. Comprobar que la noticia continúa vigente.
3. Mostrar al usuario un resumen del contenido que se publicará.
4. Solicitar confirmación explícita.

No llamar a ninguna herramienta de publicación sin autorización expresa del usuario.

---

## 2. Generar la imagen en ChatGPT

Generar mediante las herramientas nativas de OpenAI una imagen específica para la noticia.

Características recomendadas:

- relación 1:1;
- compatible con Instagram;
- adecuada también para WordPress, LinkedIn y Facebook;
- relacionada directamente con el contenido;
- estilo tecnológico, editorial y profesional;
- evitar imágenes genéricas de robots humanoides salvo que tengan sentido;
- si contiene texto, debe ser breve, legible y en español;
- no introducir afirmaciones o cifras no verificadas.

Mostrar la imagen al usuario.

Si la generación de la imagen no estaba incluida en una autorización previa, esperar su aprobación antes de continuar.

---

## 3. Obtener el enlace compartido de ChatGPT

La imagen generada no debe enviarse directamente desde una ruta interna de ChatGPT a las APIs externas.

El usuario utilizará Compartir y proporcionará una URL similar a:

`https://chatgpt.com/s/...`

Esta URL se utilizará únicamente como entrada de Social-Mcps-Cloud.

NO enviar directamente esta URL a:

- WordPress
- LinkedIn
- Facebook
- Instagram

---

## 4. Subir la imagen al bucket temporal

Utilizar:

`upload_temp_image`

Parámetros recomendados:

- `image_url`: URL `https://chatgpt.com/s/...`
- `filename`: nombre descriptivo terminado en `.jpg`
- `ttl_seconds`: 1800
- `auto_optimize`: `true`

Social-Mcps-Cloud debe:

1. abrir la página compartida;
2. localizar la imagen pública real;
3. descargarla;
4. optimizarla;
5. convertirla a JPEG cuando sea necesario;
6. almacenarla temporalmente;
7. devolver una URL pública temporal.

Guardar:

- `object_name`
- `public_url` o `signed_url`
- `mime_type`
- `size_bytes`
- `expires_at`

A partir de este punto, dejar de utilizar la URL `chatgpt.com/s/...`.

---

## 5. Validar la imagen temporal

Comprobar:

- `success: true`
- MIME de imagen válido
- URL pública disponible
- TTL suficiente
- tamaño adecuado

Para WordPress:

- preferir JPEG;
- objetivo inferior a 300 KB.

Si no se obtiene una imagen temporal válida:

detener WordPress, LinkedIn, Facebook e Instagram.

Threads y X pueden continuar porque no requieren imagen, siempre que el usuario haya autorizado la publicación.

---

## 6. Publicar WordPress primero

WordPress continúa siendo obligatoriamente el primer canal.

Utilizar:

`wordpress_publish_post`

con:

- título aprobado;
- artículo aprobado;
- `status="publish"`;
- `image_url` igual a la URL pública TEMPORAL del bucket.

Nunca pasar directamente `https://chatgpt.com/s/...`.

WordPress debe descargar la imagen temporal y almacenarla en su mediateca.

---

## 7. Verificar WordPress

Si la publicación tiene éxito, guardar:

- ID del artículo;
- URL definitiva del artículo;
- URL permanente de la imagen, si está disponible.

La URL del artículo sustituye `[WORDPRESS_URL]` en los textos sociales.

La imagen alojada en WordPress pasa a ser la versión permanente de la creatividad.

### Si WordPress devuelve error

NO reintentar automáticamente.

Especialmente ante errores procedentes de:

`/media/new`

Registrar, siempre que sea posible:

- HTTP status;
- cuerpo completo de respuesta;
- MIME enviado;
- filename;
- tamaño;
- URL utilizada.

Si el resultado es ambiguo, utilizar:

`wordpress_get_last_posts`

antes de decidir si la publicación ha fallado realmente.

Nunca realizar varios intentos consecutivos a ciegas porque pueden producir medios huérfanos en WordPress.

---

## 8. Preparar las publicaciones sociales

Sustituir `[WORDPRESS_URL]` por la URL definitiva.

### LinkedIn

Añadir:

`📖 Artículo completo: [URL]`

### Facebook

Añadir:

`🔗 Más info: [URL]`

### Instagram

Utilizar el texto específico preparado para Instagram/Facebook.

La URL puede mantenerse como referencia textual según las instrucciones del Copywriter.

### Threads

Añadir la URL únicamente si cabe dentro del límite establecido.

### X

Incluir la URL y verificar la longitud antes de publicar.

---

## 9. Elegir la URL de imagen para las RRSS

Orden de preferencia:

1. URL permanente de la imagen en WordPress.
2. Si no está disponible pero el bucket sigue vigente, URL pública temporal del bucket.

Nunca volver a utilizar la URL `chatgpt.com/s/...` para las APIs sociales.

---

## 10. LinkedIn

Publicar:

- texto específico de LinkedIn;
- URL del artículo;
- imagen.

Si falla OAuth:

- registrar error;
- no reintentar repetidamente;
- continuar con los demás canales.

---

## 11. Facebook

Publicar:

- texto específico de Facebook;
- URL del artículo;
- imagen.

Ante respuestas ambiguas o errores vacíos:

- comprobar primero si la publicación existe;
- no reintentar automáticamente.

---

## 12. Instagram

Instagram requiere imagen pública.

Publicar:

- caption preparado;
- imagen permanente de WordPress o, en su defecto, URL temporal todavía vigente.

Nunca enviar directamente la URL compartida de ChatGPT.

Si Instagram rechaza la imagen:

- registrar el error;
- no publicar una versión sin imagen;
- continuar con los canales restantes.

---

## 13. Threads

Threads se publica SIEMPRE solo con texto.

NO proporcionar `image_url`.

Publicar únicamente el contenido específico de Threads con la URL de WordPress si cabe.

---

## 14. X

Publicar como texto.

Incluir la URL del artículo.

Comprobar el límite de caracteres antes de enviar.

Si es necesario reducir longitud, recortar el texto, nunca eliminar la URL.

---

## 15. Gestión independiente de errores

Después de publicar correctamente WordPress, el fallo de una red social no debe detener las demás.

Ejemplo:

- WordPress: ✅
- LinkedIn: ❌ OAuth
- Facebook: ✅
- Instagram: ❌ API
- Threads: ✅
- X: ✅

No volver a publicar automáticamente en canales que ya hayan confirmado éxito.

---

## 16. Eliminar la imagen temporal

Una vez terminados todos los intentos de publicación, ejecutar:

`delete_temp_image`

utilizando el `object_name` devuelto originalmente por `upload_temp_image`.

No esperar al TTL salvo que la eliminación explícita falle.

La copia definitiva permanecerá almacenada en WordPress.

---

## 17. Registrar resultados

Actualizar el log de publicación indicando:

- fecha;
- noticia;
- URL WordPress;
- ID WordPress;
- URL permanente de imagen, cuando exista;
- estado de LinkedIn;
- estado de Facebook;
- estado de Instagram;
- estado de Threads;
- estado de X;
- IDs devueltos;
- errores completos.

---

## Regla de selección entre Publishers

### ChatGPT / OpenAI compatible

Si existe generación nativa de imágenes + enlace compartido `chatgpt.com/s/...`:

usar `06-chatgpt-publisher.md`.

### Otros agentes y entornos

Claude, automatizaciones externas, agentes sin ChatGPT Share o cualquier entorno incompatible:

usar `06-publisher.md`.

Nunca modificar el Publisher general para hacerlo depender de funcionalidades exclusivas de ChatGPT.

---

## Resumen visual

`ChatGPT/OpenAI`

↓

`Generar imagen`

↓

`Aprobación`

↓

`ChatGPT Share`

↓

`https://chatgpt.com/s/...`

↓

`Social-Mcps-Cloud.upload_temp_image`

↓

`Bucket temporal`

↓

`URL pública JPEG`

↓

`WordPress + imagen`

↓

`Artículo + imagen permanente`

↓

`WORDPRESS_URL`

↓

`LinkedIn + imagen`

`Facebook + imagen`

`Instagram + imagen`

`Threads → solo texto`

`X → solo texto`

↓

`delete_temp_image`

↓

`Registrar resultados`

↓

`FIN`

---

## Principio fundamental

En ChatGPT: OpenAI genera la imagen, ChatGPT proporciona el origen compartido, el bucket temporal actúa como puente y WordPress convierte la imagen en un recurso permanente.

Este procedimiento es una especialización del Publisher general y nunca debe sustituirlo en otros entornos.
