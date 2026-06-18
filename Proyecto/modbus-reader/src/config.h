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