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
            return -2;
        }
        log_warn("Modbus read error at 0x%04X: %s", address, modbus_strerror(errno));
        return -1;
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