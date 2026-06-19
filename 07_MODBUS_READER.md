# modbus-reader — Daemon C con libmodbus

> **ESTADO: LEGACY — REEMPLAZADO POR siser-reader (Python)** — Este daemon C fue reemplazado por `siser-reader` porque el protocolo real del inversor es SISER (Phoenixtec), no Modbus RTU. El código se conserva como referencia histórica pero **NO se usa en producción**. El daemon en producción es `siser_reader.py` (ver directorio `Proyecto/siser-reader/`).
>
> **ADVERTENCIA**: No intentar ejecutar este daemon en producción. El inversor no habla Modbus RTU y la comunicación fallará. Además, el esquema de base de datos ha cambiado (columnas SISER: vpv1-3, ipv1-3, ppv1-3, etc.) y las queries y dashboards actuales no son compatibles con este código. Para el daemon actual, ver `siser_reader.py`.

## Objetivo

Daemon en C que lee registros Modbus RTU del inversor Riello H.P.6065REL-D via RS232 (adaptador CH340 USB-RS232) y escribe los datos en TimescaleDB. Diseñado para ser robusto: reconexión automática ante desconexión USB, timeouts, y caídas de base de datos.

---

## Arquitectura

```
main.c (event loop, señales)
    │
    ├── modbus_comm.c/.h  ← libmodbus (comunicación serial)
    │   ├── modbus_new_rtu()           → abrir puerto
    │   ├── modbus_read_registers()    → leer registros
    │   ├── modbus_connect/disconnect   → reconexión
    │   └── watchdog de puerto serial   → detectar USB desconectado
    │
    ├── register_map.c/.h  ← mapa de registros del Riello H.P.6065REL-D
    │   ├── register_entry_t           → struct con address, name, unit, scale, table
    │   └── register_map[]              → array de registros (se llena post RE)
    │
    ├── db_writer.c/.h  ← libpq (escritura a TimescaleDB)
    │   ├── PQconnectdb()              → conectar a DB
    │   ├── PQexecParams()             → INSERT con parámetros
    │   └── buffer circular (1000)     → si DB no disponible
    │
    ├── config.c/.h  ← configuración via variables de entorno
    │
    └── watchdog.c/.h  ← monitoreo de salud
        ├── última lectura exitosa
        ├── conteo de errores
        └── health check endpoint (archivo PID)
```

---

## Estructura de Archivos

```
modbus-reader/
  ├── src/
  │   ├── main.c              # Event loop principal, manejo de señales
  │   ├── modbus_comm.c        # Comunicación Modbus RTU
  │   ├── modbus_comm.h
  │   ├── db_writer.c          # Escritura a TimescaleDB
  │   ├── db_writer.h
  │   ├── register_map.c       # Mapa de registros
  │   ├── register_map.h
  │   ├── config.c             # Configuración desde env vars
  │   ├── config.h
  │   ├── watchdog.c            # Monitoreo de salud
  │   └── watchdog.h
  ├── Makefile
  └── Dockerfile
```

---

## Dependencias

```bash
sudo apt-get install libmodbus-dev libpq-dev gcc make cmake
```

| Librería | Paquete | Uso |
|---|---|---|
| libmodbus | libmodbus-dev | Comunicación Modbus RTU |
| libpq | libpq-dev | Conexión a PostgreSQL/TimescaleDB |
| gcc/make | build-essential | Compilación |

---

## Makefile

```makefile
CC = gcc
CFLAGS = -Wall -Wextra -O2 -I/usr/include/postgresql -I/usr/include/modbus -I/opt/homebrew/opt/libpq/include -I/opt/homebrew/opt/libmodbus/include
LDFLAGS = -lmodbus -lpq -L/opt/homebrew/opt/libpq/lib -L/opt/homebrew/opt/libmodbus/lib

SRCS = src/main.c src/modbus_comm.c src/db_writer.c src/register_map.c src/config.c src/watchdog.c
OBJS = $(SRCS:.c=.o)
TARGET = modbus-reader

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(OBJS) -o $(TARGET) $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all clean
```

---

## Dockerfile (multi-stage)

```dockerfile
# Stage 1: Compilar
FROM gcc:12-bookworm AS builder

RUN apt-get update && apt-get install -y \
    libmodbus-dev libpq-dev make

WORKDIR /build
COPY src/ src/
COPY Makefile .

RUN make clean && make

# Stage 2: Runtime mínimo
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    libmodbus5 libpq5 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/modbus-reader /usr/local/bin/modbus-reader

ENTRYPOINT ["modbus-reader"]
```

---

## Mapa de Registros (`register_map.h`)

```c
#ifndef REGISTER_MAP_H
#define REGISTER_MAP_H

#include <stdint.h>

typedef enum {
    TABLE_REALTIME,
    TABLE_FAST_SAMPLES,
    TABLE_CUMULATIVES,
    TABLE_DAILY_PRODUCTION
} target_table_t;

typedef struct {
    uint16_t address;
    uint16_t count;
    const char *name;
    const char *unit;
    float scale;
    target_table_t table;
} register_entry_t;

/*
 * Mapa de registros del Riello H.P.6065REL-D
 * SE LLENA DESPUES DEL REVERSE ENGINEERING
 * Los registros de abajo son placeholders basados en RSTool (RS 3.0)
 * y pueden diferir del H.P.6065REL-D
 *
 * NOTA: No hay TABLE_SLOW_SAMPLES aquí. Los datos de 15 min los genera
 * TimescaleDB automáticamente como continuous aggregate de fast_samples.
 */
/* Array definition is in register_map.c — extern declarations only in this header */
extern const register_entry_t register_map[];
extern const int register_map_size;

#endif /* REGISTER_MAP_H */
```

> **IMPORTANTE**: Los registros con `address = 0x0000` son placeholders. Se completarán después del reverse engineering del protocolo (ver [[05_REVERSE_ENGINEERING]]).

---

## Configuración (`config.h`)

```c
#ifndef CONFIG_H
#define CONFIG_H

#include <stdint.h>

typedef struct {
    /* Serial */
    const char *serial_port;
    int baudrate;
    char parity;
    int stopbits;
    int bytesize;
    int slave_address;

    /* Polling intervals (seconds) */
    int poll_realtime;
    int poll_fast;

    /* Database */
    const char *db_host;
    int db_port;
    const char *db_name;
    const char *db_user;
    const char *db_password;

    /* Buffer */
    int buffer_size;
} config_t;

config_t *config_from_env(void);
void config_free(config_t *cfg);

#endif /* CONFIG_H */
```

Variables de entorno (mapeadas desde docker-compose):

| Variable | Default | Descripción |
|---|---|---|
| `SERIAL_PORT` | /dev/inverter-serial | Puerto serial |
| `SLAVE_ADDRESS` | 1 | Dirección Modbus del inversor (default H.P.6065REL-D) |
| `BAUDRATE` | 9600 | Velocidad serial (RS232, default H.P.6065REL-D) |
| `PARITY` | N | Paridad (N=none, E=even, O=odd) |
| `STOPBITS` | 1 | Stop bits |
| `BYTESIZE` | 8 | Data bits |
| `POLL_REALTIME` | 5 | Intervalo tiempo real (seg) |
| `POLL_FAST` | 60 | Intervalo muestras rápidas (seg) |
| `DB_HOST` | timescaledb | Host de la base de datos |
| `DB_PORT` | 5432 | Puerto de la base de datos |
| `DB_NAME` | solar_monitor | Nombre de la base de datos |
| `DB_USER` | solar | Usuario de la base de datos |
| `DB_PASSWORD` | (requerido) | Password de la base de datos |
| `BUFFER_SIZE` | 1000 | Buffer circular en memoria |

> **Nota**: `POLL_SLOW` eliminado. Los datos de 15 min (`slow_samples`) los genera TimescaleDB automáticamente como continuous aggregate desde `fast_samples`. El daemon no necesita ese intervalo.

---

## Secuencia de Unlock del Protocolo

El Riello H.P.6065REL-D implementa un bloqueo de protocolo. **Antes de poder leer cualquier registro de datos, es obligatorio desbloquear el inversor** escribiendo la contraseña de acceso.

### Por qué existe el bloqueo

Riello protege el acceso Modbus para que solo SunVision pueda leer el inversor. Sin el unlock, FC03 devuelve error o valores nulos.

### Secuencia de unlock

1. Conectar al inversor (modbus_connect)
2. Escribir `0x000000` (contraseña por defecto) en registros `0x003C`–`0x003D` usando FC06 (write single register) o FC10 (write multiple registers)
3. El inversor responde con ACK → los registros de datos quedan accesibles
4. La sesión queda desbloqueada mientras la conexión RS485 permanezca activa

```c
/* unlock en modbus_comm.c — llamar después de modbus_connect() */
static int helios_unlock(modbus_t *ctx) {
    uint16_t password[2] = {0x0000, 0x0000};  /* default: 0x000000 */
    int rc = modbus_write_registers(ctx, 0x003C, 2, password);
    if (rc == -1) {
        log_error("Unlock failed: %s", modbus_strerror(errno));
        return -1;
    }
    log_info("Inverter unlocked (Modbus protocol access granted)");
    return 0;
}
```

> **IMPORTANTE**: Si se cambia la contraseña desde el panel del inversor (menú de configuración RS485), el valor ya no será `0x000000`. En ese caso, hay que obtener la contraseña del operador del equipo o hacer un reset de fábrica del inversor.

---

## Estrategia de Reconexión USB

### Problema original

SunVision en Windows perdía la conexión USB al adaptador RS232. Esto se debe a:
1. El adaptador CH340 USB-RS232 se desconecta físicamente (cable suelto)
2. El kernel desmonta el dispositivo `/dev/inverter-serial`
3. El software no recupera la conexión

### Solución en el daemon C

```c
/* Pseudocódigo de la estrategia de reconexión */

while (running) {
    /* Intentar abrir el puerto serial */
    ctx = modbus_new_rtu(serial_port, baudrate, parity, bytesize, stopbits);
    if (ctx == NULL) {
        log_error("No se pudo crear contexto Modbus");
        sleep(RETRY_INTERVAL);
        continue;
    }

    modbus_set_slave(ctx, slave_address);
    modbus_set_response_timeout(ctx, 1, 0);  /* 1 segundo timeout */

    if (modbus_connect(ctx) == -1) {
        log_error("No se pudo conectar: %s", modbus_strerror(errno));
        modbus_free(ctx);
        sleep(backoff_get());  /* Backoff: 5s → 10s → 30s → 60s → 5min max */
        continue;
    }

    backoff_reset();  /* Conexión exitosa, resetear backoff */

    /* Unlock obligatorio antes de leer cualquier registro */
    if (helios_unlock(ctx) == -1) {
        modbus_close(ctx);
        modbus_free(ctx);
        sleep(backoff_get());
        continue;
    }

    /* Loop de lectura */
    while (connected && running) {
        for (i = 0; i < REGISTER_MAP_SIZE; i++) {
            uint16_t regs[register_map[i].count];
            rc = modbus_read_registers(ctx,
                register_map[i].address,
                register_map[i].count,
                regs);

            if (rc == -1) {
                if (errno == ENXIO || errno == EIO) {
                    /* USB desconectado — salir del loop y reconectar */
                    log_error("USB desconectado, reconectando...");
                    connected = false;
                    break;
                }
                /* Timeout o error temporal — continuar con backoff */
                log_warn("Error de lectura: %s", modbus_strerror(errno));
                sleep(backoff_get());
                continue;
            }

            /* Escala y escribe en DB */
            float value = regs[0] * register_map[i].scale;
            db_write(register_map[i].table, register_map[i].name, value, register_map[i].unit);
        }

        sleep(poll_interval);
    }

    modbus_close(ctx);
    modbus_free(ctx);
}
```

### Backoff exponencial

| Intento | Espera |
|---|---|
| 1 | 5 seg |
| 2 | 10 seg |
| 3 | 30 seg |
| 4 | 60 seg |
| 5+ | 5 min (máximo) |

### Buffer circular en memoria

Si TimescaleDB no está disponible, el daemon guarda las últimas 1000 lecturas en un buffer circular en memoria. Cuando la DB se recupera, vuelca el buffer. Esto garantiza que no se pierden datos durante reinicios de la DB.

---

## Manejo de Señales

| Señal | Acción |
|---|---|
| SIGTERM | Graceful shutdown: cerrar Modbus, volcar buffer, cerrar DB |
| SIGHUP | Reload de configuración (no implementado aún) |
| SIGUSR1 | Volcar buffer circular a DB (forzado) |

---

## Logging

El daemon escribe a stdout (Docker lo captura con `docker logs`). Formato:

```
[2024-01-15 10:23:45] INFO  Connected to /dev/inverter-serial (9600,8N1,slave 1)
[2024-01-15 10:23:50] READ  temperature=42.3°C
[2024-01-15 10:23:50] READ  power_ac=2807.0W
[2024-01-15 10:23:50] WRITE realtime: 2 rows inserted
[2024-01-15 10:24:15] WARN  Modbus timeout, retrying in 10s...
[2024-01-15 10:24:25] INFO  Reconnected to /dev/inverter-serial
[2024-01-15 10:25:00] ERROR USB disconnected, reconnecting...
[2024-01-15 10:25:05] INFO  Reconnected to /dev/inverter-serial
```

---

## Health Check

El daemon escribe un archivo JSON cada 30 segundos con el estado del sistema:

```json
{
  "status": "ok",
  "last_reading": "2024-01-15T10:23:50Z",
  "modbus_connected": true,
  "db_connected": true,
  "readings_total": 12345,
  "errors_total": 3,
  "buffer_size": 0,
  "uptime_seconds": 86400
}
```

Ubicación: `/tmp/modbus-reader-health.json`

Docker health check:

```yaml
healthcheck:
  test: ["CMD", "sh", "-c", "cat /tmp/modbus-reader-health.json | grep -q '\"status\":\"ok\"'"]
  interval: 30s
  timeout: 10s
  retries: 3
```

---

## Comandos de Debugging

```bash
# Ver logs del daemon
docker compose logs -f modbus-reader

# Ver estado de salud
cat /tmp/modbus-reader-health.json

# Probar comunicación Modbus manualmente
# (instalar modbus-client o usar mbpoll)
mbpoll -a 1 -b 9600 -p none -t 3 -r 0x101C -c 1 /dev/inverter-serial

# Verificar que el adaptador CH340 USB-RS232 está detectado
ls -la /dev/inverter-serial
dmesg | grep ttyUSB

# Strace para debuggear comunicación serial
docker exec -it solar-monitor-modbus-reader-1 strace -e trace=open,read,write -p 1
```

---

## Troubleshooting

| Problema | Causa | Solución |
|---|---|---|
| `No se pudo crear contexto Modbus` | libmodbus no instalada | `apt-get install libmodbus-dev` |
| `No se pudo conectar a /dev/inverter-serial` | Adaptador no conectado | Verificar con `ls /dev/inverter-serial` |
| Adaptador no aparece como `/dev/inverter-serial` | Driver no cargado | `dmesg | grep ttyUSB`, verificar regla udev, CH340 necesita driver `ch341` |
| `Modbus timeout` | Inversor no responde | Verificar cable RS232 (TX/RX/GND), dirección slave, baudrate |
| Respuesta errática | Cable RS232 cruzado | Verificar TX/RX (cruzar), GND conectado |
| `DB connection failed` | TimescaleDB no arrancó | `docker compose logs timescaledb` |
| Buffer crece sin parar | DB no disponible persistente | Verificar TimescaleDB, reconectar |

---

## Compilación Manual (sin Docker)

```bash
cd modbus-reader/
make clean && make
./modbus-reader
```

Variables de entorno necesarias:

```bash
export SERIAL_PORT=/dev/inverter-serial
export SLAVE_ADDRESS=1
export BAUDRATE=9600
export PARITY=N
export STOPBITS=1
export BYTESIZE=8
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=solar_monitor
export DB_USER=solar
export DB_PASSWORD=tu_password
```

---

## Implementación — Código Fuente Completo

> Los archivos `.h` (register_map.h, config.h) ya están documentados arriba. A continuación se agregan todos los archivos `.c` y headers adicionales necesarios para compilar y ejecutar el daemon. Los registros Modbus marcados como `address = 0x0000` son placeholders y se actualizarán después del reverse engineering.

---

### `src/logger.h` — Macros de Logging

```c
#ifndef LOGGER_H
#define LOGGER_H

#include <stdio.h>
#include <stdarg.h>
#include <time.h>

#define LOG_COLOR_RED     "\033[31m"
#define LOG_COLOR_YELLOW  "\033[33m"
#define LOG_COLOR_GREEN   "\033[32m"
#define LOG_COLOR_RESET   "\033[0m"

static inline void log_timestamp(void) {
    char buf[32];
    time_t now = time(NULL);
    struct tm *tm_info = gmtime(&now);
    strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", tm_info);
    fprintf(stdout, "[%s] ", buf);
}

#define log_error(fmt, ...) do { \
    log_timestamp(); \
    fprintf(stdout, LOG_COLOR_RED "ERROR " LOG_COLOR_RESET fmt "\n", ##__VA_ARGS__); \
    fflush(stdout); \
} while (0)

#define log_warn(fmt, ...) do { \
    log_timestamp(); \
    fprintf(stdout, LOG_COLOR_YELLOW "WARN  " LOG_COLOR_RESET fmt "\n", ##__VA_ARGS__); \
    fflush(stdout); \
} while (0)

#define log_info(fmt, ...) do { \
    log_timestamp(); \
    fprintf(stdout, LOG_COLOR_GREEN "INFO  " LOG_COLOR_RESET fmt "\n", ##__VA_ARGS__); \
    fflush(stdout); \
} while (0)

#define log_read(fmt, ...) do { \
    log_timestamp(); \
    fprintf(stdout, "READ  " fmt "\n", ##__VA_ARGS__); \
    fflush(stdout); \
} while (0)

#endif /* LOGGER_H */
```

---

### `src/config.c` — Implementación de Configuración desde Env Vars

```c
#include "config.h"
#include <stdlib.h>
#include <string.h>
#include "logger.h"

static const char *get_env_str(const char *name, const char *def) {
    const char *val = getenv(name);
    if (val == NULL || val[0] == '\0') return def;
    return val;
}

static int get_env_int(const char *name, int def) {
    const char *val = getenv(name);
    if (val == NULL || val[0] == '\0') return def;
    return atoi(val);
}

config_t *config_from_env(void) {
    config_t *cfg = malloc(sizeof(config_t));
    if (cfg == NULL) {
        log_error("Failed to allocate config");
        return NULL;
    }

    cfg->serial_port   = get_env_str("SERIAL_PORT",   "/dev/inverter-serial");
    cfg->baudrate      = get_env_int("BAUDRATE",      9600);
    cfg->parity        = get_env_str("PARITY",         "N")[0];
    cfg->stopbits      = get_env_int("STOPBITS",       1);
    cfg->bytesize      = get_env_int("BYTESIZE",       8);
    cfg->slave_address = get_env_int("SLAVE_ADDRESS",  1);
    cfg->poll_realtime = get_env_int("POLL_REALTIME",  5);
    cfg->poll_fast     = get_env_int("POLL_FAST",      60);
    cfg->db_host       = get_env_str("DB_HOST",        "timescaledb");
    cfg->db_port       = get_env_int("DB_PORT",        5432);
    cfg->db_name       = get_env_str("DB_NAME",        "solar_monitor");
    cfg->db_user       = get_env_str("DB_USER",        "solar");
    cfg->db_password   = get_env_str("DB_PASSWORD",    "");
    cfg->buffer_size   = get_env_int("BUFFER_SIZE",     1000);

    if (cfg->db_password[0] == '\0') {
        log_error("DB_PASSWORD environment variable is required");
        free(cfg);
        return NULL;
    }

    log_info("Config: %s %d %c%d%d slave=%d poll=%d/%ds db=%s:%d/%s",
             cfg->serial_port, cfg->baudrate, cfg->parity,
             cfg->bytesize, cfg->stopbits, cfg->slave_address,
             cfg->poll_realtime, cfg->poll_fast,
             cfg->db_host, cfg->db_port, cfg->db_name);

    return cfg;
}

void config_free(config_t *cfg) {
    if (cfg != NULL) {
        free(cfg);
    }
}
```

---

### `src/register_map.c` — Definición del Array de Registros

```c
#include "register_map.h"

/*
 * Mapa de registros del Riello H.P.6065REL-D
 *
 * Registros con address=0x0000 son PLACEHOLDERS.
 * Se completarán después del reverse engineering (ver 05_REVERSE_ENGINEERING.md).
 *
 * Orden de lectura: primero realtime (cada 5s), luego fast_samples (cada 60s),
 * luego cumulatives (cada 60s).
 *
 * El campo "count" indica cuántos registros Modbus leer consecutivamente.
 * Para valores de 32 bits (float, int32), se leen 2 registros.
 * El campo "scale" multiplica el valor crudo para obtener la unidad final.
 */

const register_entry_t register_map[] = {
    /* === Tiempo real — leídos cada 5 segundos === */
    {0x101C, 1, "temperature",    "C",   1.0,   TABLE_REALTIME},
    {0x1037, 2, "power_ac",       "W",   0.01,  TABLE_REALTIME},
    {0x1005, 1, "status",         "",    1.0,   TABLE_REALTIME},

    /* === Muestras rápidas — leídas cada 60 segundos === */
    {0x0000, 0, "vpv",            "V",   0.1,   TABLE_FAST_SAMPLES},   /* TBD */
    {0x0000, 0, "ipv",            "A",   0.01,  TABLE_FAST_SAMPLES},   /* TBD */
    {0x0000, 0, "vac",            "V",   0.1,   TABLE_FAST_SAMPLES},   /* TBD */
    {0x0000, 0, "iac",            "A",   0.01,  TABLE_FAST_SAMPLES},   /* TBD */
    {0x0000, 0, "fac",            "Hz",  0.01,  TABLE_FAST_SAMPLES},   /* TBD */

    /* Los campos de realtime también se escriben en fast_samples */
    /* (temperature, power_ac se duplican en ambas tablas) */

    /* === Acumulados — leídos cada 60 segundos === */
    {0x1021, 2, "energy_total",   "kWh", 0.01,  TABLE_CUMULATIVES},
    {0x0000, 0, "energy_daily",   "kWh", 0.01,  TABLE_CUMULATIVES},   /* TBD */
    {0x0000, 0, "hours_total",    "h",   0.01,  TABLE_CUMULATIVES},   /* TBD */
    {0x0000, 0, "co2_saved",      "kg",  0.01,  TABLE_CUMULATIVES},   /* TBD */

    /* === Gráfico diario — leído 1 vez al inicio del día === */
    {0xC000, 48, "daily_graph",   "W",   0.01,  TABLE_DAILY_PRODUCTION},
};

const int register_map_size = sizeof(register_map) / sizeof(register_map[0]);
```

---

### `src/modbus_comm.h` — Header de Comunicación Modbus

```c
#ifndef MODBUS_COMM_H
#define MODBUS_COMM_H

#include <modbus/modbus.h>
#include "config.h"

typedef struct {
    modbus_t *ctx;
    int connected;
    int slave_address;
    int backoff_seconds;
    int max_backoff;
} modbus_comm_t;

modbus_comm_t *modbus_comm_init(const config_t *cfg);
int modbus_comm_connect(modbus_comm_t *mc);
int modbus_comm_unlock(modbus_comm_t *mc);
int modbus_comm_read(modbus_comm_t *mc, uint16_t address, uint16_t count, uint16_t *dest);
void modbus_comm_disconnect(modbus_comm_t *mc);
void modbus_comm_free(modbus_comm_t *mc);
int modbus_comm_backoff_get(modbus_comm_t *mc);
void modbus_comm_backoff_reset(modbus_comm_t *mc);

#endif /* MODBUS_COMM_H */
```

---

### `src/modbus_comm.c` — Comunicación Modbus RTU

```c
#include "modbus_comm.h"
#include "logger.h"
#include <stdlib.h>
#include <errno.h>
#include <string.h>

#define BACKOFF_INITIAL 5
#define BACKOFF_MAX     300

modbus_comm_t *modbus_comm_init(const config_t *cfg) {
    modbus_comm_t *mc = malloc(sizeof(modbus_comm_t));
    if (mc == NULL) {
        log_error("Failed to allocate modbus_comm");
        return NULL;
    }

    mc->ctx = NULL;
    mc->connected = 0;
    mc->slave_address = cfg->slave_address;
    mc->backoff_seconds = BACKOFF_INITIAL;
    mc->max_backoff = BACKOFF_MAX;

    mc->ctx = modbus_new_rtu(cfg->serial_port, cfg->baudrate,
                              cfg->parity, cfg->bytesize, cfg->stopbits);
    if (mc->ctx == NULL) {
        log_error("Failed to create Modbus context: %s", modbus_strerror(errno));
        free(mc);
        return NULL;
    }

    modbus_set_slave(mc->ctx, mc->slave_address);
    modbus_set_response_timeout(mc->ctx, 1, 0);
    modbus_set_byte_timeout(mc->ctx, 0, 500000);

    log_info("Modbus context created: %s %d %c%d%d slave=%d",
             cfg->serial_port, cfg->baudrate, cfg->parity,
             cfg->bytesize, cfg->stopbits, mc->slave_address);

    return mc;
}

int modbus_comm_connect(modbus_comm_t *mc) {
    if (mc->ctx == NULL) return -1;

    if (modbus_connect(mc->ctx) == -1) {
        log_error("Modbus connect failed: %s", modbus_strerror(errno));
        return -1;
    }

    mc->connected = 1;
    log_info("Connected to serial port");
    return 0;
}

int modbus_comm_unlock(modbus_comm_t *mc) {
    if (!mc->connected) return -1;

    uint16_t password[2] = {0x0000, 0x0000};
    int rc = modbus_write_registers(mc->ctx, 0x003C, 2, password);
    if (rc == -1) {
        log_error("Unlock failed: %s", modbus_strerror(errno));
        return -1;
    }

    log_info("Inverter unlocked (Modbus protocol access granted)");
    return 0;
}

int modbus_comm_read(modbus_comm_t *mc, uint16_t address, uint16_t count, uint16_t *dest) {
    if (!mc->connected) return -1;

    int rc = modbus_read_registers(mc->ctx, address, count, dest);
    if (rc == -1) {
        if (errno == ENXIO || errno == EIO) {
            log_error("USB disconnected or device not responding at 0x%04X: %s",
                      address, modbus_strerror(errno));
            mc->connected = 0;
            return -2; /* -2 = disconnected, need reconnect */
        }
        log_warn("Modbus read error at 0x%04X: %s", address, modbus_strerror(errno));
        return -1; /* -1 = transient error, can retry */
    }

    return rc;
}

void modbus_comm_disconnect(modbus_comm_t *mc) {
    if (mc->ctx != NULL && mc->connected) {
        modbus_close(mc->ctx);
        mc->connected = 0;
        log_info("Disconnected from serial port");
    }
}

void modbus_comm_free(modbus_comm_t *mc) {
    if (mc == NULL) return;

    if (mc->ctx != NULL) {
        if (mc->connected) modbus_close(mc->ctx);
        modbus_free(mc->ctx);
    }

    free(mc);
}

int modbus_comm_backoff_get(modbus_comm_t *mc) {
    int current = mc->backoff_seconds;
    mc->backoff_seconds = mc->backoff_seconds * 2;
    if (mc->backoff_seconds > mc->max_backoff) {
        mc->backoff_seconds = mc->max_backoff;
    }
    return current;
}

void modbus_comm_backoff_reset(modbus_comm_t *mc) {
    mc->backoff_seconds = BACKOFF_INITIAL;
}
```

---

### `src/db_writer.h` — Header de Escritura a Base de Datos

```c
#ifndef DB_WRITER_H
#define DB_WRITER_H

#include <libpq-fe.h>
#include "config.h"
#include "register_map.h"

#define BUFFER_MAX_SIZE 1000

typedef struct {
    target_table_t table;
    char name[64];
    float value;
    char unit[16];
    char timestamp[32]; /* ISO 8601 */
} buffer_entry_t;

typedef struct {
    PGconn *conn;
    int connected;
    char conninfo[512];
    buffer_entry_t *buffer;
    int buffer_count;
    int buffer_size;
    long total_inserts;
    long total_errors;
} db_writer_t;

db_writer_t *db_writer_init(const config_t *cfg);
int db_writer_connect(db_writer_t *db);
void db_writer_disconnect(db_writer_t *db);
void db_writer_free(db_writer_t *db);

int db_writer_insert(db_writer_t *db, target_table_t table,
                     const char *name, float value,
                     const char *unit, int inverter_id);
int db_writer_flush_buffer(db_writer_t *db);
int db_writer_insert_event(db_writer_t *db, const char *event_type,
                            const char *event_value, int severity,
                            int inverter_id);

#endif /* DB_WRITER_H */
```

---

### `src/db_writer.c` — Escritura a TimescaleDB con Buffer Circular

```c
#include "db_writer.h"
#include "logger.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static const char *table_name_from_enum(target_table_t table) {
    switch (table) {
        case TABLE_REALTIME:          return "realtime";
        case TABLE_FAST_SAMPLES:      return "fast_samples";
        case TABLE_CUMULATIVES:       return "cumulatives";
        case TABLE_DAILY_PRODUCTION:  return "daily_production";
        default:                       return NULL;
    }
}

static int is_allowed_column(const char *name) {
    static const char *allowed_columns[] = {
        "temperature", "power_ac", "status",
        "vpv", "ipv", "vac", "iac", "fac", "power_dc",
        "energy_total", "energy_daily", "hours_total", "co2_saved",
        "daily_graph",
        NULL
    };
    for (int i = 0; allowed_columns[i] != NULL; i++) {
        if (strcmp(name, allowed_columns[i]) == 0) return 1;
    }
    return 0;
}

static void iso8601_now(char *buf, size_t len) {
    time_t now = time(NULL);
    struct tm *tm_info = gmtime(&now);
    strftime(buf, len, "%Y-%m-%dT%H:%M:%S", tm_info);
}

db_writer_t *db_writer_init(const config_t *cfg) {
    db_writer_t *db = malloc(sizeof(db_writer_t));
    if (db == NULL) {
        log_error("Failed to allocate db_writer");
        return NULL;
    }

    db->conn = NULL;
    db->connected = 0;
    db->buffer_count = 0;
    db->buffer_size = cfg->buffer_size;
    db->total_inserts = 0;
    db->total_errors = 0;

    db->buffer = malloc(sizeof(buffer_entry_t) * db->buffer_size);
    if (db->buffer == NULL) {
        log_error("Failed to allocate buffer (%d entries)", db->buffer_size);
        free(db);
        return NULL;
    }

    snprintf(db->conninfo, sizeof(db->conninfo),
             "host=%s port=%d dbname=%s user=%s password=%s",
             cfg->db_host, cfg->db_port, cfg->db_name,
             cfg->db_user, cfg->db_password);

    return db;
}

int db_writer_connect(db_writer_t *db) {
    if (db->connected) return 0;

    db->conn = PQconnectdb(db->conninfo);
    if (PQstatus(db->conn) != CONNECTION_OK) {
        log_error("DB connection failed: %s", PQerrorMessage(db->conn));
        PQfinish(db->conn);
        db->conn = NULL;
        db->connected = 0;
        return -1;
    }

    db->connected = 1;
    log_info("Connected to TimescaleDB: %s:%s/%s",
             PQhost(db->conn), PQport(db->conn), PQdb(db->conn));

    /* Flush any buffered entries */
    if (db->buffer_count > 0) {
        log_info("Flushing %d buffered entries", db->buffer_count);
        db_writer_flush_buffer(db);
    }

    return 0;
}

void db_writer_disconnect(db_writer_t *db) {
    if (db->conn != NULL && db->connected) {
        PQfinish(db->conn);
        db->conn = NULL;
        db->connected = 0;
        log_info("Disconnected from TimescaleDB");
    }
}

void db_writer_free(db_writer_t *db) {
    if (db == NULL) return;
    db_writer_disconnect(db);
    if (db->buffer != NULL) free(db->buffer);
    free(db);
}

static int db_exec_insert(db_writer_t *db, const char *query, int nparams,
                          const char **param_values, const int *param_lengths,
                          const int *param_formats) {
    if (!db->connected) return -1;

    PGresult *res = PQexecParams(db->conn, query, nparams, NULL,
                                  param_values, param_lengths, param_formats, 0);
    if (PQresultStatus(res) != PGRES_COMMAND_OK &&
        PQresultStatus(res) != PGRES_TUPLES_OK) {
        log_error("DB insert error: %s", PQerrorMessage(db->conn));
        PQclear(res);
        db->total_errors++;
        db->connected = 0; /* Mark as disconnected */
        PQfinish(db->conn);
        db->conn = NULL;
        return -1;
    }

    PQclear(res);
    db->total_inserts++;
    return 0;
}

int db_writer_insert(db_writer_t *db, target_table_t table,
                     const char *name, float value,
                     const char *unit, int inverter_id) {
    char timestamp[32];
    iso8601_now(timestamp, sizeof(timestamp));

    /* If DB not connected, buffer the entry */
    if (!db->connected) {
        if (db->buffer_count >= db->buffer_size) {
            log_warn("Buffer full (%d entries), dropping oldest", db->buffer_size);
            memmove(db->buffer, db->buffer + 1,
                    sizeof(buffer_entry_t) * (db->buffer_size - 1));
            db->buffer_count = db->buffer_size - 1;
        }

        buffer_entry_t *entry = &db->buffer[db->buffer_count++];
        entry->table = table;
        strncpy(entry->name, name, sizeof(entry->name) - 1);
        entry->value = value;
        strncpy(entry->unit, unit, sizeof(entry->unit) - 1);
        strncpy(entry->timestamp, timestamp, sizeof(entry->timestamp) - 1);
        return 0;
    }

    char val_str[32];
    snprintf(val_str, sizeof(val_str), "%.4f", value);

    const char *table_name;
    switch (table) {
        case TABLE_REALTIME:         table_name = "realtime"; break;
        case TABLE_FAST_SAMPLES:    table_name = "fast_samples"; break;
        case TABLE_CUMULATIVES:     table_name = "cumulatives"; break;
        case TABLE_DAILY_PRODUCTION: table_name = "daily_production"; break;
        default: return -1;
    }

    char query[512];
    if (table == TABLE_REALTIME) {
        snprintf(query, sizeof(query),
            "INSERT INTO %s (time, inverter_id, %s) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (inverter_id) DO UPDATE SET %s = EXCLUDED.%s, time = EXCLUDED.time",
            table_name, name, name, name);
    } else if (table == TABLE_CUMULATIVES) {
        snprintf(query, sizeof(query),
            "INSERT INTO %s (time, inverter_id, %s) "
            "VALUES ($1, $2, $3)",
            table_name, name);
    } else {
        snprintf(query, sizeof(query),
            "INSERT INTO %s (time, inverter_id, %s) "
            "VALUES ($1, $2, $3)",
            table_name, name);
    }

    char inv_str[8];
    snprintf(inv_str, sizeof(inv_str), "%d", inverter_id);

    const char *param_values[3] = {timestamp, inv_str, val_str};
    int param_lengths[3] = {0, 0, 0};
    int param_formats[3] = {0, 0, 0};

    int rc = db_exec_insert(db, query, 3, param_values,
                            param_lengths, param_formats);
    if (rc == 0) {
        log_read("%s: %s=%s%s", table_name, name, val_str, unit);
    }

    return rc;
}

int db_writer_flush_buffer(db_writer_t *db) {
    if (!db->connected || db->buffer_count == 0) return 0;

    int flushed = 0;
    int original_count = db->buffer_count;

    for (int i = 0; i < original_count; i++) {
        buffer_entry_t *entry = &db->buffer[i];
        if (db_writer_insert(db, entry->table, entry->name,
                              entry->value, entry->unit, 1) == 0) {
            flushed++;
        } else {
            /* DB disconnected again during flush, stop */
            break;
        }
    }

    /* Remove flushed entries from buffer */
    int remaining = original_count - flushed;
    if (remaining > 0) {
        memmove(db->buffer, db->buffer + flushed,
                sizeof(buffer_entry_t) * remaining);
    }
    db->buffer_count = remaining;

    log_info("Flushed %d/%d buffered entries to DB", flushed, original_count);
    return flushed;
}

int db_writer_insert_event(db_writer_t *db, const char *event_type,
                            const char *event_value, int severity,
                            int inverter_id) {
    char timestamp[32];
    iso8601_now(timestamp, sizeof(timestamp));

    char inv_str[8], sev_str[8];
    snprintf(inv_str, sizeof(inv_str), "%d", inverter_id);
    snprintf(sev_str, sizeof(sev_str), "%d", severity);

    const char *query = "INSERT INTO events (time, inverter_id, event_type, "
                        "event_value, severity) VALUES ($1, $2, $3, $4, $5)";

    const char *param_values[5] = {timestamp, inv_str, event_type,
                                    event_value, sev_str};
    int param_lengths[5] = {0, 0, 0, 0, 0};
    int param_formats[5] = {0, 0, 0, 0, 0};

    return db_exec_insert(db, query, 5, param_values,
                          param_lengths, param_formats);
}
```

---

### `src/watchdog.h` — Header de Health Check

```c
#ifndef WATCHDOG_H
#define WATCHDOG_H

typedef struct {
    int modbus_connected;
    int db_connected;
    long readings_total;
    long errors_total;
    int buffer_size;
    time_t start_time;
} watchdog_status_t;

void watchdog_init(void);
void watchdog_update(const watchdog_status_t *status);
void watchdog_cleanup(void);

#endif /* WATCHDOG_H */
```

---

### `src/watchdog.c` — Implementación de Health Check

```c
#include "watchdog.h"
#include "logger.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define HEALTH_FILE "/tmp/modbus-reader-health.json"

void watchdog_init(void) {
    log_info("Watchdog initialized, health file: %s", HEALTH_FILE);
}

void watchdog_update(const watchdog_status_t *status) {
    FILE *f = fopen(HEALTH_FILE, "w");
    if (f == NULL) {
        log_warn("Cannot write health file: %s", HEALTH_FILE);
        return;
    }

    char last_reading[32];
    time_t now = time(NULL);
    strftime(last_reading, sizeof(last_reading), "%Y-%m-%dT%H:%M:%SZ", gmtime(&now));

    long uptime = now - status->start_time;

    fprintf(f, "{\n");
    fprintf(f, "  \"status\": \"%s\",\n",
            (status->modbus_connected && status->db_connected) ? "ok" : "degraded");
    fprintf(f, "  \"last_reading\": \"%s\",\n", last_reading);
    fprintf(f, "  \"modbus_connected\": %s,\n",
            status->modbus_connected ? "true" : "false");
    fprintf(f, "  \"db_connected\": %s,\n",
            status->db_connected ? "true" : "false");
    fprintf(f, "  \"readings_total\": %ld,\n", status->readings_total);
    fprintf(f, "  \"errors_total\": %ld,\n", status->errors_total);
    fprintf(f, "  \"buffer_size\": %d,\n", status->buffer_size);
    fprintf(f, "  \"uptime_seconds\": %ld\n", uptime);
    fprintf(f, "}\n");

    fclose(f);
}

void watchdog_cleanup(void) {
    remove(HEALTH_FILE);
    log_info("Health file removed");
}
```

---

### `src/main.c` — Event Loop Principal

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <time.h>
#include <errno.h>

#include "config.h"
#include "logger.h"
#include "modbus_comm.h"
#include "db_writer.h"
#include "register_map.h"
#include "watchdog.h"

static volatile sig_atomic_t running = 1;
static volatile sig_atomic_t flush_buffer = 0;

static void signal_handler(int sig) {
    if (sig == SIGTERM || sig == SIGINT) {
        log_info("Received signal %d, shutting down...", sig);
        running = 0;
    } else if (sig == SIGUSR1) {
        flush_buffer = 1;
    }
}

int main(int argc, char *argv[]) {
    log_info("modbus-reader starting...");

    /* Setup signal handlers */
    struct sigaction sa;
    sa.sa_handler = signal_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGUSR1, &sa, NULL);

    /* Load configuration */
    config_t *cfg = config_from_env();
    if (cfg == NULL) {
        log_error("Failed to load configuration");
        return 1;
    }

    /* Initialize watchdog */
    watchdog_init();
    watchdog_status_t wd_status = {0};
    wd_status.start_time = time(NULL);

    /* Initialize DB writer */
    db_writer_t *db = db_writer_init(cfg);
    if (db == NULL) {
        log_error("Failed to initialize DB writer");
        config_free(cfg);
        return 1;
    }

    /* Main connection/reconnection loop */
    modbus_comm_t *mc = NULL;
    time_t last_realtime = 0;
    time_t last_fast = 0;
    time_t last_watchdog = 0;
    int readings_this_cycle = 0;
    int backoff_wait = 5;

    while (running) {
        /* Initialize Modbus communication if needed */
        if (mc == NULL) {
            mc = modbus_comm_init(cfg);
            if (mc == NULL) {
                log_error("Failed to create Modbus context, retrying in %ds...", backoff_wait);
                sleep(backoff_wait);
                backoff_wait = backoff_wait < 300 ? backoff_wait * 2 : 300;
                continue;
            }
            backoff_wait = 5;
        }

        /* Connect if not connected */
        if (!mc->connected) {
            if (modbus_comm_connect(mc) != 0) {
                int wait = modbus_comm_backoff_get(mc);
                log_error("Connection failed, retrying in %ds...", wait);
                modbus_comm_free(mc);
                mc = NULL;
                sleep(wait);
                continue;
            }

            /* Unlock the inverter protocol */
            if (modbus_comm_unlock(mc) != 0) {
                log_error("Unlock failed, reconnecting...");
                int wait = modbus_comm_backoff_get(mc);
                modbus_comm_disconnect(mc);
                modbus_comm_free(mc);
                mc = NULL;
                sleep(wait);
                continue;
            }

            modbus_comm_backoff_reset(mc);
            log_info("Connected and unlocked successfully");
        }

        /* Connect to DB if not connected */
        if (!db->connected) {
            if (db_writer_connect(db) != 0) {
                log_error("DB connection failed, buffering data");
            }
        }

        /* Flush buffer if signaled */
        if (flush_buffer && db->connected) {
            db_writer_flush_buffer(db);
            flush_buffer = 0;
        }

        time_t now = time(NULL);

        /* === Realtime readings (every poll_realtime seconds) === */
        if ((now - last_realtime) >= cfg->poll_realtime) {
            readings_this_cycle = 0;

            for (int i = 0; i < register_map_size; i++) {
                const register_entry_t *reg = &register_map[i];

                /* Skip entries with address 0 (TBD placeholders) */
                if (reg->address == 0x0000) continue;

                /* Only read REALTIME entries in this cycle */
                if (reg->table != TABLE_REALTIME) continue;

                /* Skip daily_graph in realtime cycle */
                if (reg->count >= 10) continue;

                uint16_t dest[2] = {0};
                int rc = modbus_comm_read(mc, reg->address, reg->count, dest);

                if (rc == -2) {
                    /* Disconnected — break out of reading loop */
                    db_writer_insert_event(db, "connection",
                                          "modbus_disconnected", 2, 1);
                    break;
                } else if (rc == -1) {
                    /* Transient error, skip this register */
                    wd_status.errors_total++;
                    continue;
                }

                float value;
                if (reg->count == 2) {
                    /* 32-bit value (two registers, little-endian) */
                    value = (float)((dest[1] << 16) | dest[0]) * reg->scale;
                } else {
                    value = (float)dest[0] * reg->scale;
                }

                db_writer_insert(db, reg->table, reg->name,
                                  value, reg->unit, 1);
                readings_this_cycle++;
            }

            if (readings_this_cycle > 0) {
                wd_status.readings_total += readings_this_cycle;
                last_realtime = now;
            }
        }

        /* === Fast samples (every poll_fast seconds) === */
        if ((now - last_fast) >= cfg->poll_fast) {
            for (int i = 0; i < register_map_size; i++) {
                const register_entry_t *reg = &register_map[i];

                if (reg->address == 0x0000) continue;
                if (reg->table != TABLE_FAST_SAMPLES &&
                    reg->table != TABLE_CUMULATIVES) continue;
                if (reg->count >= 10) continue;

                uint16_t dest[2] = {0};
                int rc = modbus_comm_read(mc, reg->address, reg->count, dest);

                if (rc == -2) {
                    db_writer_insert_event(db, "connection",
                                          "modbus_disconnected", 2, 1);
                    break;
                } else if (rc == -1) {
                    wd_status.errors_total++;
                    continue;
                }

                float value;
                if (reg->count == 2) {
                    value = (float)((dest[1] << 16) | dest[0]) * reg->scale;
                } else {
                    value = (float)dest[0] * reg->scale;
                }

                db_writer_insert(db, reg->table, reg->name,
                                  value, reg->unit, 1);
                wd_status.readings_total++;
            }

            last_fast = now;
        }

        /* === Update watchdog (every 30 seconds) === */
        if ((now - last_watchdog) >= 30) {
            wd_status.modbus_connected = mc ? mc->connected : 0;
            wd_status.db_connected = db->connected;
            wd_status.buffer_size = db->buffer_count;
            watchdog_update(&wd_status);
            last_watchdog = now;
        }

        /* === Sleep until next cycle === */
        sleep(1);
    }

    /* === Graceful shutdown === */
    log_info("Shutting down...");

    /* Flush remaining buffer */
    if (db->connected && db->buffer_count > 0) {
        log_info("Flushing %d remaining entries before exit...",
                 db->buffer_count);
        db_writer_flush_buffer(db);
    }

    watchdog_cleanup();
    db_writer_free(db);

    if (mc != NULL) {
        modbus_comm_disconnect(mc);
        modbus_comm_free(mc);
    }

    config_free(cfg);
    log_info("modbus-reader stopped.");
    return 0;
}
```

> **Nota sobre `main.c`**: El archivo maneja dos ciclos de lectura: `realtime` (cada 5 segundos, solo `TABLE_REALTIME`) y `fast` (cada 60 segundos, `TABLE_FAST_SAMPLES` y `TABLE_CUMULATIVES`). La lectura de `daily_production` (registro 0xC000, 48 registros) se implementará en un ciclo separado (1 vez al día al inicio del día) cuando se complete el reverse engineering.

> **Nota sobre el `Makefile`**: Se debe agregar `src/logger.h` como dependencia implícita. El Makefile actual ya compila todos los archivos `.c` del directorio `src/`, y los `.h` se incluyen vía `#include`, por lo que no necesita cambios.