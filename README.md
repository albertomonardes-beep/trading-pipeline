# Trading Pipeline

Sistema automatizado de recopilacion, almacenamiento y visualizacion de datos de precios semanales de acciones y ETFs del mercado estadounidense.

## Objetivo

Filtrar ~9.000 instrumentos cada semana y generar una watchlist de 4-5 acciones accionables, basada en condiciones de mercado y criterios individuales por instrumento.

## Stack tecnologico

| Componente | Tecnologia | Costo |
|---|---|---|
| Fuente de datos | yfinance + NASDAQ CSV | Gratuito |
| Base de datos | MongoDB Atlas M0 | Gratuito |
| Scheduler | GitHub Actions | Gratuito |
| Interfaz | Streamlit Community Cloud | Gratuito |

## Universo de instrumentos

- ~5.000-6.000 acciones (NYSE, NASDAQ, AMEX)
- ~3.000 ETFs
- Total: ~9.000 instrumentos

## Arquitectura de base de datos (MongoDB)

### Coleccion `tickers`
Metadata de cada instrumento.

```json
{
  "ticker": "AAPL",
  "name": "Apple Inc.",
  "exchange": "NASDAQ",
  "capital_com": true,
  "pepperstone": false
}
```

### Coleccion `weekly_prices`
Foto semanal de precios OHLCV. Se sobreescribe cada semana (no acumula historial).

```json
{
  "ticker": "AAPL",
  "open": 189.50,
  "high": 192.30,
  "low": 187.10,
  "close": 191.20,
  "volume": 58000000
}
```

### Coleccion `market_data`
Indicadores macro: indices, volatilidad, ETFs de sectores.

## Logica de filtrado (2 niveles)

1. **Nivel mercado**: evalua condiciones generales del mercado
2. **Nivel instrumento**: filtra activos individuales dentro de mercados favorables

Resultado: watchlist semanal de 4-5 acciones para revisar

## Campos especiales en `tickers`

- `capital_com`: indica si el instrumento esta disponible para tradear en Capital.com (actualizado via API mensualmente)
- `pepperstone`: indica si el instrumento esta disponible en Pepperstone (actualizado via web scraping mensualmente)

## Configuracion

### Secretos de GitHub Actions requeridos

| Secreto | Descripcion |
|---|---|
| `MONGODB_URI` | Connection string de MongoDB Atlas |

### Variables en el codigo

| Variable | Valor |
|---|---|
| `DB_NAME` | `trading` |

## Estado del proyecto

- [x] Repositorio creado
- [x] Dependencias instaladas
- [x] Conexion a MongoDB Atlas configurada
- [x] Colecciones creadas (tickers, weekly_prices, market_data)
- [ ] Script de carga de tickers
- [ ] Script de descarga de precios semanales
- [ ] Script de datos de mercado
- [ ] Filtros de watchlist
- [ ] GitHub Actions scheduler
- [ ] Interfaz Streamlit
- [ ] Integracion Capital.com API
- [ ] Integracion Pepperstone scraping
