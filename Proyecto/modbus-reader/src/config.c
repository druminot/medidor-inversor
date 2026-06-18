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

    cfg->serial_port   = get_env_str("SERIAL_PORT",   "/dev/ttyUSB0");
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