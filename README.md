# xbox-stock-bot

Monitorea Falabella, Paris, Ripley, Lider, Microplay, Weplay, PC Factory, SP Digital y Mercado Libre (solo nuevos) y avisa cuando hay stock de **Xbox Series X 1TB** o **Series X Digital Edition (blanca)** bajo `MAX_PRICE` (por defecto $900.000 CLP).

Excluye Series S, 2TB Galaxy, usados/reacondicionados y accesorios. Las consolas en bundle (consola + juego) se consideran.

## Fuentes

- **SoloTodo (API publica)**: fuente principal. Funciona desde GitHub Actions y cubre Falabella, Paris, Ripley, Lider, PC Factory, SP Digital, Mercado Libre y otras. Sus datos pueden tener algunas horas de atraso respecto de la tienda.
- **Scraping directo (Playwright)**: en GitHub solo Falabella responde (`STORES=falabella`); el resto bloquea IPs de centros de datos. En un PC local puede usarse con todas las tiendas.

Variables: `NOTIFY_EVERY_RUN=0` desactiva el resumen de cada revision, `SUMMARY_PRIORITY=low` lo deja silencioso, `SOLOTODO=0` desactiva SoloTodo, `STORES=none` desactiva el scraping, `STORES=falabella,ripley` limita tiendas.

## Estructura

```
bot/
  config.py      tiendas, URLs de busqueda, precio maximo
  filters.py     reglas de modelo, precio y stock
  scraper.py     Playwright + extractor generico (tarjetas y JSON-LD)
  solotodo.py    cliente de la API publica de SoloTodo
  state.py       deduplicacion de alertas y archivos data/*.json
  notifiers.py   ntfy y Telegram (extensible)
  main.py        entrypoint
data/
  state.json     ultimo estado por producto
  alerts.json    historial de alertas (lo lee la tarea programada de Claude)
  status.json    salud por tienda en cada ejecucion
```

## Local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
python -m playwright install chromium
python -m bot.main --debug --dry-run
STORES=falabella,ripley python -m bot.main --debug --dry-run
pytest -q
```

## GitHub Actions

1. Crea un repo **publico** y sube este proyecto (en repos publicos los minutos de Actions son gratis; en privado, cada 15 min supera los 2.000 min/mes gratuitos, cambia el cron a `0 * * * *`).
2. Settings > Actions > General > Workflow permissions: **Read and write**.
3. Opcional, Settings > Secrets and variables > Actions:
   - Secret `NTFY_TOPIC`: nombre de topico unico y dificil de adivinar (ej. `xbox-jvr-8f3k2`). Instala la app ntfy y suscribete a ese topico: aviso instantaneo.
   - Secrets `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID` si prefieres Telegram.
   - Variable `MAX_PRICE` para cambiar el tope.
4. Actions > check-stock > Run workflow con `debug` activado para validar que cada tienda devuelve consolas. Revisa `data/status.json`.

GitHub ejecuta el cron con retrasos de algunos minutos y lo deshabilita tras 60 dias sin actividad en el repo.

## Aviso en la app de Claude

Un script no puede enviar push directo a la app de Claude. La integracion se hace con una tarea programada de Claude (cada hora) que lee `data/alerts.json` desde `raw.githubusercontent.com` y te envia notificacion push si hay alertas nuevas. Para avisos inmediatos usa ntfy o Telegram en paralelo.

## Ajustes

- Si una tienda aparece con `candidates: 0` en `status.json`, abre su URL de busqueda en el navegador, copia la URL real de resultados y actualizala en `config.py`.
- Si una tienda carga lento, sube `extra_wait_ms` o define `wait_selector` en su `Store`.
- Lider, SP Digital y Paris usan protecciones anti-bot que a veces bloquean IPs de GitHub; el bot registra el error y sigue con las demas.
- Nuevo canal: crea una clase que herede de `Notifier` y agregala a `NOTIFIERS`.
