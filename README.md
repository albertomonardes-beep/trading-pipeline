# Trading Pipeline

Sistema automatizado de recopilacion, almacenamiento y visualizacion de datos de precios de acciones y ETFs del mercado estadounidense.

## Objetivo

Filtrar ~9.000 instrumentos cada semana y generar una watchlist de 4-5 acciones accionables, basada en condiciones de mercado y criterios individuales por instrumento.

## Stack tecnologico

| Componente | Tecnologia | Costo |
|---|---|---|
| Fuente de datos | yfinance + NASDAQ CSV publico | Gratuito |
| Base de datos | MongoDB Atlas M0 | Gratuito |
| Scheduler | GitHub Actions | Gratuito |
| Interfaz | Streamlit Community Cloud | Gratuito |

## Universo de instrumentos

- ~5.000-6.000 acciones (NYSE, NASDAQ, AMEX)
- ~3.000 ETFs
- Total: ~9.000 instrumentos
- Fuente: archivos publicos de NASDAQ Trader (`nasdaqlisted.txt`, `otherlisted.txt`)

---

## Arquitectura de base de datos (MongoDB)

### Coleccion `tickers`
Metadata de cada instrumento. Se actualiza mensualmente desde NASDAQ Trader.

```json
{
  "ticker": "AAPL",
  "name": "Apple Inc.",
  "exchange": "NASDAQ",
  "is_etf": false
}
```

### Coleccion `weekly_snapshot`
Un documento por ticker, sobreescrito cada semana. Contiene todos los datos tecnicos, fundamentales y de disponibilidad en brokers.

```json
{
  "ticker": "AAPL",
  "name": "Apple Inc.",
  "exchange": "NASDAQ",
  "is_etf": false,
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "capital_com": true,
  "pepperstone": false,
  "price": 191.20,
  "ema21": 185.50,
  "sma50": 180.20,
  "sma200": 175.10,
  "volume": 58000000,
  "market_cap": 2950000,
  "revenue": [94930, 90753, 119575],
  "revenue_growth": 4.6,
  "earnings": [24160, 23636, 29000],
  "earnings_growth": 2.2,
  "roe": 0.45,
  "pe": 28.5,
  "peg": 1.8,
  "debt_equity": 1.5,
  "current_ratio": 1.07,
  "fcf": [22000, 20000, 25000],
  "fcf_growth": 10.0,
  "updated_at": "2026-05-18"
}
```

#### Descripcion de campos

| Campo | Tipo | Frecuencia | Descripcion |
|---|---|---|---|
| `ticker` | string | — | Simbolo del instrumento |
| `name` | string | Semanal | Nombre del instrumento |
| `exchange` | string | Semanal | Bolsa donde cotiza |
| `is_etf` | bool | Semanal | True si es ETF |
| `sector` | string | Semanal | Sector GICS |
| `industry` | string | Semanal | Sub-sector GICS |
| `capital_com` | bool | Semanal | Disponible en Capital.com (lookup CSV) |
| `pepperstone` | bool | Semanal | Disponible en Pepperstone (lookup CSV) |
| `price` | float | Semanal | Precio de cierre de la ultima vela diaria |
| `ema21` | float | Semanal | EMA 21 dias (calculado desde historico diario) |
| `sma50` | float | Semanal | SMA 50 dias |
| `sma200` | float | Semanal | SMA 200 dias |
| `volume` | int | Semanal | Volumen de la ultima vela diaria |
| `market_cap` | float | Semanal | Capitalizacion de mercado en MM USD |
| `revenue` | list[float] | Anual | Ingresos ultimos 3 anos en MM USD (mas reciente primero) |
| `revenue_growth` | float | Anual | Crecimiento ingresos del ano mas antiguo al mas reciente (%) |
| `earnings` | list[float] | Anual | Ganancias netas ultimos 3 anos en MM USD |
| `earnings_growth` | float | Anual | Crecimiento ganancias (%) |
| `roe` | float | Anual | Return on Equity |
| `pe` | float | Anual | Price/Earnings (trailing) |
| `peg` | float | Anual | PEG ratio |
| `debt_equity` | float | Anual | Deuda/Patrimonio |
| `current_ratio` | float | Anual | Ratio corriente |
| `fcf` | list[float] | Anual | Free Cash Flow (OCF - CapEx) ultimos 3 anos en MM USD |
| `fcf_growth` | float | Anual | Crecimiento FCF (%) |
| `updated_at` | string | Semanal | Fecha del ultimo update (UTC, formato YYYY-MM-DD) |

### Coleccion `market_data`
Un documento por instrumento de mercado, sobreescrito cada semana. Cubre indices de mercado amplio, volatilidad y ETFs sectoriales.

Instrumentos:
- Mercado amplio: SPY, QQQ, DIA, IWM
- Volatilidad: ^VIX
- Sectores SPDR: XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLU, XLRE, XLC, XLB

---

## Disponibilidad en brokers

Los campos `capital_com` y `pepperstone` se resuelven por lookup en archivos CSV locales:

- `data/capital_com_list.csv` — columna: `ticker`
- `data/pepperstone_list.csv` — columna: `ticker`

Estos archivos se mantienen manualmente. No se requiere API ni scraping. El script hace un simple lookup de si el ticker aparece en la lista o no.

---

## Scripts

### `scripts/setup_db.py`
Crea las colecciones en MongoDB con sus indices. Idempotente: no sobreescribe si ya existen.

```bash
python scripts/setup_db.py
```

Colecciones creadas:
- `tickers` (indice unico en `ticker`)
- `weekly_snapshot` (indice unico en `ticker`)
- `market_data` (indice unico en `ticker`)

### `scripts/load_tickers.py`
Descarga el universo de tickers desde NASDAQ Trader y los inserta/actualiza en la coleccion `tickers`. Se ejecuta mensualmente via GitHub Actions.

```bash
python scripts/load_tickers.py
```

- Fuentes: `nasdaqlisted.txt` (NASDAQ) + `otherlisted.txt` (NYSE, AMEX, NYSE Arca)
- Filtra warrants (`$`) e indices (`^`)
- Convierte notacion NASDAQ (`BRK.B`) a notacion yfinance (`BRK-B`)
- Deduplicacion por ticker
- Upsert: no sobreescribe `capital_com` ni `pepperstone` si ya existen

### `scripts/fetch_market_data.py`
Descarga datos de los 16 instrumentos de mercado (indices + sectores) y hace upsert en `market_data`. Se ejecuta semanalmente via GitHub Actions.

```bash
python scripts/fetch_market_data.py
```

- Intervalo: diario (`1d`), historico de 1 ano
- Calcula EMA21, SMA50, SMA200 desde historico; guarda solo el valor actual
- Guarda flags booleanos `above_ema21`, `above_sma50`, `above_sma200`
- Calcula variacion porcentual semanal

### `scripts/fetch_weekly_snapshot.py`
Para cada ticker en la coleccion `tickers`, descarga todos los campos de `weekly_snapshot` y hace upsert en MongoDB. Se ejecuta semanalmente via GitHub Actions.

```bash
# Todos los tickers (~9.000, tarda varias horas)
python scripts/fetch_weekly_snapshot.py

# Solo los primeros N tickers (para pruebas)
python scripts/fetch_weekly_snapshot.py --test 50

# Tamano de lote personalizado
python scripts/fetch_weekly_snapshot.py --batch-size 200
```

Logica interna:
- Descarga precios diarios en bulk por lotes de 100 tickers (una sola llamada a yfinance por lote)
- Historico de 1 ano (`1y`), suficiente para calcular SMA200 diaria (~252 dias habiles)
- Calcula EMA21, SMA50, SMA200 desde historico; guarda solo el valor actual
- Descarga fundamentales anuales via `ticker.info`, `income_stmt`, `cashflow`
- FCF calculado como OCF + |CapEx| (CapEx viene negativo en yfinance)
- Delay de 3s entre lotes para respetar rate limit de Yahoo Finance
- Campos no disponibles quedan como `null`; el script no interrumpe por errores de un ticker

### `app.py`
Interfaz Streamlit que muestra el contenido de `weekly_snapshot` en una tabla interactiva con todas las columnas definidas.

```bash
streamlit run app.py
```

---

## GitHub Actions

### `weekly_snapshot.yml`
Se ejecuta cada sabado a las 10am UTC (tras el cierre del viernes en NY). Orden de ejecucion:
1. `setup_db.py`
2. `fetch_market_data.py`
3. `fetch_weekly_snapshot.py`

### `monthly_tickers.yml`
Se ejecuta el dia 1 de cada mes a las 6am UTC:
1. `setup_db.py`
2. `load_tickers.py`

Ambos workflows tienen `workflow_dispatch` para ejecucion manual desde GitHub.

---

## Logica de filtrado (pendiente)

Dos niveles:

1. **Nivel mercado**: analisis de condiciones generales por sector y sub-sector (VIX, SPY, ETFs sectoriales)
2. **Nivel instrumento**: revision manual sobre la tabla Streamlit

Resultado: watchlist semanal de 4-5 instrumentos.

---

## Configuracion

### Variables de entorno requeridas

| Variable | Descripcion |
|---|---|
| `MONGODB_URI` | Connection string de MongoDB Atlas |

### Variables en el codigo (`setup_db.py`)

| Variable | Valor |
|---|---|
| `DB_NAME` | `trading` |

### Secretos de GitHub Actions requeridos

| Secreto | Descripcion |
|---|---|
| `MONGODB_URI` | Connection string de MongoDB Atlas |

---

## Instalacion

```bash
pip install -r requirements.txt
```

```
pymongo==4.7.2
requests==2.32.3
pandas==2.2.2
yfinance==0.2.40
streamlit==1.35.0
```

---

## Estado del proyecto

- [x] Repositorio creado
- [x] Dependencias definidas (`requirements.txt`)
- [x] Conexion a MongoDB Atlas configurada
- [x] Coleccion `tickers` creada con indice unico
- [x] Coleccion `weekly_snapshot` creada con indice unico
- [x] Coleccion `market_data` creada con indice unico
- [x] Script de carga de tickers (`load_tickers.py`)
- [x] Script de datos de mercado (`fetch_market_data.py`)
- [x] Script de snapshot semanal (`fetch_weekly_snapshot.py`)
  - [x] Precios y volumen (velas diarias)
  - [x] EMA21, SMA50, SMA200 diarias calculadas
  - [x] Sector, sub-sector, market cap
  - [x] Disponibilidad Capital.com / Pepperstone (lookup CSV)
  - [x] Revenue, Earnings, FCF (ultimos 3 anos, en MM USD)
  - [x] Crecimientos de revenue, earnings y FCF
  - [x] ROE, P/E, PEG, Debt/Equity, Current Ratio
- [x] GitHub Actions scheduler (semanal + mensual)
- [x] Interfaz Streamlit (`app.py`)
- [ ] Logica de nivel 1: analisis de mercado por sector/sub-sector

---

## Decisiones de diseno

- **Una sola coleccion `weekly_snapshot`**: en lugar de separar precios, fundamentales y metadata en colecciones distintas, todo se consolida en un unico documento por ticker. Simplifica las queries de Streamlit.
- **Sobreescritura semanal**: el snapshot no acumula historial. Se sobreescribe cada semana. Los indicadores (EMA, SMA) se calculan al vuelo desde yfinance y solo se persiste el valor actual.
- **Datos financieros anuales**: revenue, earnings y FCF corresponden a los ultimos 3 anos fiscales completos. Mas representativos que trimestres para evaluar tendencia del negocio.
- **Velas diarias**: precios e indicadores tecnicos en temporalidad diaria (swing trading). Historico de 1 ano suficiente para calcular SMA200.
- **Brokers sin API**: la disponibilidad en Capital.com y Pepperstone se resuelve con un lookup en archivos CSV locales. No se requiere scraping ni API key. El usuario actualiza los CSV cuando cambia la oferta de los brokers.
- **Tickers desde NASDAQ Trader**: fuente publica y gratuita que cubre NYSE, NASDAQ, AMEX y ETFs. Se descargan directamente sin intermediarios.
