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