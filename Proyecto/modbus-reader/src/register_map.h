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

extern const register_entry_t register_map[];
extern const int register_map_size;

#endif /* REGISTER_MAP_H */