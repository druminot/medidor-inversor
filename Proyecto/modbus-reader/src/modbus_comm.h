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