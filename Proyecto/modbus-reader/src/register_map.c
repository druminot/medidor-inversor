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
 *
 * PROTOCOLO: Modbus RTU sobre RS232 (adaptador CH340 USB-RS232)
 * BAUDRATE: 9600 (por defecto), SLAVE: 1 (por defecto)
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

    /* === Acumulados — leídos cada 60 segundos === */
    {0x1021, 2, "energy_total",   "kWh", 0.01,  TABLE_CUMULATIVES},
    {0x0000, 0, "energy_daily",   "kWh", 0.01,  TABLE_CUMULATIVES},   /* TBD */
    {0x0000, 0, "hours_total",    "h",   0.01,  TABLE_CUMULATIVES},   /* TBD */
    {0x0000, 0, "co2_saved",      "kg",  0.01,  TABLE_CUMULATIVES},   /* TBD */

    /* === Gráfico diario — leído 1 vez al inicio del día === */
    {0xC000, 48, "daily_graph",   "W",   0.01,  TABLE_DAILY_PRODUCTION},
};

const int register_map_size = sizeof(register_map) / sizeof(register_map[0]);