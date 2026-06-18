#ifndef WATCHDOG_H
#define WATCHDOG_H

#include <time.h>

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